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
    app.text_area[0].set_value("What is the video about?")
    next(button for button in app.button if button.label == "💡 Get Answer").click().run()
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

    def app(self):
        app = AppTest.from_file("main.py", default_timeout=20).run()
        self.assertFalse(app.exception)
        return app

    def test_starts_without_credentials_and_validates_before_external_calls(self):
        app = ask(self.app())
        self.assertFalse(app.exception)
        self.assertIn("Configure an API key for gemini", app.error[0].value)
        self.fetch.assert_not_called()
        self.embed.assert_not_called()
        self.complete.assert_not_called()

    def test_validates_video_and_question_before_provider_settings(self):
        app = self.app()
        next(button for button in app.button if button.label == "💡 Get Answer").click().run()
        self.assertEqual(app.warning[0].value, "Please enter a YouTube video ID.")
        field(app, "YouTube Video ID").set_value("dQw4w9WgXcQ")
        next(button for button in app.button if button.label == "💡 Get Answer").click().run()
        self.assertEqual(app.warning[0].value, "Please type a question to ask about the video.")
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

    def test_repeated_submit_reuses_completed_turn_and_index(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        ask(app)
        self.assertFalse(app.error)
        self.assertEqual(len(app.session_state["history"]), 1)
        self.fetch.assert_called_once()
        self.assertEqual(self.embed.call_count, 2)
        self.complete.assert_called_once()

    def test_clear_controls_and_video_switch_remove_stale_answers(self):
        os.environ["LLM_API_KEY"] = "test-key"
        app = ask(self.app())
        next(b for b in app.button if b.label == "🧹 Clear History").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["history"], [])
        ask(app)
        field(app, "YouTube Video ID").set_value("abcdefghijk").run()
        self.assertEqual(app.session_state["history"], [])
        next(b for b in app.button if b.label == "🔁 Clear Fields").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(field(app, "YouTube Video ID").value, "")
        self.assertEqual(app.text_area[0].value, "")

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
