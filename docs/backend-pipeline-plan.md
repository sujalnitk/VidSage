# VidSage modular backend

The modular backend and offline learning workflow are implemented. This document records the boundaries; [the README](../README.md) contains setup and runtime limits, and [the evaluation guide](evaluation.md) contains owner commands and the release gates that still require real providers, the intended host and human review. The [product design](product-design.md) remains product context.

## Preparation

`prepare_video(session, video, embedding_config, config, language, refresh)` parses a supported YouTube URL/ID, fetches one caption language, validates ordered segments and creates an immutable `TranscriptSnapshot`. Source identity hashes the video, language, generated status and original caption text/times. Gaps, overlapping captions and repeated phrases retain their own segment references.

The chunker carries exact character spans through 1,000/200 character windows. Splitting a caption retains its available start/end timing; it never invents word timing. `ModelEmbeddings` batches, orders and validates document vectors. FAISS uses a flat squared-L2 index and retains one chunk per vector, dimension and a credential-free embedding profile. Publication replaces the session's ready reference only after the artifact validates. Failed same-video refreshes preserve the prior artifact.

Prepared data lives in the session and is reusable across questions. Model, endpoint, source, language and chunk-policy changes invalidate the relevant preparation. A second question performs no transcript download and no document embeddings. There is no cross-session index cache or persistence of credential-bearing clients.

## Questions

`ask_question` requires session, conversation, prepared-video and request identity. It checks ownership/profile compatibility and deduplicates completed submissions. Failed requests remain tombstones so automatic resubmission cannot silently repeat paid work. One session lock serializes requests; one process semaphore bounds provider concurrency.

The LangGraph flow is `resolve → retrieve → generate → validate`. Question resolution uses at most three same-video turns, each bounded, and can ask for clarification. Dense retrieval explicitly requests `k=4`; the initial retrieval candidate uses `k=8`. Context assembly removes overlapping source spans and enforces a conservative byte/token budget while keeping exact source IDs and text.

Generation returns JSON claims and evidence references, or an insufficient-context outcome. The validator rejects malformed outcomes, unknown IDs and inexact excerpts. The backend constructs timestamp links from original captions. It cannot prove semantic support from string matching: correctness and claim support require independent judging and human review.

Completed history is bounded to 20 turns and committed only after validation and, when opted in, successful trace persistence. Switching videos or clearing the conversation releases the index/history and prevents stale results from appearing in the active conversation. Streamlit keeps provider settings entirely server-side and offers answer/history downloads, opt-in feedback and deletion.

## Learning and versioning

The backend records opted-in `RunTrace` and attributed `FeedbackEvent` records in local SQLite. Retained traces/feedback expire after 30 days. Human approval creates a versioned regression example labeled by source segment IDs; approval requires frozen-source validation and records provenance. Explicit deletion removes derived managed examples as well as the run.

Owner-triggered experiments compare one allowlisted factor at a time using frozen local JSONL datasets. Sources, chunk policies, embedding profiles, prompt/configuration identities, datasets and judge rubrics are versioned. The first experiment is retrieval-only. System comparisons separately judge correctness, support, completeness, abstention and useful timing. Budget preflight reserves the full maximum cost before execution; each complete comparison must fit $5. Invalid judge responses and provider/budget failures produce incomplete reports.

The owner locks a candidate on development examples before held-out execution. The six selected Veritasium videos have a four/two split and ten proposed questions per video. The release gate requires all 60 to be human-reviewed, a reviewed failure to improve, no new quality regressions, and human report review. Selection records the report/configuration and retains rollback. Ordinary CI exercises this lifecycle with synthetic sources and mocked providers; it does not spend money or claim real-world improvement.

## Remaining validation

All six selected English caption tracks were fetched locally. Human review of the drafts, real retrieval/generation/judging, hosted caption reliability and actual request/spend/cleanup behavior still need verification. Working provider credentials and owner-verified rates are absent in this workspace. A health endpoint alone does not validate script execution or these service gates.
