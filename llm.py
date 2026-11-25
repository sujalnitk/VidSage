import os
import math
from urllib.parse import urlsplit
from functools import lru_cache
from threading import RLock

import litellm
from langchain_core.embeddings import Embeddings

litellm.suppress_debug_info = True

LOCAL_EMBEDDING_MODEL = "local/all-MiniLM-L6-v2"
LOCAL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
_LOCAL_LOCK = RLock()


@lru_cache(maxsize=1)
def local_model():
    from local_embeddings import MiniLM
    return MiniLM(LOCAL_REVISION)


def model_config(model: str, api_key: str, base_url: str = "") -> dict:
    model, api_key, base_url = model.strip(), api_key.strip(), base_url.strip()
    provider, separator, name = model.partition("/")
    if not separator or not provider or not name.strip():
        raise ValueError("Use a model name in provider/model format.")
    if base_url:
        url = urlsplit(base_url)
        if (url.scheme not in ("http", "https") or not url.hostname
                or url.username or url.password or url.query or url.fragment):
            raise ValueError("Endpoint URL must be an HTTP(S) URL without credentials, query, or fragment.")
    if provider == "local":
        if model != LOCAL_EMBEDDING_MODEL or base_url:
            raise ValueError("Use local/all-MiniLM-L6-v2 without an endpoint for local embeddings.")
        return {"model": model, "api_key": None, "api_base": None}
    api_key = api_key or os.getenv(f"{provider.upper()}_API_KEY", "").strip()
    if provider == "gemini":
        api_key = api_key or os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ValueError(f"Configure an API key for {provider} in the server's .env file.")
    return {"model": model, "api_key": api_key, "api_base": base_url or None}


class ModelEmbeddings(Embeddings):
    def __init__(self, config: dict, meter=None, usage=None):
        self.config = config
        self.meter = meter
        self.usage = usage

    @property
    def tokenizer(self):
        if self.config["model"] == LOCAL_EMBEDDING_MODEL:
            with _LOCAL_LOCK:
                return local_model().tokenizer
        return None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.config["model"] == LOCAL_EMBEDDING_MODEL:
            if not texts:
                return []
            with _LOCAL_LOCK:
                model = local_model()
                lengths = model.tokenizer(texts, truncation=False, padding=False)["input_ids"]
                if any(len(tokens) > model.max_seq_length for tokens in lengths):
                    raise ValueError("MiniLM input exceeds 256 tokens. Shorten the question or split the document.")
                vectors = model.encode(texts).tolist()
            if self.usage is not None:
                self.usage.append({"kind": "embedding", "model": LOCAL_EMBEDDING_MODEL,
                                   "prompt_tokens": sum(map(len, lengths)), "cost_usd": 0.0})
            return vectors
        vectors = []
        dimension = None
        # Keep batches within Cohere's 96-input limit and Google's 100-input limit.
        for start in range(0, len(texts), 96):
            batch = texts[start:start + 96]
            if self.meter:
                self.meter.before("embedding", self.config["model"], sum(len(t.encode()) + 16 for t in batch))
            response = litellm.embedding(input=batch, timeout=30, num_retries=0, **self.config)
            if self.usage is not None:
                usage = getattr(response, "usage", None)
                cost = getattr(response, "_hidden_params", {}).get("response_cost")
                self.usage.append({"kind": "embedding", "model": self.config["model"],
                                   "prompt_tokens": getattr(usage, "prompt_tokens", None),
                                   "cost_usd": cost if type(cost) in (int, float) and math.isfinite(cost) else None})
            try:
                data = sorted(response.data, key=lambda item: item["index"])
                valid_indexes = (all(type(item["index"]) is int for item in data)
                                 and [item["index"] for item in data] == list(range(len(batch))))
            except (AttributeError, KeyError, TypeError):
                valid_indexes = False
            if not valid_indexes:
                raise ValueError("The embedding provider returned incomplete or invalid vectors.")
            for item in data:
                vector = item.get("embedding")
                if (not isinstance(vector, list) or not vector
                        or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)
                        or (dimension is not None and len(vector) != dimension)):
                    raise ValueError("The embedding provider returned incomplete or invalid vectors.")
                dimension = len(vector)
                vectors.append(vector)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def server_configs():
    chat_model = os.getenv("LLM_MODEL", "gemini/gemini-3.8-flash").strip()
    chat = model_config(chat_model, os.getenv("LLM_API_KEY", ""), os.getenv("LLM_BASE_URL", ""))
    provider = chat_model.partition("/")[0]
    default = {"gemini": "gemini/gemini-embedding-001", "openai": "openai/text-embedding-3-small"}.get(provider, "")
    model = os.getenv("EMBEDDING_MODEL", default).strip()
    endpoint = os.getenv("EMBEDDING_BASE_URL", "").strip()
    shared = chat["api_key"] if model.partition("/")[0] == provider and endpoint == (chat["api_base"] or "") else ""
    if model == LOCAL_EMBEDDING_MODEL:
        return chat, model_config(model, "", endpoint)
    embedding = model_config(model, os.getenv("EMBEDDING_API_KEY", "").strip() or shared, endpoint)
    return chat, embedding
