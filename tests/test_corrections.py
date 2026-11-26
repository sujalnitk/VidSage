"""Correction flows with synthetic captions and external-provider responses only."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from backend.schemas import PipelineError
from backend.service import Session, ask_question, prepare_video
from test_followups import CAPTION, CHAT, EMBED, answer, embedding, response


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {
            "VIDSAGE_DB": str(Path(directory) / "pilot.sqlite3"),
            "LLM_MODEL": CHAT["model"], "LLM_API_KEY": CHAT["api_key"],
            "EMBEDDING_MODEL": EMBED["model"], "EMBEDDING_API_KEY": EMBED["api_key"],
        }, clear=True))
        self.enterContext(patch("dotenv.load_dotenv"))
        self.enterContext(patch("youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=
            SimpleNamespace(language_code="en", is_generated=False,
                            snippets=[SimpleNamespace(text=CAPTION, start=4, duration=8)])))
        self.embed = self.enterContext(patch("llm.litellm.embedding", side_effect=embedding))
        self.complete = self.enterContext(patch("llm.litellm.completion"))

    def app(self):
        app = AppTest.from_file("main.py", default_timeout=20).run()
        next(w for w in app.text_input if w.label == "YouTube Video ID").set_value("dQw4w9WgXcQ").run()
        open_video = next((b for b in app.button if b.label == "Open video"), None)
        if open_video:
            open_video.click().run()
        self.assertFalse(app.exception)
        return app

    def send(self, app, question, reply, query=None, clarification=None):
        replies = [] if query is None and clarification is None else [
            response({"query": query, "clarification": clarification})]
        if reply:
            replies.append(reply)
        self.complete.side_effect = replies
        app.chat_input[0].set_value(question).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)

    def test_supported_correction_appends_evidence_and_preserves_original_reply(self):
        app = self.app()
        original = "Search always finds the relevant passages."
        self.send(app, "Does search always work?", answer(original))
        original_turn = dict(app.session_state["history"][0])
        correction = "My earlier claim was unsupported: search can miss relevant passages."
        self.send(app, "That seems wrong", answer(correction), "Recheck whether search can miss passages")
        self.assertEqual([m.markdown[0].value for m in app.chat_message],
                         ["Does search always work?", original, "That seems wrong", correction])
        self.assertEqual(app.session_state["history"][0], original_turn)
        self.assertEqual(app.chat_message[-1].text[0].value, "Search can miss relevant passages.")
        self.assertEqual(app.chat_message[-1].get("link_button")[0].proto.url,
                         "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=4s")
        payload = json.loads(self.complete.call_args.kwargs["messages"][-1]["content"])
        self.assertEqual(payload["question"], "That seems wrong")
        self.assertEqual(payload["history"][0]["answer"], original)
        self.assertEqual(payload["sources"], [{"id": "S1", "text": CAPTION}])

    def test_unsupported_suggestion_gets_caption_explanation_instead_of_agreement(self):
        app = self.app()
        self.send(app, "Does search ever fail?", answer("Search can miss relevant passages."))
        explanation = "The captions say search can miss relevant passages; they do not support your proposed correction."
        self.send(app, "No, search always works. Correct your answer.", answer(explanation),
                  "Check whether search always works")
        self.assertEqual(app.chat_message[-1].markdown[0].value, explanation)
        self.assertEqual(app.chat_message[-1].text[0].value, "Search can miss relevant passages.")
        self.assertEqual(len(app.session_state["history"]), 2)

    def test_missing_evidence_is_displayed_without_replacing_original(self):
        app = self.app()
        self.send(app, "How many passages does search miss?", answer("Search misses ten passages."))
        self.send(app, "That seems wrong; verify the number", response({"outcome": "insufficient_context", "claims": []}),
                  "Number of passages search misses")
        self.assertEqual(app.chat_message[1].markdown[0].value, "Search misses ten passages.")
        self.assertIn("not contain enough evidence", app.chat_message[-1].markdown[0].value)
        self.assertFalse(app.chat_message[-1].get("link_button"))
        self.assertEqual(app.session_state["history"][-1]["result"]["outcome"], "insufficient_context")

    def test_ambiguous_challenge_asks_for_clarification_before_retrieval(self):
        app = self.app()
        self.send(app, "Explain RAG and summaries", answer("RAG retrieves passages; summaries shorten them."))
        retrievals = self.embed.call_count
        self.send(app, "That seems wrong", None,
                  clarification="Do you mean the retrieval claim or the summary claim?")
        self.assertEqual(app.chat_message[-1].markdown[0].value,
                         "Do you mean the retrieval claim or the summary claim?")
        self.assertEqual(self.embed.call_count, retrievals)
        self.assertEqual(app.session_state["history"][-1]["result"]["outcome"], "clarification")

    def test_invalid_correction_evidence_keeps_original_exchange(self):
        session = Session()
        ready = prepare_video(session, "dQw4w9WgXcQ", EMBED)
        self.complete.return_value = answer("Search can miss relevant passages.")
        original = ask_question(session, ready.id, "Explain search", "original", CHAT, EMBED)
        for source_id, excerpt in (("S1", "Search always works."), ("S999", "Search can miss relevant passages.")):
            with self.subTest(source_id=source_id):
                self.complete.side_effect = [response({"query": "Recheck search", "clarification": None}),
                    response({"outcome": "answered", "claims": [{"text": "Agreed, search always works.",
                        "evidence": [{"source_id": source_id, "excerpt": excerpt}]}]})]
                with self.assertRaises(PipelineError) as error:
                    ask_question(session, ready.id, "Correct your answer", source_id, CHAT, EMBED)
                self.assertEqual(error.exception.category, "invalid_citation")
                self.assertEqual(len(session.history), 1)
                self.assertEqual(session.history[0]["answer"], original.answer)
