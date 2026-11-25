# 04: Recover a failed message with explicit Retry

Status: resolved
Blocked by: 01.

**What to build:** Keep a failed viewer message visible beside earlier successful exchanges and let the viewer explicitly retry it without duplicating the message or completed work.

**Specification:** [Same-video chat](../spec.md), AC12–14; AC20 applies throughout.

**Why blocked:** Ticket 01 establishes message presentation and the distinction between submission identity and repeated text.

- [x] Preparation and answer-processing failures leave the viewer's message visible with a failure indicator and explicit Retry action.
- [x] Earlier successful exchanges and the usable prepared video remain intact when an attempt fails, where no deliberate video switch occurred.
- [x] Retry makes an explicit new attempt after failure without duplicating the pending viewer message. On success, one completed exchange appears.
- [x] Duplicate delivery, UI reruns, or repeated clicks do not duplicate a completed successful exchange or silently repeat its provider work.
- [x] Failed attempts are not completed video exchanges. Prevent duplicate sends while processing and do not add automatic paid retries.
- [x] Retry remains subject to existing spending reservations, request limits, credential redaction, and retention consent; reaching a limit displays a useful failure without bypassing the limit.
- [x] Add Streamlit AppTest scenarios for injected preparation/answer failures and successful Retry, plus focused service checks for completed-request reuse and preserved state.
- [x] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Inject failures with mocked captions/providers, mock dotenv loading, and use temporary stores/configuration. Assert visible state, retained exchanges, and repeated external work rather than implementation structure. No live provider failures or paid calls are needed.

## Verified completion

Integrated on `codex/video-chat-integration` from `ed333a7ba6e0304f1cd25cfbbac9a18b6f2867f5`, preserving explicit Open video and captured consent during conflict resolution. Dependency check, compilation, and all 82 deterministic tests passed after integration. No automatic paid retries or live checks were added.
