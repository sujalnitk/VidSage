from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.answering import generate_answer, resolve_query, validate_citations
from backend.evaluation import load_snapshot
from backend.indexing import build_index, chunk_transcript, embedding_profile
from backend.ingestion import fetch_transcript, map_timestamps, parse_video
from backend.retrieval import assemble_context, retrieve
from backend.schemas import AnswerDraft, CATALOG, ChunkPolicy, Claim, Evidence, PipelineError
from backend.service import Session, ask_question, decide_refresh, prepare_video, record_feedback
from backend.store import Store
from llm import ModelEmbeddings

FIXTURE = Path("tests/fixtures/captions.json")
CHAT = {"model": "openai/chat", "api_key": "chat-secret", "api_base": None}
EMBED = {"model": "openai/embedding", "api_key": "embedding-secret", "api_base": None}


def embedding(input, **kwargs):
    return SimpleNamespace(data=[{"index": i, "embedding": [1.0, 0.0, 0.0]} for i in range(len(input))])


def completion(messages, **kwargs):
    if "standalone search" in messages[0]["content"]:
        data = {"query": "How does retrieval augmented generation work?", "clarification": None}
    else:
        sources = json.loads(messages[-1]["content"])["sources"]
        data = {"outcome": "answered", "claims": [{"text": "RAG finds evidence before answering.",
                "evidence": [{"source_id": sources[0]["id"], "excerpt": sources[0]["text"]}]}]}
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))])


class IngestionTests(unittest.TestCase):
    def test_supported_urls_and_rejected_hosts(self):
        for value in ("dQw4w9WgXcQ", " https://youtu.be/dQw4w9WgXcQ?t=1 ",
                      "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=test", "https://m.youtube.com/shorts/dQw4w9WgXcQ",
                      "https://youtube.com/embed/dQw4w9WgXcQ", "https://youtube.com/live/dQw4w9WgXcQ"):
            self.assertEqual(parse_video(value), "dQw4w9WgXcQ")
        for value in ("bad", "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ", "https://evil.test/dQw4w9WgXcQ",
                      "https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ", "https://youtube.com/watch?v=dQw4w9WgXcQ&v=abcdefghijk",
                      "https://youtu.be/dQw4w9WgXcQ/extra", "file:///dQw4w9WgXcQ"):
            with self.subTest(value=value), self.assertRaises(PipelineError):
                parse_video(value)

    def test_source_identity_includes_metadata_text_timing_and_order(self):
        source = load_snapshot(FIXTURE)
        data = json.loads(FIXTURE.read_text())
        again = map_timestamps(data["video_id"], "en", False, data["segments"], "later")
        self.assertEqual(source.source_version, again.source_version)
        self.assertEqual(source.segments, again.segments)
        self.assertLess(source.segments[1].start, source.segments[0].end)  # overlapping captions survive
        self.assertGreater(source.segments[2].start, source.segments[1].end)  # gaps survive
        for key, new in (("text", "Changed"), ("start", 1)):
            rows = [dict(row) for row in data["segments"]]
            rows[0][key] = new
            self.assertNotEqual(source.source_version, map_timestamps(data["video_id"], "en", False, rows).source_version)
        self.assertNotEqual(source.source_version, map_timestamps(data["video_id"], "en-US", True, data["segments"]).source_version)

    def test_empty_invalid_and_out_of_order_captions(self):
        for rows in ([], [{}], [{"text": "", "start": 0, "duration": 1}], [{"text": "x", "start": -1, "duration": 1}],
                     [{"text": "x", "start": float("nan"), "duration": 1}],
                     [{"text": "a", "start": 2, "duration": 1}, {"text": "b", "start": 1, "duration": 1}]):
            with self.subTest(rows=rows), self.assertRaises(PipelineError):
                map_timestamps("dQw4w9WgXcQ", "en", False, rows)

    def test_language_metadata_and_transient_retry(self):
        data = json.loads(FIXTURE.read_text())
        from youtube_transcript_api._transcripts import FetchedTranscriptSnippet
        track = SimpleNamespace(language_code="en-US", is_generated=True,
                                snippets=[FetchedTranscriptSnippet(**row) for row in data["segments"]])
        from requests.exceptions import Timeout
        with patch("backend.ingestion.YouTubeTranscriptApi.fetch", side_effect=[Timeout(), track]) as fetch:
            result = fetch_transcript("dQw4w9WgXcQ", "en-US")
            self.assertEqual(fetch.call_count, 2)
            fetch.assert_called_with("dQw4w9WgXcQ", languages=["en-US"])
            self.assertTrue(result.generated)

    def test_permanent_failure_stops_before_embedding(self):
        from youtube_transcript_api import TranscriptsDisabled
        with patch("backend.ingestion.YouTubeTranscriptApi.fetch", side_effect=TranscriptsDisabled("dQw4w9WgXcQ")) as fetch:
            with patch("llm.litellm.embedding") as embed, self.assertRaisesRegex(PipelineError, "No accessible"):
                prepare_video(Session(), "dQw4w9WgXcQ", EMBED)
            fetch.assert_called_once()
            embed.assert_not_called()


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.source = load_snapshot(FIXTURE)
        self.embed = self.enterContext(patch("llm.litellm.embedding", side_effect=embedding))
        self.prepared = build_index(self.source, ChunkPolicy(100, 20), embedding_profile(EMBED), ModelEmbeddings(EMBED), "s", "c")

    def test_chunks_are_deterministic_with_complete_segment_coverage(self):
        policy = ChunkPolicy(40, 8)
        chunks = chunk_transcript(self.source, policy)
        self.assertEqual(chunks, chunk_transcript(self.source, policy))
        coverage = {s.id: set() for s in self.source.segments}
        for chunk in chunks:
            for span in chunk.spans:
                coverage[span.segment_id].update(range(span.begin, span.end))
            self.assertEqual(chunk.source_version, self.source.source_version)
        for s in self.source.segments:
            self.assertEqual(coverage[s.id], set(range(len(s.text))))
        repeated = self.source.segments[3]
        self.assertGreater(sum(any(s.segment_id == repeated.id for s in c.spans) for c in chunks), 1)
        self.assertTrue(all(c.start <= c.end for c in chunks))
        self.assertNotEqual(chunks[0].id, chunk_transcript(self.source, ChunkPolicy(41, 8))[0].id)

    def test_vectors_mapping_and_profile_mismatch(self):
        self.assertEqual(self.prepared.index.ntotal, len(self.prepared.chunks))
        self.assertNotIn("embedding-secret", str(asdict(self.prepared)))
        self.assertEqual(len(retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile, 4)), 4)
        for model in ("openai/different", "gemini/different"):
            with self.assertRaisesRegex(PipelineError, "embedding profile"):
                retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), replace(self.prepared.profile, model=model))
        with patch("llm.litellm.embedding", return_value=SimpleNamespace(data=[{"index": 0, "embedding": [1.0]}])):
            with self.assertRaisesRegex(PipelineError, "dimensions"):
                retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile)

    def test_context_deduplicates_overlap_and_obeys_budget(self):
        passages = retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile, 8)
        context = assemble_context(passages + passages, self.source, 1000)
        self.assertLessEqual(context.token_upper_bound, 1000)
        for segment in self.source.segments:
            text = "".join(s.text for s in context.sources if s.segment_id == segment.id)
            self.assertLessEqual(len(text), len(segment.text))
        self.assertEqual(len({s.id for s in context.sources}), len(context.sources))
        other = replace(self.source, source_version="other")
        with self.assertRaises(PipelineError):
            assemble_context(passages, other)

    def test_citations_use_exact_sources_and_backend_times(self):
        context = assemble_context(retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile), self.source)
        first = context.sources[0]
        draft = AnswerDraft("answered", (Claim("A claim", (Evidence(first.id, first.text),)),))
        result = validate_citations(draft, context, self.prepared, "r", CATALOG["baseline"].version)
        citation = result.claims[0].citations[0]
        self.assertEqual(citation.start, first.start)
        self.assertEqual(citation.url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s")
        for evidence in (Evidence("UNKNOWN", first.text), Evidence(first.id, "invented"), Evidence(first.id, "")):
            with self.assertRaises(PipelineError):
                validate_citations(AnswerDraft("answered", (Claim("claim", (evidence,)),)), context, self.prepared, "r", "v")

    def test_structured_generation_rejects_malformed_and_abstains(self):
        context = assemble_context(retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile), self.source)
        for payload in ('not-json', '[]', '{"outcome":"answered","claims":[]}', '{"outcome":"insufficient_context","claims":[{}]}'):
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])
            with patch("llm.litellm.completion", return_value=response), self.assertRaises(PipelineError):
                generate_answer("question", context, CHAT)
        with patch("llm.litellm.completion", side_effect=completion) as complete:
            self.assertEqual(generate_answer("question", context, CHAT).outcome, "answered")
            self.assertIn("untrusted data", complete.call_args.kwargs["messages"][0]["content"])
        empty = assemble_context((), self.source)
        self.assertEqual(generate_answer("question", empty, CHAT).outcome, "insufficient_context")

    def test_answer_requests_native_schema_only_when_model_supports_it(self):
        context = assemble_context(retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile), self.source)
        with patch("backend.answering.supports_answer_schema", return_value=True), \
                patch("llm.litellm.completion", side_effect=completion) as complete:
            generate_answer("question", context, CHAT)
        schema = complete.call_args.kwargs["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["required"], ["outcome", "claims"])
        self.assertFalse(schema["additionalProperties"])

        with patch("backend.answering.supports_answer_schema", return_value=False), \
                patch("llm.litellm.completion", side_effect=completion) as complete:
            generate_answer("question", context, CHAT)
        self.assertNotIn("response_format", complete.call_args.kwargs)

    def test_provider_rejecting_schema_fails_once_without_prompt_only_retry(self):
        context = assemble_context(retrieve("evidence", self.prepared, ModelEmbeddings(EMBED), self.prepared.profile), self.source)
        with patch("backend.answering.supports_answer_schema", return_value=True), \
                patch("llm.litellm.completion", side_effect=RuntimeError("unsupported response_format json_schema")) as complete:
            with self.assertRaisesRegex(PipelineError, "Contact the VidSage owner") as error:
                generate_answer("question", context, CHAT)
        self.assertEqual(error.exception.category, "structured_output_unsupported")
        complete.assert_called_once()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.source = load_snapshot(FIXTURE)
        self.fetch = self.enterContext(patch("backend.service.fetch_transcript", return_value=self.source))
        self.embed = self.enterContext(patch("llm.litellm.embedding", side_effect=embedding))
        self.complete = self.enterContext(patch("llm.litellm.completion", side_effect=completion))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.store = Store(Path(directory) / "pilot.sqlite3")
        self.session = Session()
        self.ready = prepare_video(self.session, self.source.video_id, EMBED)

    def ask(self, request_id="r", consent=False):
        return ask_question(self.session, self.ready.id, "What is RAG?", request_id, CHAT, EMBED,
                            consent=consent, store=self.store)

    def test_warm_question_and_index_reuse(self):
        self.ask("one")
        self.ask("two")
        self.fetch.assert_called_once()
        self.assertEqual(len(self.embed.call_args_list), 3)  # documents once, query twice
        again = prepare_video(self.session, self.source.video_id, EMBED)
        self.assertIs(again, self.ready)
        self.assertEqual(len(self.session.history), 2)
        self.assertEqual(self.complete.call_count, 3)  # second question resolves history

    def test_unchanged_refresh_preserves_conversation_without_embedding_documents(self):
        self.ask()
        history = list(self.session.history)
        calls = self.embed.call_count
        refreshed = prepare_video(self.session, self.source.video_id, EMBED, refresh=True)
        self.assertIs(refreshed, self.ready)
        self.assertEqual(self.session.history, history)
        self.assertEqual(self.embed.call_count, calls)

    def test_changed_refresh_is_staged_then_accepted_without_provider_work(self):
        self.ask()
        old_conversation = self.session.conversation_id
        self.fetch.return_value = map_timestamps(self.source.video_id, "en", False, [
            {"text": "New caption evidence", "start": 4, "duration": 3}])
        candidate = prepare_video(self.session, self.source.video_id, EMBED, refresh=True)
        self.assertIs(self.session.prepared, self.ready)
        self.assertEqual(len(self.session.history), 1)
        with self.assertRaisesRegex(PipelineError, "Prepare"):
            ask_question(self.session, candidate.id, "question", "candidate", CHAT, EMBED)
        calls = self.embed.call_count, self.complete.call_count, self.fetch.call_count
        self.assertIs(decide_refresh(self.session, candidate.id, True), candidate)
        self.assertNotEqual(self.session.conversation_id, old_conversation)
        self.assertEqual(self.session.history, [])
        self.assertEqual(calls, (self.embed.call_count, self.complete.call_count, self.fetch.call_count))
        with self.assertRaisesRegex(PipelineError, "Prepare"):
            self.ask("old")
        ask_question(self.session, candidate.id, "new question", "new", CHAT, EMBED)
        self.assertEqual(self.session.history[0]["result"]["prepared_id"], candidate.id)

    def test_refresh_decision_rejects_foreign_and_stale_candidates(self):
        self.fetch.return_value = map_timestamps(self.source.video_id, "en", False, [
            {"text": "New captions", "start": 4, "duration": 3}])
        candidate = prepare_video(self.session, self.source.video_id, EMBED, refresh=True)
        other = Session()
        other.prepared, other.pending_refresh = self.ready, candidate
        other.refresh_base, other.video_id = self.ready, self.source.video_id
        with self.assertRaises(PipelineError):
            decide_refresh(other, candidate.id, True)
        self.session.switch(self.source.video_id)
        with self.assertRaises(PipelineError):
            decide_refresh(self.session, candidate.id, True)

    def test_failed_replacement_embedding_or_validation_preserves_conversation(self):
        self.ask()
        history = list(self.session.history)
        self.fetch.return_value = map_timestamps(self.source.video_id, "en", False, [
            {"text": "Changed captions", "start": 4, "duration": 3}])
        for response in (RuntimeError("temporary embedding failure"), SimpleNamespace(data=[
                {"index": 0, "embedding": [float("nan"), 0, 0]}])):
            with self.subTest(response=type(response).__name__):
                self.embed.side_effect = response if isinstance(response, Exception) else None
                self.embed.return_value = response
                with self.assertRaises((RuntimeError, ValueError, PipelineError)):
                    prepare_video(self.session, self.source.video_id, EMBED, refresh=True)
                self.assertIs(self.session.prepared, self.ready)
                self.assertEqual(self.session.history, history)
                self.assertIsNone(self.session.pending_refresh)
        self.embed.side_effect = embedding
        self.ask("still-usable")

    def test_refresh_cannot_publish_after_conversation_changes_during_embedding(self):
        self.fetch.return_value = map_timestamps(self.source.video_id, "en", False, [
            {"text": "Changed captions", "start": 4, "duration": 3}])
        def switch_during_embedding(**kwargs):
            self.session.switch("abcdefghijk")
            return embedding(**kwargs)
        self.embed.side_effect = switch_during_embedding
        with self.assertRaisesRegex(PipelineError, "changed during"):
            prepare_video(self.session, self.source.video_id, EMBED, refresh=True)
        self.assertEqual(self.session.video_id, "abcdefghijk")
        self.assertIsNone(self.session.prepared)
        self.assertIsNone(self.session.pending_refresh)

    def test_retained_context_stays_bounded_without_renumbering_and_resets_on_switch(self):
        for i in range(22):
            self.ask(str(i))
        self.assertEqual([turn["exchange_number"] for turn in self.session.history], list(range(3, 23)))
        for call in self.complete.call_args_list:
            payload = json.loads(call.kwargs["messages"][-1]["content"])
            self.assertLessEqual(len(payload["history"]), 20)
        self.assertEqual(self.session.removed_exchanges, 2)
        self.ask("21")  # Duplicate delivery does not prune another exchange.
        self.assertEqual(self.session.removed_exchanges, 2)
        self.session.switch(self.source.video_id)
        self.ready = prepare_video(self.session, self.source.video_id, EMBED)
        self.ask("fresh")
        self.assertEqual(self.session.history[0]["exchange_number"], 1)
        self.assertEqual(self.session.removed_exchanges, 0)

    def test_failed_refresh_preserves_ready_index(self):
        self.fetch.side_effect = RuntimeError("temporary")
        with self.assertRaises(RuntimeError):
            prepare_video(self.session, self.source.video_id, EMBED, refresh=True)
        self.assertIs(self.session.prepared, self.ready)
        self.ask()

    def test_duplicate_requests_and_concurrent_submission(self):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.ask("same"), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.session.history), 1)
        self.assertEqual(self.complete.call_count, 1)
        with self.assertRaisesRegex(PipelineError, "already used"):
            ask_question(self.session, self.ready.id, "different", "same", CHAT, EMBED)

    def test_failed_request_is_not_rebilled_on_retry(self):
        self.complete.side_effect = RuntimeError("provider error")
        with self.assertRaises(RuntimeError):
            self.ask()
        with self.assertRaisesRegex(PipelineError, "already failed"):
            self.ask()
        self.assertEqual(self.complete.call_count, 1)
        self.assertEqual(self.session.history, [])

    def test_explicit_new_attempt_preserves_completed_exchange_and_reuses_success(self):
        first = self.ask("first")
        self.complete.side_effect = RuntimeError("temporary provider failure")
        with self.assertRaises(RuntimeError):
            self.ask("failed")
        self.assertIs(self.session.prepared, self.ready)
        self.assertEqual([turn["request_id"] for turn in self.session.history], ["first"])
        self.complete.side_effect = completion
        retried = self.ask("explicit-retry")
        calls = self.complete.call_count
        self.assertEqual(self.ask("explicit-retry"), retried)
        self.assertEqual(self.ask("first"), first)
        self.assertEqual(self.complete.call_count, calls)
        self.assertEqual([turn["request_id"] for turn in self.session.history], ["first", "explicit-retry"])

    def test_failed_new_attempts_exhaust_session_request_limit(self):
        self.ask("first")
        self.complete.side_effect = RuntimeError("temporary provider failure")
        for attempt in range(99):
            with self.assertRaises(RuntimeError):
                self.ask(f"failed-{attempt}")
        calls = self.complete.call_count
        with self.assertRaisesRegex(PipelineError, "100-question limit"):
            self.ask("explicit-retry")
        self.assertEqual(self.complete.call_count, calls)
        self.assertIs(self.session.prepared, self.ready)
        self.assertEqual([turn["request_id"] for turn in self.session.history], ["first"])

    def test_video_session_isolation_and_stale_answers(self):
        other = Session()
        with self.assertRaisesRegex(PipelineError, "Prepare"):
            ask_question(other, self.ready.id, "question", "other", CHAT, EMBED)
        def switch(messages, **kwargs):
            self.session.switch("abcdefghijk")
            return completion(messages, **kwargs)
        self.complete.side_effect = switch
        with self.assertRaisesRegex(PipelineError, "active video changed"):
            self.ask()
        self.assertEqual(self.session.history, [])
        self.assertIsNone(self.session.prepared)

    def test_clear_during_answer_rejects_stale_result_even_for_same_video(self):
        original_conversation = self.session.conversation_id
        def clear(messages, **kwargs):
            self.session.switch(self.source.video_id)
            return completion(messages, **kwargs)
        self.complete.side_effect = clear
        with self.assertRaisesRegex(PipelineError, "active video changed"):
            self.ask("stale-after-clear")
        self.assertEqual(self.session.history, [])
        self.assertNotEqual(self.session.conversation_id, original_conversation)
        self.complete.side_effect = completion
        self.ready = prepare_video(self.session, self.source.video_id, EMBED)
        with self.assertRaisesRegex(PipelineError, "already used"):
            self.ask("stale-after-clear")
        self.ask("fresh-after-clear")
        self.assertEqual([turn["request_id"] for turn in self.session.history], ["fresh-after-clear"])

    def test_consent_feedback_attribution_and_credential_isolation(self):
        self.ask("private")
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM traces").fetchone()[0], 0)
        self.ask("retained", True)
        record_feedback(self.session, "retained", "unhelpful", "wrong_passage", True, self.store)
        record_feedback(self.session, "retained", "helpful", "helpful", True, self.store)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM feedback").fetchone()[0], 1)
            payload = db.execute("SELECT payload FROM traces").fetchone()[0]
            self.assertNotIn("chat-secret", payload)
            self.assertNotIn("embedding-secret", payload)
        with self.assertRaises(PipelineError):
            record_feedback(self.session, "private", "helpful", "helpful", True, self.store)
        self.assertNotIn("secret", str(self.session))

    def test_storage_failure_does_not_commit_turn(self):
        with patch.object(self.store, "save_trace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(PipelineError, "could not be retained"):
                self.ask(consent=True)
        self.assertEqual(self.session.history, [])

    def test_ambiguous_followup_returns_clarification(self):
        self.ask("first")
        payload = json.dumps({"query": None, "clarification": "Which method do you mean?"})
        self.complete.side_effect = None
        self.complete.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])
        self.assertEqual(self.ask("second").outcome, "clarification")
        self.assertEqual(len(self.embed.call_args_list), 2)  # documents, first query
