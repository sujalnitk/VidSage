import os
from urllib.parse import urlsplit

import litellm
from langchain_core.embeddings import Embeddings

litellm.suppress_debug_info = True


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
    else:
        api_key = api_key or os.getenv(f"{provider.upper()}_API_KEY", "").strip()
        if provider == "gemini":
            api_key = api_key or os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ValueError(f"Enter an API key for {provider}. Custom endpoints require a key entered in the app.")
    return {"model": model, "api_key": api_key, "api_base": base_url or None}


class ModelEmbeddings(Embeddings):
    def __init__(self, config: dict):
        self.config = config

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        # Keep batches within Cohere's 96-input limit and Google's 100-input limit.
        for start in range(0, len(texts), 96):
            batch = texts[start:start + 96]
            response = litellm.embedding(input=batch, **self.config)
            data = sorted(response.data, key=lambda item: item["index"])
            if [item["index"] for item in data] != list(range(len(batch))):
                raise ValueError("The embedding provider returned incomplete or invalid vectors.")
            vectors.extend(item["embedding"] for item in data)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
