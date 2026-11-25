# Same-video chat

Status: awaiting-final-confirmation

## Goal

Let a viewer have a chronological chat about one video, including follow-ups
that refer to previous messages and answers.

## Confirmed requirements

- Show a chronological message thread with one active video per conversation.
- Strengthen follow-ups such as "simplify that", "compare those two", and
  repeated "explain more" messages. Intentional new messages must not be
  mistaken for duplicate delivery of the same submission.
- Ground factual claims in caption evidence. Earlier answers provide
  conversational context, not independent evidence.
- Ask for clarification when a reference is ambiguous; state when caption
  evidence is insufficient. Do not silently supplement with outside knowledge.
- Resolve follow-ups against any message still visible in the current
  conversation, rather than only its last three turns. When a referenced
  message is no longer available, ask the viewer to restate it instead of guessing.
- Keep conversations in the current session for the first release. Saving
  and reopening chats is outside this scope. Explain before actions that
  discard a conversation; reloading may lose the discussion.
- Keep a failed viewer message visible with a failure indicator and an
  explicit Retry action. Preserve earlier successful answers and prevent
  duplicate sends while processing. A deliberately repeated message after
  completion is a new follow-up.
- Retain and display the latest 20 question-answer exchanges in chronological
  order. Clearly indicate when older exchanges have been removed. Do not
  silently reinterpret a reference to a removed message as a newer message.
- If refreshing captions finds changed content, explain the change and ask
  for confirmation before starting a fresh conversation against the new
  evidence. An unchanged refresh keeps the discussion. A failed refresh
  preserves the existing conversation and usable index.
- When the viewer challenges an answer, recheck caption evidence and append
  a correction or explanation as a new reply. Preserve the original answer;
  acknowledge unsupported claims or missing evidence, and do not accept a
  suggested correction without checking it.

## Current implementation findings

- The UI uses a question box, a latest-answer area, and reverse-order history.
- The resolver sees three recent turns; the session retains up to 20 turns.
- Generation sees a rewritten question and retrieved captions, without the
  original conversation. Rewriting can lose explanation or formatting intent.
- The UI suppresses consecutive identical submissions based on their content.
- Switching videos and clearing history reset the conversation.
- Existing mocked pipeline and UI tests passed (34 checks); real model
  follow-up quality has not been verified.

## Acceptance scenarios

1. A viewer asks a question, then "when does that fail?"; the follow-up
   resolves the relevant subject and answers using supporting caption evidence.
2. "Simplify your second point" and "compare those two" preserve both the
   referenced content and the requested explanation style.
3. Sending "explain more" deliberately twice produces two follow-ups;
   duplicate delivery of one submission does not create duplicate work.
4. A follow-up can reference an exchange more than three turns back when
   it remains visible. A reference to removed context prompts clarification.
5. The 21st completed exchange leaves the latest 20 visible, with a clear
   notice that older context was removed.
6. An ambiguous reference produces a clarification question. The viewer can
   answer that clarification and continue the same conversation.
7. A caption-unsupported question, visual-only detail, or request for outside
   facts does not produce an unsupported factual answer.
8. A challenged answer is checked against captions; any correction appears
   in a new reply with evidence, without rewriting the original answer.
9. A failed submission stays visible, previous answers remain intact, and
   explicit Retry can complete it without duplicating a successful exchange.
10. Changing videos or clearing the conversation explains the loss before
    discarding it. The new conversation cannot use the previous video's context.
11. Unchanged caption refresh preserves the conversation. Changed captions
    require confirmation before replacing its evidence and starting fresh;
    declining keeps the previous conversation and index. Failed refresh
    preserves the previous conversation and usable index.
12. The interface explains session-only retention and possible loss on reload.
    Existing citation links, downloads, feedback consent, retained-data
    deletion, credential isolation, and spending limits continue to work.

## Validation and evidence limits

- Add focused mocked backend and Streamlit tests for the changed behaviors,
  then run the repository's required dependency, compilation, and unittest checks.
- Mocked model responses verify orchestration and UI behavior; they do not
  establish the model's ability to resolve references or support a claim.
- Real model quality requires a separately reported, owner-triggered check
  of representative conversations against captions, under the existing
  verified-price and spending rules. No paid calls are authorized by this spec
  discussion alone.

## Out of scope

- Saving and reopening conversations across sessions.
- Cross-video conversations and outside-knowledge answers.
- Editing earlier messages, branching conversations, accounts, or visual
  analysis of video frames.

## Open decisions

None remaining from the behavior interview. Awaiting confirmation that this
consolidated specification captures the shared understanding.

## Implementation gate

Do not change application behavior until the user confirms shared understanding
of this completed specification.
