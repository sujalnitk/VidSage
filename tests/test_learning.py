from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.budget import Meter, Rate, load_rates
from backend.evaluation import experiment, load_dataset, load_snapshot, retrieval_metrics, validate_example
from backend.schemas import CATALOG, FeedbackEvent, PipelineError, RetrievedPassage, RunTrace
from backend.indexing import chunk_transcript
from backend.store import Store
from test_pipeline import CHAT, EMBED, FIXTURE, completion, embedding


def example(source, split="development", identifier="one"):
    return {"id": identifier, "video_id": source.video_id, "source_version": source.source_version,
            "question": "What is RAG?", "answerable": True, "evidence_sets": [[source.segments[0].id]],
            "reference": "RAG finds evidence before answering.", "split": split, "reviewed": True,
            "reviewer": "fixture author", "category": "direct_fact"}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.store = Store(Path(self.directory) / "pilot.sqlite3")
        self.source = load_snapshot(FIXTURE)

    def trace(self, identifier="r", age=0):
        return RunTrace(identifier, "s", "c", "p", (datetime.now(timezone.utc) - timedelta(days=age)).isoformat(),
                        {"source_version": self.source.source_version, "question": "What is RAG?", "secret": "private-key"}, {}, ())

    def test_reviewed_examples_retention_deletion_and_redaction(self):
        self.store.save_trace(self.trace(), ["private-key"])
        self.store.record_feedback(FeedbackEvent("r", "s", "unhelpful", "wrong_passage", True))
        approved_id = self.store.approve_example("r", example(self.source), "Sujal", self.source)
        self.store.export_examples()
        registered = Path(self.directory) / "reviewed.jsonl"
        with self.store.connect() as db:
            registered.write_text(db.execute("SELECT payload FROM examples").fetchone()[0] + "\n")
        self.store.register_dataset(registered)
        export = Path(self.directory) / "datasets/approved.jsonl"
        self.assertTrue(json.loads(export.read_text())["reviewed"])
        self.store.purge(datetime.now(timezone.utc) + timedelta(days=31))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM traces").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT request_id FROM examples").fetchone()[0], None)
            self.assertEqual(db.execute("SELECT count(*) FROM examples").fetchone()[0], 1)
        self.store.delete_session("s")
        self.assertEqual(export.read_text(), "")
        self.assertEqual(registered.read_text(), "")
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM examples").fetchone()[0], 0)

    def test_feedback_requires_consent_and_ownership(self):
        self.store.save_trace(self.trace())
        for event in (FeedbackEvent("r", "s", "helpful", "helpful", False),
                      FeedbackEvent("r", "other", "helpful", "helpful", True),
                      FeedbackEvent("unknown", "s", "helpful", "helpful", True)):
            with self.assertRaises(PipelineError):
                self.store.record_feedback(event)
        with self.assertRaises(ValueError):
            self.store.approve_example("r", example(self.source), "Sujal", self.source)

    def test_retained_request_ids_cannot_collide_across_sessions(self):
        self.store.save_trace(self.trace())
        with self.assertRaisesRegex(PipelineError, "another session"):
            self.store.save_trace(replace(self.trace(), session_id="other"))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT session_id FROM traces").fetchone()[0], "s")

    def test_old_traces_expire_and_duplicate_feedback_updates(self):
        self.store.save_trace(self.trace("old", 31))
        self.store.save_trace(self.trace())
        self.store.purge()
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM traces").fetchone()[0], 1)
        for rating, reason in (("unhelpful", "wrong_passage"), ("helpful", "helpful")):
            self.store.record_feedback(FeedbackEvent("r", "s", rating, reason, True))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT * FROM feedback").fetchall(), [("r", "helpful", "helpful")])

    def test_selection_requires_reviewed_heldout_system_report_and_can_rollback(self):
        for mode, phase, human in (("retrieval", "heldout", True), ("system", "development", True), ("system", "heldout", False)):
            report = {"id": mode + phase + str(human), "candidate": "k8", "recommendation": True, "complete": True,
                      "mode": mode, "phase": phase, "human_reviewed": human, "release_dataset_verified": True}
            self.store.save_report(report)
            with self.assertRaises(ValueError):
                self.store.select("k8", report["id"])
        report = {**report, "id": "passing", "human_reviewed": True}
        self.store.save_report(report)
        self.store.select("k8", "passing")
        self.assertEqual(self.store.selected(), CATALOG["k8"])
        self.assertEqual(self.store.rollback(), CATALOG["baseline"])

    def test_daily_spend_and_request_reservations_are_atomic(self):
        self.store.reserve(2)
        self.store.reserve(2)
        with self.assertRaises(PipelineError):
            self.store.reserve(2)
        with self.assertRaises(PipelineError):
            self.store.reserve(0, attempt_limit=2)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.store = Store(Path(self.directory) / "pilot.sqlite3")
        self.source = load_snapshot(FIXTURE)
        self.examples = [example(self.source)]
        self.sources = {self.source.source_version: self.source}
        self.rates = {c["model"]: Rate(0.01, 0.01) for c in (CHAT, EMBED)}
        self.embed = self.enterContext(patch("llm.litellm.embedding", side_effect=embedding))
        self.complete = self.enterContext(patch("llm.litellm.completion", side_effect=completion))

    def run_experiment(self, **kwargs):
        return experiment(self.examples, self.sources, "k8", EMBED, CHAT, CHAT, self.rates, self.store, **kwargs)

    def test_evidence_metrics_distinguish_recall_ranking_and_multi_passage_coverage(self):
        chunks = chunk_transcript(self.source)
        passage = RetrievedPassage(chunks[0], 2, 0, "p")
        metrics = retrieval_metrics([passage], self.examples[0])
        self.assertEqual(metrics["reciprocal_rank"], 0.5)
        missing = {**self.examples[0], "evidence_sets": [[self.source.segments[0].id], ["missing"]]}
        self.assertEqual(retrieval_metrics([passage], missing)["evidence_set_coverage"], 0.5)
        self.assertEqual(retrieval_metrics([], self.examples[0])["recall_at_k"], 0)

    def test_dataset_rejects_unreviewed_source_mismatch_and_split_leakage(self):
        for updates in ({"reviewed": False}, {"reviewer": ""}, {"source_version": "wrong"}, {"evidence_sets": [["unknown"]]}):
            with self.assertRaises(ValueError):
                validate_example({**self.examples[0], **updates}, self.source)
        path = Path(self.directory) / "set.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in [self.examples[0], example(self.source, "heldout", "two")]))
        with self.assertRaisesRegex(ValueError, "disjoint"):
            load_dataset(path, self.sources)

    def test_retrieval_only_runs_without_generation_and_freezes_versions(self):
        report = self.run_experiment()
        self.assertTrue(report["complete"])
        self.complete.assert_not_called()
        self.assertEqual(report["candidate"], "k8")
        self.assertIsNotNone(report["dataset_version"])
        self.assertIsNone(report["actual_cost_usd"])
        self.assertFalse(report["recommendation"])

    def test_over_budget_or_unknown_price_preflight_makes_no_provider_calls(self):
        for rates in ({}, {c["model"]: Rate(10000, 10000) for c in (CHAT, EMBED)}):
            with self.assertRaises(ValueError):
                experiment(self.examples, self.sources, "k8", EMBED, CHAT, CHAT, rates, self.store)
        self.embed.assert_not_called()
        self.complete.assert_not_called()

    def test_invalid_judge_marks_comparison_incomplete(self):
        def invalid(messages, **kwargs):
            if "Grade an answer" in messages[0]["content"]:
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"support":"yes"}'))])
            return completion(messages, **kwargs)
        self.complete.side_effect = invalid
        report = self.run_experiment(mode="system")
        self.assertFalse(report["complete"])
        self.assertFalse(report["recommendation"])
        self.assertEqual(report["failure_category"], "incomplete_comparison")

    def test_candidate_must_be_locked_before_heldout_run(self):
        heldout = replace(self.source, video_id="abcdefghijk", source_version="heldout-source")
        self.examples.append(example(heldout, "heldout", "heldout"))
        self.sources[heldout.source_version] = heldout
        with self.assertRaisesRegex(ValueError, "Lock"):
            self.run_experiment(phase="heldout")
        self.embed.assert_not_called()
        locked = self.run_experiment()
        report = self.run_experiment(phase="heldout", locked_report=locked)
        self.assertTrue(report["complete"])
        changed = {**locked, "signature": "changed"}
        with self.assertRaises(ValueError):
            self.run_experiment(phase="heldout", locked_report=changed)

    def test_attempt_limit_applies_even_to_free_models(self):
        meter = Meter({"free": Rate(0)}, 0.01, max_attempts=1)
        meter.before("embedding", "free", 1)
        with self.assertRaisesRegex(PipelineError, "attempts"):
            meter.before("embedding", "free", 1)

    def test_runtime_reservation_prevents_extra_attempts(self):
        meter = Meter({"model": Rate(1, 1)}, 0.01)
        meter.before("embedding", "model", 10000)
        with self.assertRaises(PipelineError):
            meter.before("chat", "model", 1, 1)
        with self.assertRaises(PipelineError):
            meter.before("chat", "unknown", 1, 1)

    def test_reviewed_failure_can_improve_pass_heldout_and_be_selected(self):
        from backend.ingestion import map_timestamps
        categories = ["direct_fact", "paraphrase", "exact_term", "multi_passage", "followup", "unavailable", "caption_instructions", "direct_fact", "direct_fact", "direct_fact"]
        sources, examples = {}, []
        raw = json.loads(FIXTURE.read_text())["segments"]
        for n in range(6):
            source = map_timestamps(f"fixture{n:04d}", "en", False, raw)
            sources[source.source_version] = source
            for i, category in enumerate(categories):
                e = example(source, "development" if n < 4 else "heldout", f"{n}-{i}")
                e["category"] = category
                if category == "followup":
                    e["history"] = [{"video_id": source.video_id, "question": "What is RAG?", "answer": "RAG finds evidence."}]
                if category == "unavailable":
                    e.update(question="What is the private password?", answerable=False, evidence_sets=[], reference="Abstain")
                examples.append(e)
        first = examples[0]
        trace = RunTrace("failure", "tester", "conversation", "baseline", datetime.now(timezone.utc).isoformat(),
                         {"source_version": first["source_version"], "question": first["question"]}, {}, ())
        self.store.save_trace(trace)
        self.store.record_feedback(FeedbackEvent("failure", "tester", "unhelpful", "incomplete_answer", True))
        approved = self.store.approve_example("failure", first, "fixture reviewer", sources[first["source_version"]])
        with self.store.connect() as db:
            examples[0] = json.loads(db.execute("SELECT payload FROM examples WHERE id=?", (approved,)).fetchone()[0])
        def provider(messages, **kwargs):
            system = messages[0]["content"]
            if "standalone search" in system:
                payload = {"query": "What is RAG?", "clarification": None}
            elif "Grade an answer" in system:
                supplied = json.loads(messages[-1]["content"])
                correct = (supplied["result"]["outcome"] == "answered") == supplied["answerable"]
                payload = {k: float(correct) for k in ("correctness", "support", "completeness", "abstention", "timing")}
            else:
                supplied = json.loads(messages[-1]["content"])
                if "First check whether" in system and "password" not in supplied["question"]:
                    return completion(messages, **kwargs)
                payload = {"outcome": "insufficient_context", "claims": []}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        self.complete.side_effect = provider
        development = experiment(examples, sources, "prompt-v2", EMBED, CHAT, CHAT, self.rates, self.store, mode="system")
        self.assertTrue(development["complete"])
        self.assertTrue(development["reviewed_failure_improved"])
        self.assertTrue(development["recommendation"])
        locked = self.store.review_report(development["id"], "fixture reviewer")
        heldout = experiment(examples, sources, "prompt-v2", EMBED, CHAT, CHAT, self.rates, self.store,
                             mode="system", phase="heldout", locked_report=locked)
        self.assertTrue(heldout["complete"])
        self.assertTrue(heldout["recommendation"])
        with self.assertRaises(ValueError):
            self.store.select("prompt-v2", heldout["id"])
        self.store.review_report(heldout["id"], "fixture reviewer")
        self.store.select("prompt-v2", heldout["id"])
        self.assertEqual(self.store.selected().name, "prompt-v2")
        self.assertEqual(self.store.rollback().name, "baseline")
