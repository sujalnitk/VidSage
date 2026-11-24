# VidSage — YouTube Conversational QA Agent

A retrieval-augmented QA assistant that lets you ask natural language questions about a YouTube video.  
VidSage extracts the video transcript, chunks and indexes it with your chosen embedding model and FAISS, then answers questions through your chosen chat model. A Streamlit frontend provides video preview, session history, and downloads. The current prompt also permits answers from general knowledge when context is insufficient; strict transcript grounding is not enforced.

---

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```bash
uv venv --python 3.11
uv sync --locked
```

This creates `.venv` and installs the versions in `uv.lock`. For later installs, `uv sync --locked` is sufficient. Activation is optional; use `source .venv/bin/activate` if desired.

Start the app; no API key is required just to open it:

```bash
uv run --locked streamlit run main.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`. Configure models and masked API keys in the **Model settings** sidebar, then enter a video ID such as `dQw4w9WgXcQ` and a question.

## Providers and keys

Chat and embeddings use the [LiteLLM Core SDK](https://docs.litellm.ai/docs/litellm_core). Use a `provider/model` identifier from the [supported providers](https://docs.litellm.ai/docs/providers) rather than guessing the vendor from a key.

| Service | Chat model format | Native environment key |
| --- | --- | --- |
| Google Gemini | `gemini/<model-id>` | `GEMINI_API_KEY` or legacy `GOOGLE_API_KEY` |
| OpenAI | `openai/<model-id>` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/<model-id>` | `ANTHROPIC_API_KEY` |
| Other supported vendors | Provider prefix and model ID from LiteLLM's provider guide | Enter the key in the app; similarly named `<PROVIDER>_API_KEY` variables also work |
| OpenAI-compatible service | `openai/<model-id>` plus its endpoint URL, such as `https://your-service.example/v1` | Enter the service's key in the app |

1. Enter the **Chat model** and its API key. For a native endpoint, a blank key field uses the corresponding server environment key. Environment keys are not copied into the browser field.
2. Choose an **Embedding model** under **Embedding settings**. Google and OpenAI chat routes prefill an editable embedding model; other routes require you to choose one. The embedding model must support the [embeddings endpoint](https://docs.litellm.ai/docs/embedding/supported_embedding).
3. Leave the embedding key blank to share the chat key only when both provider and endpoint match, or enter a separate embedding key. For example, Anthropic chat can use OpenAI embeddings with its own OpenAI key; it does not need a Google key.

Custom endpoint URLs require a key entered in the app, so changing an endpoint cannot redirect a server environment credential. Keys entered in the app remain in the current Streamlit session; they are not written to process environment variables, history, or downloads. Credential values are redacted from displayed processing errors.

`LLM_MODEL` and `EMBEDDING_MODEL` can override the initial model values. Google defaults are `gemini/gemini-3.8-flash` and `gemini/gemini-embedding-001`; the old hardcoded `gemini-2.0-flash` and `embedding-001` are retired according to [Google's model lifecycle table](https://aistudio.google.com/docs/deprecations).

A `.env` file is not loaded automatically. To load an ignored local file explicitly, use `uv run --env-file .env --locked streamlit run main.py`. Keep credentials out of Git and shared terminal output. Some cloud integrations require additional provider-specific authentication or optional SDK packages; a key alone does not configure those services.

## How it runs

`main.py` contains the graph and UI; `llm.py` validates provider configuration and adapts embeddings to LangChain:

1. `fetch_transcript` downloads the transcript, splits it into 1,000-character chunks with 200-character overlap, embeds them, and builds a FAISS index.
2. The retriever selects context for the current question.
3. `our_agent` sends the question and context to the configured chat provider through a two-node LangGraph workflow.
4. Streamlit displays the answer and stores the exchange in session history, with answer/history downloads.

The transcript and index are rebuilt for every question. History is a UI record for the current session; previous exchanges are not supplied to the model as conversation context.

## Validation and known issues

Basic local checks:

```bash
uv pip check
uv run --locked python -m compileall -q main.py llm.py tests
uv run --locked python -m unittest discover -s tests -v
```

The checked-in unittest suite covers startup without credentials, input validation, provider/key/endpoint routing, legacy Google environment support, credential isolation and redaction, mocked Q&A/history, and embedding batching/response ordering. YouTube and model API calls are mocked; these checks do not verify live keys, account permissions, quotas, or model access.

Confirmed issues left for follow-up:

- **Clear Fields** and **Clear History** call `st.experimental_rerun`, which is absent from the pinned Streamlit 1.48.1 and raises `AttributeError`.
- The retriever uses the misspelled `search_kwags` argument. It is ignored, so retrieval currently relies on the default `k=4` rather than the supplied setting.
- The prompt asks for transcript-only answers but also permits general-knowledge fallback when context is insufficient.

See [AGENTS.md](AGENTS.md) for the maintained development, validation, and branch/commit/push workflow.

## 🚀 Features

- Fetches YouTube transcripts and converts them to searchable chunks.
- Embeds chunks using a selectable provider and indexes with FAISS for fast retrieval.
- Uses a selectable chat model with transcript context.
- Streamlit frontend with:
  - Video preview (by video ID)
  - Question input & “Get Answer” flow
  - Conversation history persisted in `st.session_state`
  - Downloadable answers & full history

---
