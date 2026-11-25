"""Conversation behavior at the service and viewer boundaries; all providers are fake."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from backend.ingestion import map_timestamps
from backend.schemas import PipelineError
from backend.service import Session, ask_question, prepare_video

CHAT = {"model": "openai/chat", "api_key": "test-chat"}
EMBED = {"model": "openai/embedding", "api_key": "test-embedding"}
CAPTION = "RAG retrieves passages. Search can miss relevant passages. Summaries shorten passages."


def response(data):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))])


def embedding(input, **kwargs):
    return SimpleNamespace(data=[{"index": i, "embedding": [1.0, 0.0, 0.0]} for i in range(len(input))])


def answer(text):
    return response({"outcome": "answered", "claims": [{"text": text, "evidence": [
        {"source_id": "S1", "excerpt": "Search can miss relevant passages."}]}]})


class FollowupServiceTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("llm.litellm.embedding", side_effect=embedding))
        source = map_timestamps("dQw4w9WgXcQ", "en", False, [
            {"text": CAPTION, "start": 4, "duration": 8}])
        self.enterContext(patch("backend.service.fetch_transcript", return_value=source))
        self.complete = self.enterContext(patch("llm.litellm.completion"))
        self.session = Session()
        self.ready = prepare_video(self.session, source.video_id, EMBED)

    def ask(self, question):
        return ask_question(self.session, self.ready.id, question, str(len(self.session.requests)), CHAT, EMBED)

    def test_simplification_keeps_original_request_and_referenced_answer(self):
        original = "1. RAG retrieves passages. 2. Search can miss relevant passages."
        self.complete.return_value = answer(original)
        self.ask("Explain the two points")
        self.complete.side_effect = [response({"query": "Search limitations", "clarification": None}),
                                     answer("Search may miss useful text.")]
        result = self.ask("Simplify your second point")
        payload = json.loads(self.complete.call_args.kwargs["messages"][-1]["content"])
        self.assertEqual(payload["question"], "Simplify your second point")
        self.assertEqual(payload["history"], [{"exchange_number": 1, "question": "Explain the two points", "answer": original}])
        self.assertEqual(payload["retrieval_query"], "Search limitations")
        self.assertEqual(result.answer, "Search may miss useful text.")
        self.assertEqual(result.claims[0].citations[0].url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=4s")

    def test_previous_answer_is_not_accepted_as_caption_evidence(self):
        self.complete.return_value = answer("An earlier unsupported assertion.")
        self.ask("Explain RAG")
        self.complete.side_effect = [response({"query": "RAG limitations", "clarification": None}),
            response({"outcome": "answered", "claims": [{"text": "Repeated assertion", "evidence": [
                {"source_id": "S1", "excerpt": "An earlier unsupported assertion."}]}]})]
        with self.assertRaisesRegex(PipelineError, "unknown or inexact caption evidence"):
            self.ask("Is that really true?")
        self.assertEqual(len(self.session.history), 1)


class FollowupAppTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {
            "VIDSAGE_DB": str(Path(directory) / "pilot.sqlite3"),
            "LLM_MODEL": "openai/chat", "LLM_API_KEY": "test-chat",
            "EMBEDDING_MODEL": "openai/embedding", "EMBEDDING_API_KEY": "test-embedding",
        }, clear=True))
        self.enterContext(patch("dotenv.load_dotenv"))
        self.fetch = self.enterContext(patch("youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=
            SimpleNamespace(language_code="en", is_generated=False,
                            snippets=[SimpleNamespace(text=CAPTION, start=4, duration=8)])))
        self.enterContext(patch("llm.litellm.embedding", side_effect=embedding))
        self.complete = self.enterContext(patch("llm.litellm.completion"))
        self.app = AppTest.from_file("main.py", default_timeout=20).run()
        next(w for w in self.app.text_input if w.label == "YouTube Video ID").set_value("dQw4w9WgXcQ")

    def send(self, question, reply, query=None, clarification=None):
        replies = [reply] if query is None and clarification is None else [
            response({"query": query, "clarification": clarification})] + ([reply] if reply else [])
        self.complete.side_effect = replies
        if self.app.chat_input:
            self.app.chat_input[0].set_value(question).run()
        else:
            self.app.text_area[0].set_value(question)
            next(b for b in self.app.button if b.label == "💡 Get Answer").click().run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.error)
        if reply:
            payload = json.loads(self.complete.call_args.kwargs["messages"][-1]["content"])
            self.assertEqual(payload["question"], question)
            return payload

    def test_followups_clarification_and_explicit_topic_change(self):
        self.send("Explain RAG and summaries", answer("1. RAG retrieves passages. 2. Summaries shorten passages."))
        payload = self.send("When does that fail?", answer("Search may miss useful text."), "RAG search limitations")
        self.assertIn("Summaries shorten passages.", payload["history"][0]["answer"])
        payload = self.send("Simplify your second point", answer("Search can miss useful text."), "Search limitations")
        self.assertEqual(len(payload["history"]), 2)
        payload = self.send("Compare those two", response({"outcome": "insufficient_context", "claims": []}),
                            "Compare RAG and summaries")
        self.assertEqual(self.app.session_state["history"][-1]["result"]["outcome"], "insufficient_context")
        self.send("What about the other one?", None, clarification="Do you mean RAG or summaries?")
        self.assertEqual(self.app.session_state["history"][-1]["answer"], "Do you mean RAG or summaries?")
        self.assertTrue(any("Do you mean RAG or summaries?" in item.value for item in self.app.markdown))
        payload = self.send("I mean RAG", answer("Search can miss useful text."), "RAG search limitations")
        self.assertEqual(payload["history"][-1]["answer"], "Do you mean RAG or summaries?")
        payload = self.send("New topic: explain summaries", answer("Summaries shorten passages."), "Explain summaries")
        self.assertEqual(payload["retrieval_query"], "Explain summaries")
        self.assertEqual(self.app.session_state["history"][-1]["answer"], "Summaries shorten passages.")
        self.assertTrue(any("Summaries shorten passages." in item.value for item in self.app.markdown))
        self.fetch.assert_called_once()

    def test_visual_only_and_outside_knowledge_have_evidence_limitation(self):
        self.send("What color is the diagram?", response({"outcome": "insufficient_context", "claims": []}))
        self.assertIn("not contain enough evidence", self.app.session_state["history"][-1]["answer"])
        self.send("Use outside knowledge to tell me the latest RAG benchmark", response({"outcome": "insufficient_context", "claims": []}),
                  "Latest RAG benchmark")
        self.assertFalse(self.app.session_state["history"][-1]["result"]["claims"])


class FollowupEvaluationTests(unittest.TestCase):
    def test_system_comparison_preserves_original_followup_and_context(self):
        from backend.budget import Rate
        from backend.evaluation import experiment
        from backend.store import Store

        source = map_timestamps("dQw4w9WgXcQ", "en", False, [
            {"text": CAPTION, "start": 4, "duration": 8}])
        history = [{"video_id": source.video_id, "question": "Explain RAG", "answer": "RAG retrieves passages."}]
        example = {"id": "followup", "video_id": source.video_id, "source_version": source.source_version,
                   "question": "When does that fail?", "answerable": True,
                   "evidence_sets": [[source.segments[0].id]], "reference": "Search may miss useful text.",
                   "split": "development", "reviewed": True, "reviewer": "fixture author",
                   "category": "followup", "history": history}
        generation = []

        def provider(messages, **kwargs):
            if "standalone search" in messages[0]["content"]:
                return response({"query": "RAG limitations", "clarification": None})
            if "Grade an answer" in messages[0]["content"]:
                return response({key: 1 for key in ("correctness", "support", "completeness", "abstention", "timing")})
            generation.append(json.loads(messages[-1]["content"]))
            return answer("Search may miss useful text.")

        with tempfile.TemporaryDirectory() as directory, patch("llm.litellm.embedding", side_effect=embedding), \
                patch("llm.litellm.completion", side_effect=provider):
            report = experiment([example], {source.source_version: source}, "k8", EMBED, CHAT, CHAT,
                                {c["model"]: Rate(0.01, 0.01) for c in (CHAT, EMBED)},
                                Store(Path(directory) / "pilot.sqlite3"), mode="system")
        self.assertTrue(report["complete"])
        self.assertEqual(len(generation), 2)
        for payload in generation:
            self.assertEqual(payload["question"], "When does that fail?")
            self.assertEqual(payload["retrieval_query"], "RAG limitations")
            self.assertEqual(payload["history"], [{"exchange_number": 1, "question": "Explain RAG", "answer": "RAG retrieves passages."}])
