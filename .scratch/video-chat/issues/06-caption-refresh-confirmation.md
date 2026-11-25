# 06: Refresh captions without silently replacing evidence

Status: resolved
Blocked by: 01.

**What to build:** Refresh captions while protecting the existing video conversation. Preserve discussion for unchanged captions; ask before adopting changed evidence; keep the current usable state when refresh fails or the viewer declines.

**Specification:** [Same-video chat](../spec.md), AC16–18; AC20 applies throughout.

**Why blocked:** Ticket 01 establishes the conversation display and lifecycle used to show refresh results and start fresh after confirmed evidence replacement. Ticket 05 is not a blocker: its discard controls and this refresh decision are independently demoable behaviors.

- [x] An unchanged caption refresh leaves the conversation and its usable context intact.
- [x] Changed captions are explained and require confirmation before replacing active evidence and starting a fresh conversation.
- [x] Accepting a usable replacement starts a fresh conversation against that evidence; old conversational context and stale answers cannot enter it.
- [x] Declining keeps the previous conversation and usable index. No changed evidence is silently published into the active discussion while awaiting a decision.
- [x] Caption-fetch, embedding, or replacement-validation failure preserves the prior conversation and usable index and displays a clear, credential-safe failure.
- [x] Preserve atomic publication, caption citation provenance, consent/retention controls, and existing spending/request limits, including refresh work.
- [x] Add Streamlit AppTest scenarios for unchanged, changed/accepted, changed/declined, and failed refresh; use focused preparation-service checks for atomic replacement and failure preservation.
- [x] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use synthetic old/unchanged/changed caption snapshots and mocked fetch, embedding, completion, and dotenv behavior with temporary stores/configuration. Assert active evidence and visible conversation behavior, not private index construction. No live caption fetching or paid experiments are required.

## Verified completion

Integrated on `codex/video-chat-integration` from `faedc2ed23fbe675ae0dd208d63bebded6c21d8c`, combining Retry, captured consent, and explicit active-video selection. Dependency check, compilation, and all 92 deterministic tests passed. Refresh decisions make no provider calls; the pending question remains visible for explicit resending. Live captions and model quality were not checked.
