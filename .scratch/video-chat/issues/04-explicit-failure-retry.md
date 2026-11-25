# 04: Recover a failed message with explicit Retry

Status: ready-for-agent
Blocked by: 01.

**What to build:** Keep a failed viewer message visible beside earlier successful exchanges and let the viewer explicitly retry it without duplicating the message or completed work.

**Specification:** [Same-video chat](../spec.md), AC12–14; AC20 applies throughout.

**Why blocked:** Ticket 01 establishes message presentation and the distinction between submission identity and repeated text.

- [ ] Preparation and answer-processing failures leave the viewer's message visible with a failure indicator and explicit Retry action.
- [ ] Earlier successful exchanges and the usable prepared video remain intact when an attempt fails, where no deliberate video switch occurred.
- [ ] Retry makes an explicit new attempt after failure without duplicating the pending viewer message. On success, one completed exchange appears.
- [ ] Duplicate delivery, UI reruns, or repeated clicks do not duplicate a completed successful exchange or silently repeat its provider work.
- [ ] Failed attempts are not completed video exchanges. Prevent duplicate sends while processing and do not add automatic paid retries.
- [ ] Retry remains subject to existing spending reservations, request limits, credential redaction, and retention consent; reaching a limit displays a useful failure without bypassing the limit.
- [ ] Add Streamlit AppTest scenarios for injected preparation/answer failures and successful Retry, plus focused service checks for completed-request reuse and preserved state.
- [ ] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Inject failures with mocked captions/providers, mock dotenv loading, and use temporary stores/configuration. Assert visible state, retained exchanges, and repeated external work rather than implementation structure. No live provider failures or paid calls are needed.
