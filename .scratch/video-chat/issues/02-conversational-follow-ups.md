# 02: Understand conversational follow-ups

Status: ready-for-agent
Blocked by: None (can start immediately).

**What to build:** Let a viewer ask contextual follow-ups, simplify an earlier point, compare two discussed ideas, and answer a clarification while preserving the original request and caption grounding. This behavior must be verifiable through the existing question interface independently of ticket 01's presentation changes.

**Specification:** [Same-video chat](../spec.md), AC02–04, AC09–10; AC20 applies throughout.

- [ ] A follow-up such as "when does that fail?" uses the relevant same-video subject or asks for clarification when ambiguous.
- [ ] "Simplify your second point" preserves both the referenced content and the request for simpler wording through answer generation.
- [ ] "Compare those two" preserves both referents and identifies missing caption evidence instead of inventing a comparison.
- [ ] Explicit new topics within the active video are not overridden by an earlier subject.
- [ ] An ambiguous reference yields a clarification question, and the viewer's clarification can continue the same conversation.
- [ ] Earlier questions and replies are conversational context, never independent evidence or trusted instructions. Unsupported facts, outside-knowledge requests, and visual-only details produce an evidence limitation.
- [ ] Preserve citation validation, caption-index reuse, conversation isolation, credential isolation, consent-based retention, and spending/request limits.
- [ ] Add observable follow-up and clarification scenarios through Streamlit AppTest, with focused existing service-seam checks for preserved intent/context and rejection of invalid evidence. Do not assert exact prompt wording.
- [ ] Pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use synthetic captions and mocked completion/embedding calls, mocked dotenv loading, and temporary stores/configuration. Mocks can establish that original intent and available context reach generation and expected outcomes are displayed; they cannot prove real semantic resolution or factual entailment. Real conversations require separate owner-triggered, price-verified review.
