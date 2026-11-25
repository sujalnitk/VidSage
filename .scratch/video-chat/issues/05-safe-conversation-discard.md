# 05: Change videos or clear conversations safely

Status: ready-for-agent
Blocked by: 01.

**What to build:** Explain conversation loss before a viewer changes videos or clears the discussion, then start an isolated conversation without earlier-video context or stale results.

**Specification:** [Same-video chat](../spec.md), AC15; AC20 applies throughout.

**Why blocked:** Ticket 01 establishes the conversation display and submission lifecycle that discard actions must reset consistently.

- [ ] The interface explains that changing videos or clearing the conversation discards the current discussion before that action takes effect.
- [ ] Changing the active video or clearing the conversation resets the appropriate conversation, submission, and visible message state without carrying old context forward.
- [ ] An answer belonging to the previous conversation cannot appear in the new conversation, including a stale result that finishes after the change.
- [ ] Returning to the previous video does not restore a discarded discussion or imply cross-session persistence.
- [ ] Input validation, credential isolation, answer/history downloads, consent controls, retained-data deletion, and spending/request limits continue to work. Clearing in-memory history must not falsely claim persistent retained data was deleted.
- [ ] Add Streamlit AppTest scenarios for the warning, video change, clear action, and returning to the previous video; use the existing service seam to inject a stale-result condition.
- [ ] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use mocked captions/providers and dotenv loading with synthetic exchanges and temporary stores/configuration. Verify discarded/retained state and visible results, not widget implementation details. This ticket does not require tickets 04 or 06; later slices must compose with the conversation reset behavior.
