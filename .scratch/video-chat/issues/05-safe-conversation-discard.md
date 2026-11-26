# 05: Change videos or clear conversations safely

Status: resolved
Blocked by: 01.

**What to build:** Explain conversation loss before a viewer changes videos or clears the discussion, then start an isolated conversation without earlier-video context or stale results.

**Specification:** [Same-video chat](../spec.md), AC15; AC20 applies throughout.

**Why blocked:** Ticket 01 establishes the conversation display and submission lifecycle that discard actions must reset consistently.

- [x] The interface explains that changing videos or clearing the conversation discards the current discussion before that action takes effect.
- [x] Changing the active video or clearing the conversation resets the appropriate conversation, submission, and visible message state without carrying old context forward.
- [x] An answer belonging to the previous conversation cannot appear in the new conversation, including a stale result that finishes after the change.
- [x] Returning to the previous video does not restore a discarded discussion or imply cross-session persistence.
- [x] Input validation, credential isolation, answer/history downloads, consent controls, retained-data deletion, and spending/request limits continue to work. Clearing in-memory history must not falsely claim persistent retained data was deleted.
- [x] Add Streamlit AppTest scenarios for the warning, video change, clear action, and returning to the previous video; use the existing service seam to inject a stale-result condition.
- [x] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use mocked captions/providers and dotenv loading with synthetic exchanges and temporary stores/configuration. Verify discarded/retained state and visible results, not widget implementation details. This ticket does not require tickets 04 or 06; later slices must compose with the conversation reset behavior.

## Verified completion

Integrated on `codex/video-chat-integration` from `253b2ae`. Combined follow-up AppTest setup now explicitly opens the video. Dependency check, compilation, and all 76 deterministic tests passed. No live provider checks ran.
