# 01: Send messages in a chronological video conversation

Status: resolved
Blocked by: None (can start immediately).

**What to build:** Let a viewer send messages and see completed video exchanges in chronological order, with the active video, caption citations, and existing useful controls. Deliberately repeating a message is different from duplicate delivery of the same submission.

**Specification:** [Same-video chat](../spec.md), AC01, AC05, AC14, AC19; AC20 applies throughout.

- [x] Initial questions and subsequent messages appear with their responses in chronological order, clearly attached to one active video.
- [x] Sending the same message deliberately after a reply completes creates a new exchange; text equality does not suppress a new submission.
- [x] Duplicate delivery or a UI rerun for one completed submission does not repeat provider work or append another exchange.
- [x] A submission in progress cannot be sent twice. Preserve existing backend request idempotency and limits.
- [x] Caption excerpts, timestamp links, answer/history downloads, opt-in feedback and retention, and retained-data deletion remain usable.
- [x] Explain session-only conversation lifetime and possible loss on reload without promising saved chats.
- [x] Add Streamlit AppTest scenarios for message order, deliberate repeated messages, duplicate delivery, and existing controls; use focused service checks only where UI assertions cannot establish request behavior.
- [x] Preserve server credential isolation and spending/request controls; pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use synthetic captions and mocked completion/embedding calls, mock dotenv loading, and use temporary configuration and stores. Test observable results rather than prompt wording or internal structure. These checks do not establish real model quality; do not run paid calls for this ticket without the separate owner-triggered verification process.

## Verified completion

Integrated on `codex/video-chat-integration` from `ec49a063dbf69ec35aee9589b68af2e04f960e20`. Dependency check, compilation, and all 68 deterministic tests passed after integration. Live model quality was not evaluated.
