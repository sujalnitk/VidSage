# 01: Send messages in a chronological video conversation

Status: ready-for-agent
Blocked by: None (can start immediately).

**What to build:** Let a viewer send messages and see completed video exchanges in chronological order, with the active video, caption citations, and existing useful controls. Deliberately repeating a message is different from duplicate delivery of the same submission.

**Specification:** [Same-video chat](../spec.md), AC01, AC05, AC14, AC19; AC20 applies throughout.

- [ ] Initial questions and subsequent messages appear with their responses in chronological order, clearly attached to one active video.
- [ ] Sending the same message deliberately after a reply completes creates a new exchange; text equality does not suppress a new submission.
- [ ] Duplicate delivery or a UI rerun for one completed submission does not repeat provider work or append another exchange.
- [ ] A submission in progress cannot be sent twice. Preserve existing backend request idempotency and limits.
- [ ] Caption excerpts, timestamp links, answer/history downloads, opt-in feedback and retention, and retained-data deletion remain usable.
- [ ] Explain session-only conversation lifetime and possible loss on reload without promising saved chats.
- [ ] Add Streamlit AppTest scenarios for message order, deliberate repeated messages, duplicate delivery, and existing controls; use focused service checks only where UI assertions cannot establish request behavior.
- [ ] Preserve server credential isolation and spending/request controls; pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use synthetic captions and mocked completion/embedding calls, mock dotenv loading, and use temporary configuration and stores. Test observable results rather than prompt wording or internal structure. These checks do not establish real model quality; do not run paid calls for this ticket without the separate owner-triggered verification process.
