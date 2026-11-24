import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
        self.fetch = self.enterContext(patch(
            "youtube_transcript_api.YouTubeTranscriptApi.fetch",
            return_value=SimpleNamespace(snippets=[SimpleNamespace(text="This video explains retrieval augmented generation.")]),
        ))
        self.embed = self.enterContext(patch(
            "llm.litellm.embedding",
            side_effect=lambda input, **kwargs: SimpleNamespace(data=[
                {"index": i, "embedding": [1.0, 0.0, 0.0]} for i in range(len(input))
            ]),
        ))
        self.complete = self.enterContext(patch(
            "llm.litellm.completion",
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="The video explains RAG."))]),
        ))

    def app(self):
        app = AppTest.from_file("main.py", default_timeout=20).run()
        self.assertFalse(app.exception)
        return app

    def test_starts_without_credentials_and_validates_before_external_calls(self):
        app = ask(self.app())
        self.assertFalse(app.exception)
        self.assertIn("Enter an API key for gemini", app.error[0].value)
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

    def test_google_environment_key_stays_out_of_password_field(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "server-google-key"}):
            app = self.app()
            self.assertEqual(field(app, "Chat API key").value, "")
            ask(app)
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(self.complete.call_args.kwargs["api_key"], "server-google-key")
            self.assertEqual(self.embed.call_args.kwargs["api_key"], "server-google-key")

    def test_openai_compatible_endpoint_shares_key_without_google(self):
        app = self.app()
        field(app, "Chat model").set_value("openai/custom-chat").run()
        field(app, "Chat API key").set_value("chat-secret")
        field(app, "Chat endpoint URL (optional)").set_value("https://custom.example/v1")
        field(app, "Embedding endpoint URL (optional)").set_value("https://custom.example/v1")
        ask(app)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["history"][0]["answer"], "The video explains RAG.")
        self.assertEqual(self.complete.call_args.kwargs["model"], "openai/custom-chat")
        self.assertEqual(self.complete.call_args.kwargs["api_base"], "https://custom.example/v1")
        self.assertEqual(self.embed.call_args.kwargs["api_key"], "chat-secret")
        self.assertNotIn("chat-secret", str(app.session_state["history"]))

    def test_anthropic_chat_with_separate_openai_embedding_key(self):
        app = self.app()
        field(app, "Chat model").set_value("anthropic/test-chat").run()
        field(app, "Chat API key").set_value("anthropic-secret")
        field(app, "Embedding model").set_value("openai/test-embedding").run()
        field(app, "Embedding API key (optional)").set_value("embedding-secret")
        ask(app)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(self.complete.call_args.kwargs["api_key"], "anthropic-secret")
        self.assertEqual(self.embed.call_args.kwargs["api_key"], "embedding-secret")

    def test_chat_key_is_not_forwarded_to_another_embedding_provider_or_endpoint(self):
        for model, url in (("openai/test-embedding", ""), ("gemini/test-embedding", "https://other.example")):
            with self.subTest(model=model, url=url):
                app = self.app()
                field(app, "Chat API key").set_value("google-secret")
                field(app, "Embedding model").set_value(model).run()
                field(app, "Embedding endpoint URL (optional)").set_value(url)
                ask(app)
                self.assertFalse(app.exception)
                self.assertTrue(app.error)
                self.fetch.assert_not_called()
                self.embed.assert_not_called()

    def test_switching_chat_provider_clears_the_key_field(self):
        app = self.app()
        field(app, "Chat API key").set_value("google-secret").run()
        field(app, "Chat model").set_value("openai/test").run()
        self.assertEqual(field(app, "Chat API key").value, "")

    def test_provider_error_redacts_credentials_and_does_not_add_history(self):
        app = self.app()
        field(app, "Chat API key").set_value("private-key")
        self.complete.side_effect = RuntimeError("Provider rejected private-key")
        ask(app)
        self.assertFalse(app.exception)
        self.assertIn("[redacted]", app.error[0].value)
        self.assertNotIn("private-key", app.error[0].value)
        self.assertEqual(app.session_state["history"], [])

    def test_rejects_empty_chat_response(self):
        app = self.app()
        field(app, "Chat API key").set_value("test-key")
        self.complete.return_value.choices[0].message.content = None
        ask(app)
        self.assertIn("no text answer", app.error[0].value)
        self.assertEqual(app.session_state["history"], [])
