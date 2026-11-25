import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from llm import LOCAL_EMBEDDING_MODEL, LOCAL_REVISION, ModelEmbeddings, local_model, model_config
from backend.budget import Meter
from backend.evaluation import load_snapshot, preflight
from backend.indexing import build_index, chunk_transcript, embedding_profile
from backend.schemas import CATALOG


def tokenizer(texts, add_special_tokens=True, **kwargs):
    def ids(text):
        return [1] * (len(text) + (2 if add_special_tokens else 0))
    if isinstance(texts, list):
        return {"input_ids": [ids(text) for text in texts]}
    return {"input_ids": ids(texts), "offset_mapping": [(i, i + 1) for i in range(len(texts))]}


class LocalEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.model = SimpleNamespace(tokenizer=tokenizer, max_seq_length=256,
            encode=Mock(side_effect=lambda texts, **kwargs: np.array([[1., 0., 0.] for _ in texts])))
        self.loader = self.enterContext(patch("llm.local_model", return_value=self.model))
        self.remote = self.enterContext(patch("llm.litellm.embedding"))
        self.config = model_config(LOCAL_EMBEDDING_MODEL, "must-not-be-stored")

    def test_local_config_needs_no_key_or_endpoint(self):
        self.assertIsNone(self.config["api_key"])
        with self.assertRaises(ValueError):
            model_config(LOCAL_EMBEDDING_MODEL, "", "https://example.com")
        with self.assertRaises(ValueError):
            model_config("local/unknown", "")

    def test_local_vectors_are_normalized_cached_and_not_charged(self):
        usage, meter = [], Mock()
        adapter = ModelEmbeddings(self.config, meter, usage)
        self.assertEqual(adapter.embed_documents([]), [])
        self.loader.assert_not_called()
        self.assertEqual(adapter.embed_query("short question"), [1., 0., 0.])
        self.model.encode.assert_called_once_with(["short question"])
        self.assertEqual(usage[0]["cost_usd"], 0)
        meter.before.assert_not_called()
        self.remote.assert_not_called()
        profile = embedding_profile(self.config)
        self.assertEqual((profile.revision, profile.normalization), (LOCAL_REVISION, "l2"))

    def test_overlong_queries_fail_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError, "256 tokens"):
            ModelEmbeddings(self.config).embed_query("x" * 255)
        self.model.encode.assert_not_called()

    def test_chunk_splitting_retains_complete_source_coverage(self):
        snapshot = load_snapshot(Path("tests/fixtures/captions.json"))
        chunks = chunk_transcript(snapshot, tokenizer=tokenizer)
        self.assertEqual(chunks, chunk_transcript(snapshot, tokenizer=tokenizer))
        for chunk in chunks:
            self.assertLessEqual(len(tokenizer(chunk.text)["input_ids"]), 256)
        for segment in snapshot.segments:
            positions = {i for chunk in chunks for span in chunk.spans if span.segment_id == segment.id
                         for i in range(span.begin, span.end)}
            self.assertEqual(positions, set(range(len(segment.text))))
        ready = build_index(snapshot, CATALOG["baseline"].chunk_policy, embedding_profile(self.config),
                            ModelEmbeddings(self.config), "session", "conversation")
        self.assertEqual(ready.index.ntotal, len(chunks))

    def test_app_runs_with_only_a_groq_key(self):
        from streamlit.testing.v1 import AppTest
        from test_pipeline import completion
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_MODEL": "groq/openai/gpt-oss-120b", "GROQ_API_KEY": "groq-secret",
            "EMBEDDING_MODEL": LOCAL_EMBEDDING_MODEL, "VIDSAGE_DB": str(Path(directory) / "pilot.sqlite3"),
        }, clear=True), patch("dotenv.load_dotenv"), patch("llm.litellm.completion", side_effect=completion), patch(
            "youtube_transcript_api.YouTubeTranscriptApi.fetch", return_value=SimpleNamespace(
                language_code="en", is_generated=False,
                snippets=[SimpleNamespace(text="Retrieval finds evidence before answering.", start=1., duration=3.)])):
            app = AppTest.from_file("main.py", default_timeout=20).run()
            app.text_input[0].set_value("dQw4w9WgXcQ")
            app.text_area[0].set_value("What does retrieval do?")
            next(b for b in app.button if b.label == "💡 Get Answer").click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(len(app.session_state["history"]), 1)
            self.remote.assert_not_called()

    def test_free_retrieval_preflight_needs_no_local_rate(self):
        snapshot = load_snapshot(Path("tests/fixtures/captions.json"))
        examples = [{"source_version": snapshot.source_version}]
        amount, attempts = preflight(examples, {snapshot.source_version: snapshot}, CATALOG["baseline"],
                                    CATALOG["k8"], self.config, {}, {}, {}, "retrieval")
        self.assertEqual((amount, attempts), (0, 0))
        with self.assertRaises(ValueError):
            Meter({}, -1)
        Meter({}, amount, attempts)


class ModelCacheTests(unittest.TestCase):
    def test_loader_loads_one_pinned_cpu_model(self):
        local_model.cache_clear()
        constructor = Mock(return_value=object())
        try:
            with patch("local_embeddings.MiniLM", constructor):
                self.assertIs(local_model(), local_model())
            constructor.assert_called_once_with(LOCAL_REVISION)
        finally:
            local_model.cache_clear()


class OnnxPoolingTests(unittest.TestCase):
    def test_masked_pooling_normalization_batching_and_order(self):
        from local_embeddings import MiniLM
        model = MiniLM.__new__(MiniLM)
        model._tokenizer = SimpleNamespace(encode_batch=lambda texts: [
            SimpleNamespace(ids=[1, 2] if text == "two" else [3]) for text in texts])
        def run(outputs, inputs):
            ids = inputs["input_ids"]
            return [np.stack([ids, np.ones_like(ids), np.zeros_like(ids)], axis=-1).astype(np.float32)]
        model.session = SimpleNamespace(run=Mock(side_effect=run), get_inputs=lambda: [
            SimpleNamespace(name=n) for n in ("input_ids", "attention_mask", "token_type_ids")])
        texts = ["two", "one"] * 17
        vectors = model.encode(texts)
        self.assertEqual(model.session.run.call_count, 2)
        self.assertEqual(vectors.shape, (34, 3))
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), np.ones(34), atol=1e-6)
        np.testing.assert_allclose(vectors[0], np.array([1.5, 1., 0.]) / np.sqrt(3.25), atol=1e-6)
        np.testing.assert_allclose(vectors[1], np.array([3., 1., 0.]) / np.sqrt(10), atol=1e-6)
