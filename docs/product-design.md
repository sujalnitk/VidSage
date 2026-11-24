# VidSage product design brief
November 24, 2026 · Proposal for discussion

The [backend pipeline plan](backend-pipeline-plan.md) develops preparation, indexing, retrieval, citations, and the implementation sequence for this experience.

**Design VidSage for the moment a viewer half-remembers an explanation and wants to find it again.** Someone who watched a 50-minute system design talk yesterday may remember the speaker discussing retries, but not the term “idempotency.” Give them a place to paste the link, ask in their own words, and jump to the passage that answers them. The design succeeds when they can hear the speaker and judge the answer for themselves.

The proposed first audience is people revisiting technical talks and lectures. They offer a concrete way to test the idea. Whether they do this often enough to return to VidSage is still an open question.

## What a viewer would see

| Moment | Screen and interaction | Expected effect |
| --- | --- | --- |
| Arrive with a link | A field labeled **Paste a YouTube link** and an **Open video** button. Accept a normal watch or share URL as well as the existing video ID. | Someone can use the link already on their clipboard. Opening the wrong video is easy to spot before asking a question. |
| Ask | Show the video title, player and caption language together. Put **Ask about this video** directly beneath them. During loading, show whether VidSage is finding captions or preparing the video for questions. | The viewer knows which recording is in scope and what they are waiting for. |
| Verify | Show a short answer with a clickable time and a short caption excerpt beside each material claim. Selecting the time seeks the player and highlights the passage. Keep the question and answer visible. On mobile, put the player above the answer in a single column. | The viewer can check a claim in one action. The excerpt lets them judge whether the jump is worth making. |
| Continue or leave | Keep the next question attached to this video. Offer **Copy answer with video link and time**. Starting another video opens a fresh conversation. | A follow-up such as “When does that fail?” has a clear referent. A copied note still leads back to its evidence tomorrow. |

**Illustrative answer card** · The speaker, wording and timestamp below are fictional.

> **How did the speaker stop retries from creating a second order?**
>
> The client sends the same request ID on a retry. The server recognizes the ID and returns the original order.
>
> **▶ 18:42 · Play explanation**
> “If we’ve seen that request ID already, we return the order we created the first time.”
>
> **Ask a follow-up**　　**Copy with timestamp**

When an answer depends on a diagram the speaker never describes, show “I couldn’t find that in the captions.” Offer the relevant passage if there is one. If captions themselves are unavailable, explain that before accepting questions and offer another video. These are different failures. Only the first can sometimes be resolved by rephrasing.

## What to borrow from shipped products

| Product and observed behavior | Decision for VidSage |
| --- | --- |
| YouTube lets viewers click a transcript line to jump to that part of a video. [YouTube Help](https://support.google.com/youtube/answer/15930243?hl=en) | Treat jumping to a moment as the baseline. The additional value to test is finding it when the viewer remembers the idea but cannot recall the speaker’s words. |
| Google’s Gemini Notebook lets readers select a citation and inspect the supporting quote in context. [Google’s chat guide](https://support.google.com/gemininotebook/answer/16179559) | Put the evidence on the answer itself. For a claim assembled from two parts of a lecture, show both passages. A lone link to the start of a long video gives the viewer little help. |
| Readwise Reader pairs playback with a synchronized transcript and lets readers return to highlights. Its docs also describe how transcript changes can affect highlights. [Readwise Reader video guide](https://docs.readwise.io/reader/docs/faqs/videos) | Start with a portable timestamped note. A saved library creates lasting value only if people revisit it, and maintaining anchors across transcript changes adds work. Track whether viewers actually reopen copied links before designing accounts. |

These are documented product behaviors. They establish what viewers can already do. They do not tell us whether anyone would switch to VidSage or pay for it.

## Where the current experience would break that promise

The baseline is the [reviewed application revision](https://github.com/sujalnitk/VidSage/blob/2aaf2a2bedd7839ed9ffbc49529e831ce2b18c7b/main.py). It already has a player, question input, transcript retrieval, answers, history and downloads. Keep those familiar pieces. Four decisions matter more than a visual redesign.

| Current cause | Proposed decision and likely effect | Tradeoff or check |
| --- | --- | --- |
| Transcript snippets are joined into plain text. Their times disappear before retrieval. The prompt permits a general-knowledge answer when the evidence runs out. | Preserve the source passage and its time. Accept citations only to passages VidSage actually retrieved. Answer the supported part and identify what the captions leave unanswered. | A valid time can still point to irrelevant evidence. Have a person review whether each cited passage supports the exact claim. Expect some questions to get shorter answers. |
| Each question fetches and embeds the video again. History shows earlier answers, but the model sees only the current question and retrieved text. | Prepare the video once per session and keep follow-ups scoped to it. This should reduce waiting and repeated embedding charges while making references like “that example” understandable. | In a trial, compare first-question and follow-up latency separately. Count transcript fetches and embedding calls. Start with session reuse so there is no cross-user transcript store to manage. |
| The UI asks for a bare ID, both clear actions have known errors, and processing failures appear as exception text. | Accept pasted links, make **Change video** and **Clear conversation** distinct, and distinguish unavailable captions, a temporary service problem, and missing caption evidence. | Test all three failures. Repeating an unavailable-caption request should never incur a model call. A transcript-library maintainer has documented hosting-specific access failures, so test on the intended host before promising coverage. [Maintainer discussion](https://github.com/jdepoix/youtube-transcript-api/discussions/381) |
| Visitors use the server’s provider credentials. Every question can create costs, including an unsuccessful attempt after embedding. | Before opening access beyond invited testers, cap video size and request volume, set a server-wide spend ceiling, and show a useful limit message. Measure cost per successfully verified answer, including failed attempts. | Limits exclude some long lectures. Choose them from the pilot’s video lengths and actual spend. Record timing, usage and failure categories without retaining private questions or transcript text by default. |

## What to test before investing in a build

**First, test the value with a mockup.** Recruit five people who revisited a lecture in the last week. Ask each to bring one captioned video and describe something they wanted to find. Prepare two comparable tasks per person. Have them use YouTube’s transcript for one and a hand-prepared VidSage answer card for the other. Alternate the order and assigned tasks. Time them until they locate a passage and explain how it answers the question. A quick answer with the wrong passage counts as a failure. This tests the interaction independently of model speed.

**Use an explicit decision rule.** A proposed signal to continue is that at least four of five people can verify the correct passage unaided and the median time to a correct passage is lower with VidSage. If they prefer ordinary transcript search for exact phrases, examine the paraphrased questions separately. If neither group benefits, reconsider the audience or task before adding features. Five sessions reveal friction and guide the next experiment. They cannot establish market demand.

**Then test a small private release.** Assemble a review set covering direct facts, paraphrases, questions that need two passages, and questions the captions cannot answer. Record the human-identified passages before comparing models. For each wrong answer, check whether retrieval missed the passage or the model misread it. Independently try the same videos from the intended host and measure caption availability. A beautiful citation card cannot compensate for missing captions.

**Let repeat use determine the next investment.** Give pilot viewers a week and look for an unprompted return with a second video. If they regularly copy citations into notes, explore a personal collection. If they mostly abandon on the second question, improve follow-up speed and context first. If they repeatedly need information visible only on slides, measure that share before funding visual analysis. A frontend rewrite, team workspaces and subscriptions can wait until one of these behaviors gives them a purpose.

The first product milestone is small enough to demonstrate in a minute. A viewer pastes a lecture, asks a question in their own words, plays the supporting moment and leaves with a note they can verify later.
