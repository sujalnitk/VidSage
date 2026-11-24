# VidSage agent instructions

## Scope and maintenance

- These instructions apply to the whole repository. Keep one root `AGENTS.md` while the app remains this small; add a nested file only when a directory needs different rules.
- Update this file and the README when verified setup commands, architecture, validation, or working agreements change. Remove resolved limitations instead of accumulating session logs.
- Make the smallest complete change. Reuse the current structure and installed dependencies; avoid speculative features, abstractions, or broad dependency upgrades.
- Read the affected code and search its callers before editing. Preserve unrelated working-tree changes.

## Project map

- `main.py` contains the entire app: `AgentState`, transcript fetching/chunking/retrieval in `fetch_transcript`, Gemini prompting in `our_agent`, the LangGraph graph, and the Streamlit UI.
- The graph runs `START -> preprocess -> agent -> END` for each submitted question.
- FAISS indexes are rebuilt per question. History lives only in Streamlit session state and is not passed to the model as conversational memory.
- `pyproject.toml` declares dependencies; `uv.lock` pins them; `.python-version` selects Python 3.11.
- The README records setup, observed behavior, and unresolved baseline issues. Check it before assuming an issue is new.

## Environment and secrets

- Use uv and the repository's `.venv`; do not install project dependencies globally or create a second environment.
- Initial setup: `uv venv --python 3.11`, then `uv sync --locked`. For an existing environment, run `uv sync --locked`.
- Run through uv: `uv run --locked streamlit run main.py`. Activation is optional: `source .venv/bin/activate`.
- Set `GOOGLE_API_KEY` in the process environment before starting the app. The current fallback prompts in the server terminal with `getpass`; the app does not load a `.env` file itself.
- Never print or commit credentials, `.env` files, `.streamlit/secrets.toml`, `.venv`, or private conversation exports. Verify staged files before pushing.
- Keep `pyproject.toml` and `uv.lock` consistent when deliberately changing dependencies. Preserve the lockfile for unrelated changes.

## Validation

- Check dependency consistency with `uv pip check` and syntax with `uv run --locked python -m compileall -q main.py`.
- For runtime changes, use Streamlit's installed `streamlit.testing.v1.AppTest` and a focused regression check for the affected behavior. No persistent automated test suite exists at the initial setup baseline.
- Mock YouTube transcript fetching and Google embedding/model calls for local checks. A placeholder key can exercise initialization; it cannot validate real service access or model availability.
- Check input validation, successful answers/history, and displayed failures when changing the Q&A flow. Check widget/session-state behavior when changing clear or download actions.
- A healthy `/_stcore/health` endpoint proves the server is listening; verify script execution separately. Report live checks and mocked checks distinctly.

## Git workflow

- Routine task-related commits and pushes are authorized. Carry completed work through validation, commit, and push without asking again.
- Use a descriptive branch for each cohesive task or feature, such as `codex/project-setup` or `fix/clear-controls`. Continue on its existing task branch while that work is ongoing.
- Keep related changes together and separate unrelated work. Stage explicit task files after reviewing `git status` and the diff.
- Write an imperative commit subject. For nontrivial work, include a body explaining the problem, resulting behavior, validation, and any material limitation.
- Push the branch with `git push -u origin HEAD`. Do not force-push, push directly to `main`, merge branches, or rewrite shared history unless specifically requested.
- Finish with the branch/commit, checks performed, and any remaining blocker. If pushing fails, preserve the local commit and report the exact blocker.
