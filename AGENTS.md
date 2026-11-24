# VidSage agent instructions

## Scope and maintenance

- These instructions apply to the whole repository. Keep one root `AGENTS.md` while the app remains this small; add a nested file only when a directory needs different rules.
- Update this file and the README when verified setup commands, architecture, validation, or working agreements change. Remove resolved limitations instead of accumulating session logs.
- Make the smallest complete change. Reuse the current structure and installed dependencies; avoid speculative features, abstractions, or broad dependency upgrades.
- Read the affected code and search its callers before editing. Preserve unrelated working-tree changes.

## Project map

- `main.py` contains `AgentState`, transcript fetching/chunking/retrieval in `fetch_transcript`, provider-independent prompting in `our_agent`, the LangGraph graph, and the Streamlit UI.
- `llm.py` validates model/credential/endpoint settings and adapts LiteLLM embeddings to LangChain's interface. `litellm-core` supplies both chat and embedding provider support; do not install the overlapping `litellm` distribution alongside it.
- The graph runs `START -> preprocess -> agent -> END` for each submitted question.
- FAISS indexes are rebuilt per question. History lives only in Streamlit session state and is not passed to the model as conversational memory.
- `pyproject.toml` declares dependencies; `uv.lock` pins them; `.python-version` selects Python 3.11.
- The README records setup, observed behavior, and unresolved baseline issues. Check it before assuming an issue is new.

## Environment and secrets

- Use uv and the repository's `.venv`; do not install project dependencies globally or create a second environment.
- Initial setup: `uv venv --python 3.11`, then `uv sync --locked`. For an existing environment, run `uv sync --locked`.
- Run through uv: `uv run --locked streamlit run main.py`. Activation is optional: `source .venv/bin/activate`.
- The app must open without credentials. Collect masked keys in the sidebar and pass them per request; never write browser-entered keys into process environment variables, shared caches, history, or logs.
- Models use `provider/model` names. Chat and embedding models/keys/endpoints are independent. Share a key only when their provider and endpoint match; preserve that boundary when extending provider support.
- Native endpoints may use `<PROVIDER>_API_KEY` environment variables; Gemini also accepts the legacy `GOOGLE_API_KEY`. Keep server environment keys out of browser widget defaults. Custom endpoints require an explicit session key so changing a URL cannot redirect a server credential.
- `LLM_MODEL` and `EMBEDDING_MODEL` override model defaults. The app does not load `.env` files itself; use `uv run --env-file .env --locked streamlit run main.py` when needed.
- Never print or commit credentials, `.env` files, `.streamlit/secrets.toml`, `.venv`, or private conversation exports. Verify staged files before pushing.
- Keep `pyproject.toml` and `uv.lock` consistent when deliberately changing dependencies. Preserve the lockfile for unrelated changes.

## Validation

- Run `uv pip check`, `uv run --locked python -m compileall -q main.py llm.py tests`, and `uv run --locked python -m unittest discover -s tests -v`.
- `tests/test_app.py` uses Streamlit `AppTest` for startup, input validation, provider routing, and credential isolation. `tests/test_llm.py` covers configuration, embedding batching, and response ordering. Add a focused regression check for changed behavior.
- Mock YouTube transcript fetching and LiteLLM completion/embedding calls for local checks. Placeholder keys cannot validate real service access or model availability.
- Check input validation, successful answers/history, and displayed failures when changing the Q&A flow. Check widget/session-state behavior when changing clear or download actions.
- A healthy `/_stcore/health` endpoint proves the server is listening; verify script execution separately. Report live checks and mocked checks distinctly.

## Git workflow

- Routine task-related commits and pushes are authorized. Carry completed work through validation, commit, and push without asking again.
- Use a descriptive branch for each cohesive task or feature, such as `codex/project-setup` or `fix/clear-controls`. Continue on its existing task branch while that work is ongoing.
- Keep related changes together and separate unrelated work. Stage explicit task files after reviewing `git status` and the diff.
- Write an imperative commit subject. For nontrivial work, include a body explaining the problem, resulting behavior, validation, and any material limitation.
- Push the branch with `git push -u origin HEAD`. Do not force-push, push directly to `main`, merge branches, or rewrite shared history unless specifically requested.
- Finish with the branch/commit, checks performed, and any remaining blocker. If pushing fails, preserve the local commit and report the exact blocker.
