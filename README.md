# VidSage — YouTube Conversational QA Agent

A caption-grounded YouTube Q&A app for a private pilot. VidSage prepares a timestamped FAISS index once per session/video, resolves bounded follow-ups, and returns structured claims with backend-generated timestamp links. Reviewed feedback can become offline regression examples for owner-triggered configuration comparisons.
---

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```bash
uv venv --python 3.11
uv sync --locked
```

This creates `.venv` and installs the versions in `uv.lock`. For later installs, `uv sync --locked` is sufficient. Activation is optional; use `source .venv/bin/activate` if desired.

Copy `.env.example` to `.env` in the repository root, then edit `.env` in your editor to set the server's model and API key. The local `.env` is ignored by Git; `.env.example` is the committed template. Start the app normally:

```bash
uv run --locked streamlit run main.py
```

The app automatically loads the `.env` beside `main.py`; no terminal key entry or extra startup flag is required. Existing deployment environment variables take precedence. Restart Streamlit after changing `.env`.

Open the local URL printed by Streamlit, normally `http://localhost:8501`, then enter a video ID such as `dQw4w9WgXcQ` and a question. Visitors do not enter keys or configure providers in the browser. The app can open before keys are configured; Q&A needs working server credentials.

## Providers and keys

Chat and embeddings use the [LiteLLM Core SDK](https://docs.litellm.ai/docs/litellm_core). Use a `provider/model` identifier from the [supported providers](https://docs.litellm.ai/docs/providers) rather than guessing the vendor from a key.

Set these values in your local `.env`:

| Setting | Purpose |
| --- | --- |
| `LLM_MODEL` | Chat provider/model ID |
| `LLM_API_KEY` | Server's chat API key |
| `LLM_BASE_URL` | Optional custom chat endpoint |
| `EMBEDDING_MODEL` | Provider/model ID for embeddings |
| `EMBEDDING_API_KEY` | Separate embedding key, or blank to share the chat key when provider and endpoint match |
| `EMBEDDING_BASE_URL` | Optional custom embedding endpoint; set both URLs when sharing a custom endpoint |

Native provider key names are also accepted in `.env` or the deployment environment:

| Service | Chat model format | Native key name |
| --- | --- | --- |
| Google Gemini | `gemini/<model-id>` | `GEMINI_API_KEY` or legacy `GOOGLE_API_KEY` |
| OpenAI | `openai/<model-id>` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/<model-id>` | `ANTHROPIC_API_KEY` |
| Other supported vendors | Provider prefix and model ID from LiteLLM's provider guide | Use `LLM_API_KEY`; similarly named `<PROVIDER>_API_KEY` variables also work |
| OpenAI-compatible service | `openai/<model-id>` plus its endpoint URL, such as `https://your-service.example/v1` | Use `LLM_API_KEY` and `LLM_BASE_URL` |

The embedding model must support the [embeddings endpoint](https://docs.litellm.ai/docs/embedding/supported_embedding). For example, configure `LLM_MODEL=anthropic/<model-id>` and `LLM_API_KEY` for Anthropic chat, with `EMBEDDING_MODEL=openai/text-embedding-3-small` and its own `EMBEDDING_API_KEY` for OpenAI embeddings. This setup does not need a Google key.

Models, endpoints, and keys are controlled by the server configuration. Secrets are not copied into browser widgets, history, or downloads, and credential values are redacted from displayed processing errors.

`LLM_MODEL` and `EMBEDDING_MODEL` can override the initial model values. Google defaults are `gemini/gemini-3.8-flash` and `gemini/gemini-embedding-001`; the old hardcoded `gemini-2.0-flash` and `embedding-001` are retired according to [Google's model lifecycle table](https://aistudio.google.com/docs/deprecations).

Keep `.env` local and place the server's own file on each deployment. Some cloud integrations require additional provider-specific authentication or optional SDK packages; a key alone does not configure those services.

## Groq chat configuration

For Groq, use `LLM_MODEL=groq/openai/gpt-oss-120b` and put the Groq key in `LLM_API_KEY` or `GROQ_API_KEY`. Leave `LLM_BASE_URL` blank for the native endpoint. Available models depend on the account; check the [Groq model catalog](https://console.groq.com/docs/models).

Transcript embeddings run locally when `EMBEDDING_MODEL=local/all-MiniLM-L6-v2`. Leave `EMBEDDING_API_KEY` and `EMBEDDING_BASE_URL` blank. The selected setup uses Groq for chat and MiniLM for embeddings; no Google embedding key is needed.

`uv sync --locked` installs ONNX Runtime, Hugging Face Hub and the tokenizer runtime. First use downloads the pinned public model revision (about 91 MB of weights, plus tokenizer/config files) into the normal Hugging Face cache. Dependencies and runtime RAM add overhead beyond the weights. Subsequent runs reuse the cached model, and embedding inference needs no network or API key. The adapter loads one model per application process, serializes its use, uses the ONNX CPU runtime with one inference thread, avoiding the native FAISS/PyTorch conflict observed on M1, batches at 32 texts, and emits normalized 384-dimensional vectors.

MiniLM supports English input up to 256 tokens including special tokens. Preparation splits character windows further using tokenizer offsets when needed, retaining exact source spans/timestamps. Overlong questions fail with a shortening instruction instead of silently losing text. Local embedding usage records zero API cost and consumes no paid-provider attempts; experiments still budget Groq generation/resolution/judging. Hosted embedding configurations remain supported and keep independent credentials.

## How it runs

`main.py` is the Streamlit caller. The Python backend can also run without Streamlit:

| Module | Responsibility |
| --- | --- |
| `backend/schemas.py` | Immutable source, chunk, index, answer, trace and feedback contracts; versioned configuration catalog |
| `backend/ingestion.py` | YouTube URL/ID parsing, language selection, caption fetching and validated timestamp mapping |
| `backend/indexing.py` | Character chunks with source spans, vector checks and atomic session-memory FAISS publication |
| `backend/retrieval.py` | Explicit dense retrieval (`k=4`, candidate `k=8`) and bounded, deduplicated source context |
| `backend/answering.py` | Follow-up resolution, grounded JSON generation, exact-excerpt validation and timestamp links |
| `backend/service.py` | `prepare_video`, `ask_question`, `record_feedback`; ownership, reuse, request deduplication and LangGraph orchestration |
| `backend/store.py` | Local SQLite consent, feedback, reviewed examples, quotas, reports, selected version and rollback |
| `backend/evaluation.py` | Frozen JSONL datasets, retrieval metrics, semantic judging and paired comparisons |
| `llm.py` | Independent provider configuration, hosted embedding validation, and local model caching |
| `local_embeddings.py` | Pinned MiniLM tokenization, ONNX CPU inference, masked mean pooling and normalization |

Preparation preserves caption timing, generated-track status, language and content-derived source identity. Chunks start at 1,000 characters with 200 overlap and shrink to the local model’s token limit when necessary; split captions retain their original available time range. Indexes hold vectors and source mappings, never credential-bearing clients. A second question fetches no captions and embeds no documents. A failed refresh keeps the previous ready artifact for that same video.

Questions run `resolve → retrieve → generate → validate` through LangGraph. The resolver sees the last three same-video turns (bounded to 2,000 characters each). Context is limited to 4,096 UTF-8 bytes as a conservative token bound. Answers must cite exact excerpts from supplied source IDs; unsupported questions produce an insufficient-context result. Structural citation checks cannot establish that the excerpt logically supports the claim; the judge and human review address that separately.

Each conversation has one active video. Switching videos or clearing history starts a new conversation and releases the active index. History is bounded to 20 turns. Duplicate request IDs return one completed result; failed request IDs remain tombstones. Streamlit also suppresses repeated completed submissions with the same inputs. Requests are serialized per session and provider work is limited to two concurrent operations in the application process.

The app opens without credentials. Configuration and secrets stay on the server, outside indexes, browser settings, history, downloads, and retained traces. Provider calls use a 30-second timeout and no automatic paid retries. The caption client uses 15-second HTTP timeouts and one retry for connection/timeouts. Captions are capped at 500,000 characters/30,000 segments; an index at 2,000 chunks; a question at 2,000 characters; a session at 100 question attempts.

## Pilot retention and spending

Retention is opt-in per answer. SQLite retains traces and attributed feedback for 30 days, purged when the store is opened or the cleanup command runs. Human-approved examples remain until deleted. **Delete my retained data** removes that session's traces, feedback, derived examples, regenerates the managed example export and registered experiment datasets, and invalidates retained comparison reports. Independently copied files and backups are outside this managed deletion path. The SQLite file is created with owner-only permissions.

Set `VIDSAGE_PILOT=1` for invited access and point `VIDSAGE_RATE_CARD` at a private, verified rate card based on `eval/rates.example.json`. The example contains placeholders and is rejected until filled in. Rates must cover worst-case billing for the chosen models/endpoints, including reasoning/output charges. Each app submission reserves at most $0.25; the single-process server admits at most 100 submissions and $5 in conservative reservations per UTC day. Unused or unknown-cost reservations are retained. Local development can run without a rate card when pilot mode is off; it still has request/size/concurrency limits.

Experiments require verified rates, preflight both versions including document preparation, query resolution, generation and judging, and reserve the complete maximum attempt cost **before the first provider call**. A complete experiment must fit $5. Unknown prices stop preflight; invalid judge output, provider failure or exhausted reservations produces an incomplete report. Actual cost stays unknown when provider usage/cost is missing. These controls bound planned calls under the verified rate assumptions; provider billing must be checked during the real smoke test.

Use a persistent local volume and one application process for the pilot. Configure daily retention cleanup on the host:

```bash
uv run --locked python -m backend purge
```

## Evaluation and learning

[The evaluation guide](docs/evaluation.md) covers the 60-question review process, first retrieval-only experiment, paired system comparisons, human calibration, selection and rollback. Available owner commands:

```bash
uv run --locked python -m backend --help
uv run --locked python -m backend freeze
uv run --locked python -m backend draft-dataset
```

The six sources are selected from Veritasium in [eval/videos.json](eval/videos.json), with four development videos and two held-out videos. All six English tracks were fetched successfully on this local machine on November 25, 2026. Frozen captions and 60 source-linked, **unreviewed** drafts are in Git-ignored `eval/local/` in this workspace. Six drafts use clearly marked synthetic caption-injection variants. No real provider experiment has run: the real dataset still needs human review and experiments need verified rates. No draft is a gold example until a human reviews it.

Release gates still open: human review of the 60 questions/evidence labels, a real retrieval baseline and system/judge comparison, judge calibration, a hosted caption check, provider smoke test and verification of spend/request limits and daily cleanup on the actual host. A local caption success does not establish hosted reliability.

## Engineering workflow

Matt's engineering skills use local Markdown: specifications live in `.scratch/<feature-slug>/spec.md`, with one numbered ticket per file in `.scratch/<feature-slug>/issues/`. See [issue tracker conventions](docs/agents/issue-tracker.md) and [domain documentation rules](docs/agents/domain.md). You can edit `docs/agents/*.md` directly as the workflow evolves.

## Validation

```bash
uv pip check
uv run --locked python -m compileall -q main.py llm.py local_embeddings.py backend tests
uv run --locked python -m unittest discover -s tests -v
```

The deterministic suite mocks YouTube and LiteLLM. It checks provider isolation, startup/dotenv behavior, timestamp provenance, chunk coverage, vector/index compatibility, context budgets, citations, warm reuse, refresh failures, request deduplication, conversation isolation, consent, retention/deletion, experiment budgets, held-out locking, human review gates, selection and rollback. Streamlit AppTest covers clear/download/feedback controls and repeated submissions. GitHub Actions runs the same checks without provider keys. Tests never read the real local `.env`.

A healthy `/_stcore/health` only proves the server is listening; AppTest verifies script execution separately. See [AGENTS.md](AGENTS.md) for development and Git workflow agreements.
