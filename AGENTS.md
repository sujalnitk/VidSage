# VidSage agent instructions

## Scope and maintenance

- These instructions apply to the whole repository. Keep one root `AGENTS.md` while the app remains this small; add a nested file only when a directory needs different rules.
- Update this file and the README when verified setup commands, architecture, validation, or working agreements change. Remove resolved limitations instead of accumulating session logs.
- Make the smallest complete change. Reuse the current structure and installed dependencies; avoid speculative features, abstractions, or broad dependency upgrades.
- Read the affected code and search its callers before editing. Preserve unrelated working-tree changes.

## Project map

- `main.py` contains chronological Streamlit chat, submission identity, answer/citation display, session controls, and feedback consent. It calls the backend; no model settings are exposed to visitors.
- `backend/schemas.py` defines shared immutable contracts and the allowlisted configuration catalog. `backend/ingestion.py`, `indexing.py`, `retrieval.py`, and `answering.py` contain independently testable stages.
- `backend/service.py` exposes `prepare_video`, `ask_question`, and `record_feedback`. Its question graph is `START -> resolve -> retrieve -> generate -> validate -> END`. Generation preserves the original message and bounded same-video context alongside the retrieval query; prior replies never count as caption evidence.
- `backend/store.py` owns SQLite retention, reviewed examples, quotas, comparison reports, selection, and rollback. `backend/evaluation.py` and `python -m backend` implement owner-triggered experiments. See `docs/evaluation.md` for the workflow and remaining release gates.
- `local_embeddings.py` runs pinned MiniLM with ONNX Runtime; `llm.py` lazily caches the CPU model for `local/all-MiniLM-L6-v2` (no key/endpoint); local chunks must stay within 256 tokens with their original source spans preserved. Local usage has zero API cost and is excluded from paid reservations.
- `llm.py` validates independent model/credential/endpoint settings and adapts LiteLLM embeddings. `litellm-core` supplies chat and embeddings; do not install the overlapping `litellm` distribution.
- FAISS indexes live in one session/conversation, hold no credential-bearing adapter, and are reused across questions. Publication is atomic; a failed same-video refresh preserves the ready index. History is limited to 20 turns; the resolver sees three bounded same-video turns.
- `pyproject.toml` declares dependencies; `uv.lock` pins them; `.python-version` selects Python 3.11. Reuse installed packages and the standard library.
- `eval/videos.json` selects six Veritasium sources. Real captions/datasets/reports and SQLite belong only in Git-ignored `eval/local/` and `.vidsage/`; committed fixtures are synthetic. Human review is required for reference examples and changed judge outcomes.
- The README records verified setup, architecture, limits, and unresolved release gates. `docs/product-design.md` is product context; `docs/backend-pipeline-plan.md` describes the implemented boundaries and pending validation.

## Environment and secrets

- Use uv and the repository's `.venv`; do not install project dependencies globally or create a second environment.
- Initial setup: `uv venv --python 3.11`, then `uv sync --locked`. For an existing environment, run `uv sync --locked`.
- Run through uv: `uv run --locked streamlit run main.py`. Activation is optional: `source .venv/bin/activate`.
- The server owns models, endpoints, and credentials. Automatically load the repository-local `.env` beside `main.py` with python-dotenv and `override=False`; deployment environment variables take precedence. Do not ask visitors for keys or expose provider settings in browser controls.
- `.env.example` is the committed blank template; the real `.env` stays local and ignored. Preserve an existing `.env` when setting up or updating the app. Restart the server after editing its configuration.
- The app must open without credentials. Pass server keys per request and keep them out of browser widgets, history, downloads, shared caches, and logs.
- Models use `provider/model` names. Chat and embedding models/keys/endpoints are independent. Share a key only when their provider and endpoint match; preserve that boundary when extending provider support.
- Configure chat through `LLM_MODEL`, `LLM_API_KEY`, and optional `LLM_BASE_URL`; configure embeddings through the corresponding `EMBEDDING_*` settings. Native `<PROVIDER>_API_KEY` variables and legacy `GOOGLE_API_KEY` remain supported. Endpoint URLs are server-controlled.
- Never print or commit credentials, `.env` files, `.streamlit/secrets.toml`, `.venv`, or private conversation exports. Verify staged files before pushing.
- Keep `pyproject.toml` and `uv.lock` consistent when deliberately changing dependencies. Preserve the lockfile for unrelated changes.

## Validation

- Run `uv pip check`, `uv run --locked python -m compileall -q main.py llm.py local_embeddings.py backend tests`, and `uv run --locked python -m unittest discover -s tests -v`.
- `tests/test_pipeline.py` checks independent stages and service integration; `tests/test_learning.py` checks retention, experiment budgets, review gates, selection and rollback.
- `tests/test_app.py` uses Streamlit `AppTest` for startup, dotenv loading/precedence, input validation, server provider routing, and credential isolation. Mock the dotenv loader by default and use temporary fixtures for loading tests; never read a developer's actual `.env`. `tests/test_llm.py` covers configuration, embedding batching, and response ordering. Add a focused regression check for changed behavior.
- Keep paid experiments owner-triggered and outside CI. Require verified prices, reserve all attempts before calls, keep the $5 ceiling, and retain reservations when actual cost is unknown. Pilot mode requires a server rate card.
- Mock YouTube transcript fetching and LiteLLM completion/embedding calls for local checks. Placeholder keys cannot validate real service access or model availability.
- Check input validation, successful answers/history, and displayed failures when changing the Q&A flow. Check widget/session-state behavior when changing clear or download actions.
- A healthy `/_stcore/health` endpoint proves the server is listening; verify script execution separately. Report live checks and mocked checks distinctly.

## Agent skills

### Issue tracker

Specifications and tickets live in `.scratch/<feature>/`.
See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: root `GLOSSARY.md` and `docs/adr/`.
See `docs/agents/domain.md`.

## Git workflow

- Routine task-related commits and pushes are authorized. Carry completed work through validation, commit, and push without asking again.
- Use a descriptive branch for each cohesive task or feature, such as `codex/project-setup` or `fix/clear-controls`. Continue on its existing task branch while that work is ongoing.
- Keep related changes together and separate unrelated work. Stage explicit task files after reviewing `git status` and the diff.
- Write an imperative commit subject. For nontrivial work, include a body explaining the problem, resulting behavior, validation, and any material limitation.
- Push the branch with `git push -u origin HEAD`. Do not force-push, push directly to `main`, merge branches, or rewrite shared history unless specifically requested.
- Finish with the branch/commit, checks performed, and any remaining blocker. If pushing fails, preserve the local commit and report the exact blocker.
