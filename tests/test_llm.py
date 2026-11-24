import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm import ModelEmbeddings, model_config


class ModelConfigTests(unittest.TestCase):
    def test_routes_keys_to_each_provider_without_mutating_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            for provider in ("gemini", "openai", "anthropic", "groq", "openrouter"):
                with self.subTest(provider=provider):
                    config = model_config(f" {provider}/test-model ", " session-key ")
                    self.assertEqual(config, {
                        "model": f"{provider}/test-model", "api_key": "session-key", "api_base": None,
                    })
            self.assertEqual(dict(os.environ), {})

    def test_native_environment_keys_and_legacy_google_key(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "google-key", "OPENAI_API_KEY": "openai-key"}, clear=True):
            self.assertEqual(model_config("gemini/test", "")["api_key"], "google-key")
            self.assertEqual(model_config("openai/test", "")["api_key"], "openai-key")
            self.assertEqual(model_config("openai/test", "typed-key")["api_key"], "typed-key")
            with self.assertRaisesRegex(ValueError, "Configure an API key for anthropic"):
                model_config("anthropic/test", "")

    def test_server_custom_endpoint_uses_configured_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "server-key"}, clear=True):
            self.assertEqual(model_config("openai/test", "", "https://custom.example/v1")["api_key"], "server-key")
            config = model_config("openai/test", "custom-key", "https://custom.example/v1")
            self.assertEqual(config["api_key"], "custom-key")
            self.assertEqual(config["api_base"], "https://custom.example/v1")

    def test_rejects_missing_models_and_invalid_endpoints(self):
        for model in ("", "model-without-provider", "/model", "openai/"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                model_config(model, "key")
        for url in ("example.com", "file:///tmp/test", "https://user:key@example.com", "https://example.com?key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                model_config("openai/test", "key", url)


class EmbeddingTests(unittest.TestCase):
    def test_batches_and_preserves_input_order(self):
        config = model_config("openai/test-embeddings", "embedding-key")
        def embed(input, **kwargs):
            self.assertEqual(kwargs, config)
            return SimpleNamespace(data=[
                {"index": i, "embedding": [float(text)]} for i, text in reversed(list(enumerate(input)))
            ])
        with patch("llm.litellm.embedding", side_effect=embed) as call:
            result = ModelEmbeddings(config).embed_documents([str(i) for i in range(100)])
            self.assertEqual(result, [[float(i)] for i in range(100)])
            self.assertEqual([len(args.kwargs["input"]) for args in call.call_args_list], [96, 4])

    def test_query_and_empty_input(self):
        config = model_config("gemini/test-embedding", "key")
        with patch("llm.litellm.embedding", return_value=SimpleNamespace(data=[{"index": 0, "embedding": [1.0]}])) as call:
            embeddings = ModelEmbeddings(config)
            self.assertEqual(embeddings.embed_documents([]), [])
            call.assert_not_called()
            self.assertEqual(embeddings.embed_query("question"), [1.0])
            call.assert_called_once_with(input=["question"], **config)

    def test_rejects_incomplete_embedding_responses(self):
        with patch("llm.litellm.embedding", return_value=SimpleNamespace(data=[])):
            with self.assertRaisesRegex(ValueError, "invalid vectors"):
                ModelEmbeddings(model_config("openai/test", "key")).embed_documents(["text"])
