# VidSage — YouTube Conversational QA Agent

A retrieval-augmented QA assistant that lets you ask natural language questions about a YouTube video.  
VidSage extracts the video transcript, chunks and indexes it (FAISS + Google Generative AI embeddings), then uses a Gemini LLM (via `langchain_google_genai`) to answer questions using the retrieved transcript context. A Streamlit frontend provides video preview, conversation history and export/download utilities. The current prompt also permits answers from general knowledge when context is insufficient; strict transcript grounding is not enforced.

---

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```bash
uv venv --python 3.11
uv sync --locked
```

This creates `.venv` and installs the versions in `uv.lock`. For later installs, `uv sync --locked` is sufficient. Activation is optional; use `source .venv/bin/activate` if desired.

Set `GOOGLE_API_KEY` in the terminal environment using your Google AI Studio key, then start the app:

```bash
export GOOGLE_API_KEY="your-google-ai-studio-key"
uv run --locked streamlit run main.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`. Without an environment key, the current app prompts in the server terminal with `getpass`. A `.env` file is not loaded automatically. Keep credentials out of Git and shared terminal output.

Enter a video ID such as `dQw4w9WgXcQ` and a question. Live Q&A requires an accessible YouTube transcript, a working Google API key, and access to the configured models (`gemini-2.0-flash` and `models/embedding-001`).

## How it runs

All application code is in `main.py`:

1. `fetch_transcript` downloads the transcript, splits it into 1,000-character chunks with 200-character overlap, embeds them, and builds a FAISS index.
2. The retriever selects context for the current question.
3. `our_agent` sends the question and context to Gemini through a two-node LangGraph workflow.
4. Streamlit displays the answer and stores the exchange in session history, with answer/history downloads.

The transcript and index are rebuilt for every question. History is a UI record for the current session; previous exchanges are not supplied to the model as conversation context.

## Validation and known issues

Basic local checks:

```bash
uv pip check
uv run --locked python -m compileall -q main.py
```

Baseline verified on November 24, 2026 with Python 3.11.16 and the existing lockfile:

- All 107 installed packages pass dependency compatibility checks.
- The Streamlit server starts and its health endpoint responds successfully.
- Streamlit `AppTest` checks pass for initialization with a placeholder environment key, empty-input validation, Q&A/history and the history export control with mocked external APIs, and a displayed transcript failure that leaves history unchanged.
- These were temporary smoke checks; no automated test suite is checked in yet. Real YouTube/Google calls and current model availability were not verified because no Google API key was available.

Confirmed issues left for follow-up:

- **Clear Fields** and **Clear History** call `st.experimental_rerun`, which is absent from the pinned Streamlit 1.48.1 and raises `AttributeError`.
- The retriever uses the misspelled `search_kwags` argument. It is ignored, so retrieval currently relies on the default `k=4` rather than the supplied setting.
- The prompt asks for transcript-only answers but also permits general-knowledge fallback when context is insufficient.

See [AGENTS.md](AGENTS.md) for the maintained development, validation, and branch/commit/push workflow.

## 🔍 Project summary (one-liner)

**VidSage** — Retrieval-augmented YouTube Q&A: extract transcripts, index with FAISS + Google embeddings, and answer video questions using a Gemini LLM through a Streamlit UI.

---

## 🚀 Features

- Fetches YouTube transcripts and converts them to searchable chunks.
- Embeds chunks using `GoogleGenerativeAIEmbeddings` and indexes with FAISS for fast retrieval.
- Uses a Gemini-based LLM (via `langchain_google_genai`) to generate context-grounded answers.
- Streamlit frontend with:
  - Video preview (by video ID)
  - Question input & “Get Answer” flow
  - Conversation history persisted in `st.session_state`
  - Downloadable answers & full history

---
