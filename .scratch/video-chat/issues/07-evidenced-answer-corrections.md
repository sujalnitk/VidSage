# 07: Challenge an answer and append an evidenced correction

Status: resolved
Blocked by: 02.

**What to build:** Let a viewer challenge an earlier reply or suggest a correction, recheck caption evidence, and append a supported correction or explanation while preserving the original reply.

**Specification:** [Same-video chat](../spec.md), AC11; AC20 applies throughout.

**Why blocked:** Ticket 02 preserves the challenged content and the viewer's correction intent through the answer flow. This slice can be demonstrated using the existing question interface without waiting for ticket 01's presentation work.

- [x] "That seems wrong" resolves the challenged answer or asks for clarification if the referent is ambiguous.
- [x] A supported correction appears as a new reply with caption evidence and timestamp links; the original reply is preserved.
- [x] A proposed correction unsupported by captions is not automatically accepted. Explain the evidence or its limits without inventing support.
- [x] Acknowledge an earlier unsupported claim or missing evidence rather than using the earlier generated answer as proof.
- [x] Preserve conversation isolation, citation validation, consent-based retention, credential isolation, and spending/request limits.
- [x] Add viewer-flow scenarios for a supported correction, an unsupported suggested correction, and insufficient evidence; use focused service checks for preserved original exchanges and rejected invalid evidence.
- [x] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use synthetic conversations/captions with mocked providers and dotenv loading and temporary stores/configuration. Mocked outcomes verify orchestration, displayed corrections, and preserved history; they do not establish that a real model can judge a correction correctly. Semantic quality needs separate owner-triggered, price-verified human review.

## Verified completion

Integrated on `codex/video-chat-integration` from `d137dae53fd6fb2746a93ef51251194015483dbc`. Correction mechanics were already present after ticket 02; this slice clarifies model guidance and adds five behavioral regression scenarios without claiming a fabricated red test. Dependency check, compilation, and all 97 combined deterministic tests passed. Semantic correction quality still requires separate real-model human review.
