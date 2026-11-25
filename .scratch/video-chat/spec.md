# Same-video chat

Status: ready-for-agent

## Problem Statement

A viewer wants to discuss a video naturally: ask an initial question, refer to an earlier explanation, request a simpler version, compare ideas, and challenge an answer without repeating the whole conversation. VidSage already resolves some follow-ups, but its question form and reverse-order history do not provide a chronological chat. Only three recent exchanges inform resolution, although the session retains 20, and answer generation depends on a rewritten question that can lose the viewer's original intent. Consecutive identical messages are suppressed even when the viewer deliberately asks for more explanation.

Viewers also need predictable behavior when a request fails, older context is removed, they change videos, or refreshed captions change the available evidence. A conversational answer must remain verifiable against the video.

## Solution

Provide a chronological, session-only **Video conversation** for one active video. Support **Follow-up** messages against every visible retained exchange, including requests to simplify, expand, compare, or correct an explanation. Keep the latest 20 **Video exchanges** visible and available as conversational context, with a clear notice when older exchanges are removed.

Ground factual claims in **Caption evidence**, preserving timestamp links and supporting excerpts. Earlier replies provide conversational context, never independent evidence. Ask for clarification when the reference is ambiguous or unavailable; explain when supporting caption evidence is missing.

Keep failed messages visible with explicit Retry. Preserve the current conversation during refresh failures, and obtain confirmation before adopting changed captions and starting fresh. Append corrections as new replies rather than rewriting the conversation.

### Acceptance Criteria

| ID | Scenario | Required behavior |
| --- | --- | --- |
| AC01 | Initial question followed by another message | Show viewer messages and replies in chronological order, clearly attached to the same active video. |
| AC02 | “When does that fail?” after a supported explanation | Resolve the relevant subject and answer from caption evidence, or ask for clarification if the reference is ambiguous. |
| AC03 | “Simplify your second point” | Preserve the referenced point and the request for simpler language; factual claims remain supported by captions. |
| AC04 | “Compare those two” | Resolve both referents when available and compare only what the caption evidence supports; identify missing evidence instead of inventing a comparison. |
| AC05 | Two deliberate consecutive “explain more” messages | Process them as separate follow-ups after each preceding reply completes. Duplicate delivery of one submission must not repeat completed provider work or create another exchange. |
| AC06 | A reference more than three exchanges back, still visible | Make that retained exchange available to resolve the follow-up, preserving the original request's intent. |
| AC07 | The 21st completed exchange | Retain and display the latest 20 exchanges and show that older context was removed. Do not silently remap references to removed messages onto newer ones. |
| AC08 | A reference to removed or otherwise unavailable context | Ask the viewer to restate the relevant content rather than guessing. |
| AC09 | An ambiguous reference followed by the viewer's clarification | Ask a concise clarification question, retain it in the conversation, and allow the viewer to answer it and continue. |
| AC10 | Unsupported facts, outside-knowledge requests, or visual-only details absent from captions | State the evidence limitation without presenting unsupported factual claims as an answer. |
| AC11 | “That seems wrong” or a suggested correction | Recheck caption evidence, append a correction or explanation, and preserve the original reply. Acknowledge unsupported claims or missing evidence; do not agree merely because the viewer proposed a correction. |
| AC12 | A question fails during processing | Keep the viewer's message visible with a failure indicator and explicit Retry; preserve earlier successful exchanges. |
| AC13 | Explicit Retry after failure | Allow another attempt without duplicating the viewer's pending message or any already completed successful exchange. Preserve existing request and spending limits; do not silently retry paid work. |
| AC14 | A send is already processing | Prevent duplicate sends for that submission. Deliberate later messages with the same text remain valid new messages. |
| AC15 | Changing the video or clearing the conversation | Explain that the discussion will be discarded before doing so. The resulting conversation cannot use the previous conversation's context or stale results. Returning to a previous video does not restore its discarded discussion. |
| AC16 | Refresh returns unchanged captions | Keep the conversation and its existing context. |
| AC17 | Refresh finds changed captions | Explain the change and obtain confirmation before replacing the active evidence and starting a fresh conversation. Declining preserves the previous conversation and usable index. |
| AC18 | Refresh fails | Preserve the existing conversation and usable index; communicate the failure without publishing a partial replacement. |
| AC19 | Session lifetime | Explain session-only retention and possible loss on reload. Do not promise saved or reopenable conversations. |
| AC20 | Existing features and protections | Preserve caption citations, timestamp links, answer/history downloads, opt-in feedback and retention, retained-data deletion, server credential isolation, and request/spending limits. |

## User Stories

1. As a viewer, I want to see my messages and replies chronologically, so that I can follow how the discussion develops.
2. As a viewer, I want the active video to remain clear, so that I know which recording supports each answer.
3. As a viewer, I want to ask an initial question about a captioned video, so that I can locate and understand its relevant explanation.
4. As a viewer, I want to ask “when does that fail?”, so that I can explore the limitations of the idea just discussed.
5. As a viewer, I want to request simpler wording for a specific earlier point, so that I can understand it without reconstructing the question.
6. As a viewer, I want to compare two previously discussed ideas, so that I can understand their relationship within the video.
7. As a viewer, I want to request more detail repeatedly, so that each deliberate follow-up can deepen the discussion.
8. As a viewer, I want to change topics within the same video, so that an earlier topic does not override my explicit new question.
9. As a viewer, I want to refer to any retained visible exchange, so that visible history is useful conversational context.
10. As a viewer, I want to know when older exchanges have been removed, so that I understand the conversation's memory limit.
11. As a viewer, I want to be asked to restate unavailable context, so that VidSage does not guess what I meant.
12. As a viewer, I want ambiguous references clarified, so that the answer addresses the subject I intended.
13. As a viewer, I want to answer a clarification in the same conversation, so that I can continue without starting over.
14. As a viewer, I want factual claims supported by caption evidence, so that I can distinguish the video's explanation from unsupported statements.
15. As a viewer, I want timestamp links and supporting excerpts, so that I can verify an answer against the recording.
16. As a viewer, I want missing caption evidence identified, so that I know when the video cannot support an answer.
17. As a viewer, I want visual-only information treated as unavailable when captions omit it, so that the assistant does not pretend to have seen it.
18. As a viewer, I want to challenge an earlier answer, so that unsupported claims can be checked and corrected.
19. As a viewer, I want corrections appended without rewriting earlier replies, so that I can understand what changed.
20. As a viewer, I want a failed message to stay visible, so that I do not lose my question or earlier answers.
21. As a viewer, I want an explicit Retry action, so that I control another attempt after a failure.
22. As a viewer, I want duplicate sends prevented while processing, so that one submission does not create repeated work or answers.
23. As a viewer, I want to be warned before discarding a conversation, so that changing videos or clearing history does not unexpectedly lose my discussion.
24. As a viewer, I want unchanged caption refreshes to preserve my discussion, so that refreshing does not unnecessarily interrupt it.
25. As a viewer, I want to decide whether to adopt changed captions, so that earlier answers are not silently mixed with different evidence.
26. As a viewer, I want a failed refresh to preserve the usable video and discussion, so that a temporary problem does not destroy working context.
27. As a viewer, I want session-only behavior explained, so that I know a reload may lose the discussion.
28. As a viewer, I want existing answer and history downloads preserved, so that I can keep a local copy of useful information.
29. As a viewer, I want feedback retention to remain opt-in and retained data deletable, so that a chat interface does not change my privacy choices.
30. As the application owner, I want credentials to remain on the server and existing request/spending limits enforced, so that conversational use preserves the application's operating boundaries.

## Implementation Decisions

- Reuse the existing Streamlit UI, session-owned video preparation, backend question service, resolution, retrieval, generation, citation validation, and retention boundaries. This feature does not require a new application architecture or dependency family.
- Replace the question-form/latest-answer/reverse-history presentation with a chronological conversation while preserving existing useful controls.
- Keep one active video per conversation. Conversation changes must isolate history and prevent an old in-flight result from entering a new conversation.
- Align visible retained history and follow-up context at the latest 20 completed video exchanges. Do not silently limit reference resolution to three exchanges while displaying older exchanges as usable context.
- Preserve the viewer's original message and conversational referents through resolution and generation. A rewritten retrieval query alone must not erase a request to simplify, expand, compare, or check an earlier answer.
- Treat previous replies and questions as untrusted conversational context; factual answers require caption evidence and the existing citation checks. An earlier generated claim must not become evidence merely through repetition.
- Distinguish submission identity from message text. Duplicate delivery of one submission is idempotent; intentionally sending the same words later is a distinct follow-up. Retry is an explicit attempt after a failure and remains subject to existing budgets and request limits.
- Represent pending or failed viewer messages in the UI without treating a failure as a completed video exchange. Preserve successful exchanges during retries and do not add automatic paid retries.
- Refresh must preserve active state until a usable replacement exists. Unchanged evidence preserves the conversation; changed evidence requires confirmation before adoption and resets conversational context on adoption. Failure or refusal leaves the previous conversation and index usable.
- Keep corrections as new replies. Reassess caption evidence rather than silently editing history or treating the viewer's correction as fact.
- Keep conversations session-only. This changes conversational interaction, not the existing consent-based retention policy or managed deletion scope.
- No public schema or service signature change was prescribed during the discussion. Choose the smallest compatible changes within these existing boundaries when implementing; preserve unaffected callers and protections.

## Testing Decisions

- Test observable behavior: visible message order and state, returned answers and outcomes, preserved conversation data, usable video state, evidence links, and whether a submission repeats external work. Avoid assertions about private helper structure, prompt wording, or internal graph-node order.
- Prefer the highest existing seam: Streamlit AppTest drives the conversation as a viewer would. Cover chronological follow-ups, intentional repeated messages, clarification replies, older visible context, trimming notices, failures/Retry, discard warnings, caption-refresh decisions, and existing download/feedback/deletion controls through that seam where practical.
- Add focused tests at the existing backend question/preparation service seam for ownership isolation, stale results, submission idempotency, history bounds, failure preservation, caption replacement, and evidence handling where UI checks alone cannot reliably exercise or observe the condition. Reuse existing seams rather than introducing test-only interfaces.
- The existing pipeline/service suite is prior art for warm index reuse, ambiguous follow-ups, failed refresh preservation, duplicate requests, conversation isolation, citation validation, and consent-based retention. The existing Streamlit suite is prior art for startup, submission reuse, clearing/switching, feedback/deletion, and credential isolation.
- Use synthetic fixtures and mock YouTube captions plus LiteLLM completion and embedding calls. Mock dotenv loading by default and use temporary stores and configuration fixtures; never read the developer's real credentials or private conversation exports in deterministic tests.
- Keep broad acceptance criteria such as factual support distinct from what a mocked test proves. Mocks can verify that retained context and original intent reach the relevant boundary, that the expected result is displayed, and that invalid evidence is rejected. They cannot demonstrate that the real model reliably interprets a reference or that a citation entails a claim.
- Real conversational quality requires a separately reported owner-triggered check of representative caption-grounded conversations, including direct follow-ups, simplification, comparison, older references, ambiguity, and corrections. Apply existing verified-price, reservation, and spending rules; human review determines whether claims and citations actually match.
- Run the repository's documented dependency compatibility check, bytecode compilation, and full unittest suite after implementation. Preserve existing input validation, privacy, limits, retention, and evaluation regressions. A listening server health endpoint does not establish script execution or conversational quality.

## Out of Scope

- Saving, synchronizing, or reopening conversations across sessions, accounts, or devices; automatic recovery of discarded conversations after switching videos.
- Cross-video conversations, outside-knowledge answers, or using prior answers as independent factual evidence.
- Analysis of video frames, diagrams, or other visual details absent from captions.
- Editing earlier messages, branching conversations, or rewriting earlier replies when adding a correction.
- Unlimited conversation memory or silently recovering removed exchanges.
- Automatic paid retries, changing provider settings in the UI, raising existing spending/request limits, or redesigning the evaluation and retention systems.
- Live paid experiments, provider access verification, hosted caption validation, or claims of real model quality as part of writing this specification.
- Implementing the feature or creating implementation tickets in this specification task.

## Further Notes

- This specification synthesizes the behavior decisions accepted in the requirements discussion. It supersedes the earlier interview draft and its pending-final-confirmation marker; no further requirements interview is needed to publish it as ready for agent work.
- Publish and maintain this specification in the configured local Markdown tracker. `Status: ready-for-agent` records readiness locally; no GitHub issue or remote triage-label creation is required.
- No application behavior has changed as part of this specification. The existing 65-test suite passed during the requirements work; that baseline is not proof that these new acceptance criteria are implemented.
- No new architecture decision record is needed for these reversible changes within the existing boundaries. Use the project's glossary terms consistently in later tickets, implementation, and tests.
