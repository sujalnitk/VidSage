import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest


def field(app, label):
    return next(widget for widget in app.text_input if widget.label == label)


def ask(app):
    field(app, "YouTube Video ID").set_value("dQw4w9WgXcQ")
    next(b for b in app.button if b.label == "Open video").click().run()
    app.chat_input[0].set_value("What is the video about?").run()
    return app


class ProviderAppTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        os.environ["VIDSAGE_DB"] = str(Path(self.directory) / "pilot.sqlite3")
        self.load_env = self.enterContext(patch("dotenv.load_dotenv"))
        self.fetch = self.enterContext(patch(
            "youtube_transcript_api.YouTubeTranscriptApi.fetch",
            return_value=SimpleNamespace(language_code="en", is_generated=False, snippets=[SimpleNamespace(text="This video explains retrieval augmented generation.", start=2.5, duration=4)]),
        ))
        self.embed = self.enterContext(patch(
            "llm.litellm.embedding",
            side_effect=lambda input, **kwargs: SimpleNamespace(data=[
                {"index": i, "embedding": [1.0, 0.0, 0.0]} for i in range(len(input))
            ]),
        ))
        self.complete = self.enterContext(patch(
            "llm.litellm.completion",
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"outcome": "answered", "claims": [{"text": "The video explains RAG.", "evidence": [{"source_id": "S1", "excerpt": "retrieval augmented generation"}]}]})))]),
        ))
        self.complete.side_effect = self.completion

    def completion(self, **kwargs):
        if kwargs["max_tokens"] == 300:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps({"query": "Explain retrieval augmented generation", "clarification": None})))])
        return self.complete.return_value

    def app(self):
        app = AppTest.from_file("main.py", default_timeout=20).run()
        self.assertFalse(app.exception)
        return app

    def test_video_conversation_displays_exchanges_in_chronological_order(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = self.app()
        field(app, "YouTube Video ID").set_value("dQw4w9WgXcQ").run()
        next(b for b in app.button if b.label == "Open video").click().run()
        app.chat_input[0].set_value("What is RAG?").run()
        app.chat_input[0].set_value("Explain more").run()
        self.assertFalse(app.exception)
        self.assertEqual([message.name for message in app.chat_message],
                         ["user", "assistant", "user", "assistant"])
        self.assertEqual([message.markdown[0].value for message in app.chat_message],
                         ["What is RAG?", "The video explains RAG.",
                          "Explain more", "The video explains RAG."])
        self.assertTrue(any("Session-only" in item.value and "reload" in item.value for item in app.caption))

    def test_preparation_failure_keeps_message_until_explicit_retry(self):
        os.environ["LLM_API_KEY"] = "test-key"
        self.fetch.side_effect = RuntimeError("Captions temporarily unavailable")
        app = ask(self.app())
        self.assertEqual([m.markdown[0].value for m in app.chat_message],
                         ["What is the video about?"])
        self.assertIn("failed", app.error[0].value)
        app.run()
        self.fetch.assert_called_once()
        self.fetch.side_effect = None
        next(b for b in app.button if b.label == "Retry").click().run()
        self.assertFalse(app.error)
        self.assertEqual(len(app.chat_message), 2)
        self.assertEqual(len(app.session_state["history"]), 1)
        self.assertEqual(self.fetch.call_count, 2)
        app.run()
        self.assertEqual(self.fetch.call_count, 2)
        self.complete.assert_called_once()

    def test_preparation_failure_preserves_existing_exchange_and_ready_video(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        self.fetch.side_effect = RuntimeError("temporary caption failure")
        next(c for c in app.checkbox if "Refresh captions" in c.label).check()
        app.chat_input[0].set_value("Explain more").run()
        self.assertEqual([m.name for m in app.chat_message], ["user", "assistant", "user"])
        self.assertEqual(len(app.session_state["history"]), 1)
        next(c for c in app.checkbox if "Refresh captions" in c.label).uncheck().run()
        next(b for b in app.button if b.label == "Retry").click().run()
        self.assertFalse(app.error)
        self.assertEqual(len(app.session_state["history"]), 2)
        self.assertEqual(self.fetch.call_count, 2)  # initial fetch and failed refresh only

    def test_answer_failure_retry_preserves_history_index_and_original_consent(self):
        os.environ["LLM_API_KEY"] = "private-key"
        app = ask(self.app())
        self.complete.side_effect = RuntimeError("Provider rejected private-key")
        app.chat_input[0].set_value("Explain more").run()
        self.assertEqual([m.name for m in app.chat_message], ["user", "assistant", "user"])
        self.assertEqual(app.chat_message[-1].markdown[0].value, "Explain more")
        self.assertIn("[redacted]", app.error[0].value)
        self.assertNotIn("private-key", str(app.session_state["submission"]))
        self.assertEqual(len(app.session_state["history"]), 1)
        self.assertTrue(app.chat_input[0].disabled)
        calls = self.complete.call_count
        next(c for c in app.checkbox if "30 days" in c.label).check().run()
        self.assertEqual(self.complete.call_count, calls)
        self.complete.side_effect = self.completion
        next(b for b in app.button if b.label == "Retry").click().run()
        self.assertFalse(app.error)
        self.assertEqual([m.name for m in app.chat_message], ["user", "assistant", "user", "assistant"])
        self.assertEqual([turn["consent"] for turn in app.session_state["history"]], [False, False])
        self.fetch.assert_called_once()
        calls = self.complete.call_count
        app.run()
        self.assertEqual(self.complete.call_count, calls)
        self.assertFalse(any(b.label == "Retry" for b in app.button))

    def test_retry_respects_global_attempt_and_spending_reservations(self):
        from backend.store import Store

        os.environ["LLM_API_KEY"] = "test-key"
        for limit in ("attempts", "spend"):
            with self.subTest(limit=limit):
                os.environ["VIDSAGE_DB"] = str(Path(self.directory) / f"{limit}.sqlite3")
                self.fetch.side_effect = RuntimeError("temporary caption failure")
                app = ask(self.app())
                store = Store(os.environ["VIDSAGE_DB"])
                if limit == "attempts":
                    for _ in range(99):
                        store.reserve(0)
                else:
                    store.reserve(5)
                    rate_file = Path(self.directory) / "rates.json"
                    rate_file.write_text(json.dumps({
                        "verified_at": "2026-11-25", "source": "https://example.com/prices",
                        "models": {},
                    }))
                    os.environ["VIDSAGE_RATE_CARD"] = str(rate_file)
                calls = self.fetch.call_count
                next(b for b in app.button if b.label == "Retry").click().run()
                self.assertIn("limit", app.error[0].value)
                self.assertEqual(self.fetch.call_count, calls)
                self.assertEqual(len(app.chat_message), 1)
                self.assertEqual(app.session_state["history"], [])
                os.environ.pop("VIDSAGE_RATE_CARD", None)

    def test_changed_refresh_waits_for_decision_and_decline_preserves_discussion(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        session = app.session_state["session"]
        ready, history = session.prepared, list(session.history)
        self.fetch.return_value.snippets = [SimpleNamespace(
            text="Changed retrieval augmented generation captions.", start=9, duration=4)]
        next(c for c in app.checkbox if "Refresh captions" in c.label).check()
        app.chat_input[0].set_value("Explain the change").run()
        self.assertFalse(app.exception)
        self.assertIs(session.prepared, ready)
        self.assertEqual(session.history, history)
        self.assertTrue(any("Explain the change" in m.value for m in app.markdown))
        calls = self.embed.call_count, self.complete.call_count, self.fetch.call_count
        next(b for b in app.button if b.label == "Keep current captions").click().run()
        self.assertIs(session.prepared, ready)
        self.assertEqual(session.history, history)
        self.assertEqual(calls, (self.embed.call_count, self.complete.call_count, self.fetch.call_count))

    def test_unchanged_refresh_keeps_prior_exchange_and_its_context(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        session = app.session_state["session"]
        ready, conversation = session.prepared, session.conversation_id
        next(c for c in app.checkbox if "Refresh captions" in c.label).check()
        app.chat_input[0].set_value("Explain more").run()
        self.assertFalse(app.error)
        self.assertIs(session.prepared, ready)
        self.assertEqual(session.conversation_id, conversation)
        self.assertEqual(len(app.chat_message), 4)
        self.assertEqual(self.embed.call_count, 3)  # documents once; two questions

    def test_changed_refresh_accept_starts_fresh_without_answering_pending_question(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        session = app.session_state["session"]
        old = session.conversation_id
        self.fetch.return_value.snippets = [SimpleNamespace(
            text="Changed retrieval augmented generation captions.", start=9, duration=4)]
        next(c for c in app.checkbox if "Refresh captions" in c.label).check()
        app.chat_input[0].set_value("Explain the change").run()
        candidate = session.pending_refresh
        calls = self.embed.call_count, self.complete.call_count, self.fetch.call_count
        next(b for b in app.button if b.label == "Use changed captions").click().run()
        self.assertFalse(app.exception)
        self.assertIs(session.prepared, candidate)
        self.assertNotEqual(session.conversation_id, old)
        self.assertEqual(session.history, [])
        self.assertEqual([m.markdown[0].value for m in app.chat_message], ["Explain the change"])
        self.assertTrue(any("not been sent" in item.value for item in app.info))
        self.assertEqual(calls, (self.embed.call_count, self.complete.call_count, self.fetch.call_count))
        app.chat_input[0].set_value("What changed?").run()
        self.assertFalse(app.error)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(app.get("link_button")[0].proto.url,
                         "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=9s")

    def test_failed_caption_refresh_keeps_usable_discussion_and_redacts_error(self):
        os.environ["LLM_API_KEY"] = "private-key"
        app = ask(self.app())
        session = app.session_state["session"]
        ready, history = session.prepared, list(session.history)
        self.fetch.side_effect = RuntimeError("Fetch failed private-key")
        next(c for c in app.checkbox if "Refresh captions" in c.label).check()
        app.chat_input[0].set_value("Explain more").run()
        self.assertFalse(app.exception)
        self.assertNotIn("private-key", app.error[0].value)
        self.assertIn("[redacted]", app.error[0].value)
        self.assertIs(session.prepared, ready)
        self.assertEqual(session.history, history)

    def test_refresh_obeys_server_reservation_before_fetching_replacement(self):
        from backend.store import Store
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        session = app.session_state["session"]
        ready = session.prepared
        store = Store(os.environ["VIDSAGE_DB"])
        for _ in range(99):
            store.reserve(0)
        calls = self.fetch.call_count, self.embed.call_count
        next(c for c in app.checkbox if "Refresh captions" in c.label).check()
        app.chat_input[0].set_value("Refresh please").run()
        self.assertIn("daily request or spend limit", app.error[0].value)
        self.assertIs(session.prepared, ready)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(calls, (self.fetch.call_count, self.embed.call_count))

    def test_starts_without_credentials_and_validates_before_external_calls(self):
        app = ask(self.app())
        self.assertFalse(app.exception)
        self.assertIn("Configure an API key for gemini", app.error[0].value)
        self.fetch.assert_not_called()
        self.embed.assert_not_called()
        self.complete.assert_not_called()

    def test_validates_video_and_question_before_provider_settings(self):
        app = self.app()
        app.chat_input[0].set_value("What is the video about?").run()
        self.assertIn("Please enter a YouTube video ID and select Open video.", [item.value for item in app.warning])
        field(app, "YouTube Video ID").set_value("dQw4w9WgXcQ")
        next(b for b in app.button if b.label == "Open video").click().run()
        app.chat_input[0].set_value("   ").run()
        self.assertIn("Please type a question to ask about the video.", [item.value for item in app.warning])
        self.fetch.assert_not_called()

    def test_google_server_key_never_appears_in_browser_fields(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "server-google-key"}):
            app = self.app()
            self.assertEqual([item.label for item in app.text_input], ["YouTube Video ID"])
            ask(app)
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(self.complete.call_args.kwargs["api_key"], "server-google-key")
            self.assertEqual(self.embed.call_args.kwargs["api_key"], "server-google-key")

    def test_openai_compatible_endpoint_shares_key_without_google(self):
        os.environ.update({
            "LLM_MODEL": "openai/custom-chat", "LLM_API_KEY": "chat-secret",
            "LLM_BASE_URL": "https://custom.example/v1",
            "EMBEDDING_BASE_URL": "https://custom.example/v1",
        })
        app = self.app()
        ask(app)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["history"][0]["answer"], "The video explains RAG.")
        self.assertEqual(self.complete.call_args.kwargs["model"], "openai/custom-chat")
        self.assertEqual(self.complete.call_args.kwargs["api_base"], "https://custom.example/v1")
        self.assertEqual(self.embed.call_args.kwargs["api_key"], "chat-secret")
        self.assertNotIn("chat-secret", str(app.session_state["history"]))

    def test_anthropic_chat_with_separate_openai_embedding_key(self):
        os.environ.update({
            "LLM_MODEL": "anthropic/test-chat", "LLM_API_KEY": "anthropic-secret",
            "EMBEDDING_MODEL": "openai/test-embedding", "EMBEDDING_API_KEY": "embedding-secret",
        })
        app = self.app()
        ask(app)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(self.complete.call_args.kwargs["api_key"], "anthropic-secret")
        self.assertEqual(self.embed.call_args.kwargs["api_key"], "embedding-secret")

    def test_chat_key_is_not_forwarded_to_another_embedding_provider_or_endpoint(self):
        for model, url in (("openai/test-embedding", ""), ("gemini/test-embedding", "https://other.example")):
            with self.subTest(model=model, url=url):
                os.environ.update({
                    "LLM_API_KEY": "google-secret", "EMBEDDING_MODEL": model, "EMBEDDING_BASE_URL": url,
                })
                app = self.app()
                ask(app)
                self.assertFalse(app.exception)
                self.assertTrue(app.error)
                self.fetch.assert_not_called()
                self.embed.assert_not_called()

    def test_loads_repo_local_env_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".env"
            config.write_text("LLM_MODEL=openai/test-chat\nLLM_API_KEY=file-secret\n")
            self.load_env.side_effect = lambda path, override: load_dotenv(config, override=override)
            app = self.app()
            self.load_env.assert_called_once_with(Path.cwd() / ".env", override=False)
            ask(app)
            self.assertFalse(app.error)
            self.assertEqual(self.complete.call_args.kwargs["model"], "openai/test-chat")
            self.assertEqual(self.complete.call_args.kwargs["api_key"], "file-secret")
            self.assertEqual(self.embed.call_args.kwargs["api_key"], "file-secret")

    def test_deployment_environment_takes_precedence_over_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".env"
            config.write_text("LLM_API_KEY=file-secret\n")
            self.load_env.side_effect = lambda path, override: load_dotenv(config, override=override)
            os.environ["LLM_API_KEY"] = "deployment-secret"
            app = ask(self.app())
            self.assertFalse(app.error)
            self.assertEqual(self.complete.call_args.kwargs["api_key"], "deployment-secret")

    def test_provider_error_redacts_credentials_and_does_not_add_history(self):
        os.environ["LLM_API_KEY"] = "private-key"
        app = self.app()
        self.complete.side_effect = RuntimeError("Provider rejected private-key")
        ask(app)
        self.assertFalse(app.exception)
        self.assertIn("[redacted]", app.error[0].value)
        self.assertNotIn("private-key", app.error[0].value)
        self.assertEqual(app.session_state["history"], [])

    def test_rejects_empty_chat_response(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = self.app()
        self.complete.return_value.choices[0].message.content = None
        ask(app)
        self.assertIn("no text answer", app.error[0].value)
        self.assertEqual(app.session_state["history"], [])

    def test_deliberate_repeated_message_creates_new_exchange_and_reuses_index(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        app.chat_input[0].set_value("Explain more").run()
        app.chat_input[0].set_value("Explain more").run()
        self.assertFalse(app.error)
        self.assertEqual([turn["question"] for turn in app.session_state["history"]],
                         ["What is the video about?", "Explain more", "Explain more"])
        self.fetch.assert_called_once()
        self.assertEqual(self.embed.call_count, 4)
        self.assertEqual(self.complete.call_count, 5)

    def test_rerun_does_not_redeliver_completed_submission(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        app.run()
        next(c for c in app.checkbox if c.label == "Show instructions").check().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.chat_message), 2)
        self.fetch.assert_called_once()
        self.assertEqual(self.embed.call_count, 2)
        self.complete.assert_called_once()

    def test_chat_keeps_caption_links_excerpts_and_downloads(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        assistant = app.chat_message[1]
        self.assertEqual(assistant.text[0].value, "retrieval augmented generation")
        self.assertEqual(app.get("link_button")[0].proto.url,
                         "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=2s")
        self.assertEqual([item.label for item in app.get("download_button")],
                         ["💾 Download Answer (txt)", "📥 Download Full History (JSON)"])

    def test_video_edits_preserve_discussion_until_explicit_open(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        original_conversation = app.session_state["session"].conversation_id
        for draft in ("", "https://youtu", "abcdefghijk"):
            field(app, "YouTube Video ID").set_value(draft).run()
            self.assertEqual(len(app.chat_message), 2)
            self.assertEqual(app.session_state["session"].conversation_id, original_conversation)
        self.assertTrue(any("discards" in item.value and "discussion" in item.value for item in app.warning))
        next(b for b in app.button if b.label == "Open video").click().run()
        self.assertEqual(app.session_state["history"], [])
        self.assertEqual(len(app.chat_message), 0)
        self.assertNotIn("submission", app.session_state)
        field(app, "YouTube Video ID").set_value("dQw4w9WgXcQ").run()
        next(b for b in app.button if b.label == "Open video").click().run()
        self.assertEqual(app.session_state["history"], [])
        self.assertNotEqual(app.session_state["session"].conversation_id, original_conversation)

    def test_same_video_url_and_invalid_open_preserve_active_discussion(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        original_conversation = app.session_state["session"].conversation_id
        for value in ("https://youtu.be/dQw4w9WgXcQ?t=10", "https://youtu"):
            field(app, "YouTube Video ID").set_value(value).run()
            next(b for b in app.button if b.label == "Open video").click().run()
            self.assertEqual(len(app.chat_message), 2)
            self.assertEqual(app.session_state["session"].conversation_id, original_conversation)
        self.assertTrue(app.error)
        app.chat_input[0].set_value("Explain more").run()
        self.assertFalse(app.error)
        self.assertEqual(len(app.chat_message), 4)
        self.fetch.assert_called_once()

    def test_clear_controls_and_video_switch_remove_stale_answers(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        self.assertTrue(any("discards" in item.value for item in app.warning))
        self.assertTrue(any("retained data remains" in item.value for item in app.caption))
        next(b for b in app.button if b.label == "🧹 Clear History").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["history"], [])
        self.assertNotIn("submission", app.session_state)
        self.assertEqual(len(app.chat_message), 0)
        ask(app)
        field(app, "YouTube Video ID").set_value("abcdefghijk").run()
        next(b for b in app.button if b.label == "Open video").click().run()
        self.assertEqual(app.session_state["history"], [])
        next(b for b in app.button if b.label == "🔁 Clear Fields").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(field(app, "YouTube Video ID").value, "")
        self.assertEqual(app.chat_input[0].value, "")
        self.assertNotIn("submission", app.session_state)
        self.assertIsNone(app.session_state["session"].video_id)

    def test_pilot_requires_prices_before_external_calls(self):
        os.environ.update(LLM_API_KEY="test-key", VIDSAGE_PILOT="1")
        app = ask(self.app())
        self.assertIn("rate card", app.error[0].value)
        self.fetch.assert_not_called()
        self.embed.assert_not_called()

    def test_feedback_and_delete_retained_data(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = self.app()
        next(c for c in app.checkbox if "30 days" in c.label).check()
        ask(app)
        self.assertFalse(app.error)
        next(b for b in app.button if b.label == "Save feedback").click().run()
        self.assertFalse(app.error)
        next(b for b in app.button if b.label == "Delete my retained data").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["history"], [])

    def test_groq_chat_routes_separate_embedding_credentials(self):
        os.environ.update({
            "LLM_MODEL": "groq/openai/gpt-oss-120b", "GROQ_API_KEY": "groq-secret",
            "EMBEDDING_MODEL": "gemini/gemini-embedding-001", "EMBEDDING_API_KEY": "google-secret",
        })
        app = ask(self.app())
        self.assertFalse(app.error)
        self.assertEqual(self.complete.call_args.kwargs["model"], "groq/openai/gpt-oss-120b")
        self.assertEqual(self.complete.call_args.kwargs["api_key"], "groq-secret")
        self.assertEqual(self.embed.call_args.kwargs["api_key"], "google-secret")
        self.assertNotIn("groq-secret", str(app.session_state["history"]))

    def test_groq_key_does_not_authenticate_google_embeddings(self):
        os.environ.update({"LLM_MODEL": "groq/openai/gpt-oss-120b", "LLM_API_KEY": "groq-secret",
                           "EMBEDDING_MODEL": "gemini/gemini-embedding-001"})
        app = ask(self.app())
        self.assertIn("Configure an API key for gemini", app.error[0].value)
        self.fetch.assert_not_called()
        self.complete.assert_not_called()
