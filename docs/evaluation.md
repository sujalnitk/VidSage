# Evaluation and feedback-driven learning

The implementation is a single Python backend, with deterministic checks in CI and paid experiments run only by the owner. It does not train model weights or automatically publish configuration changes.

## Dataset and source review

The selected [Veritasium manifest](../eval/videos.json) has four development videos and two held-out videos. The workspace currently contains frozen English captions and 60 assistant-authored, source-linked drafts under `eval/local/`. All drafts have `reviewed: false`. Six source variants contain an explicitly synthetic malicious caption; their metadata records the original source version. These variants test whether caption instructions are treated as evidence rather than followed.

For a fresh checkout:

```bash
uv run --locked python -m backend freeze
uv run --locked python -m backend draft-dataset
uv run --locked python -m backend source eval/local/sources/nmgFG7PUHfo.json
```

`freeze` never overwrites an existing snapshot. `draft-dataset` creates a generic 60-question starting point and refuses to overwrite review work. The source-linked drafts prepared in this workspace are more specific than that generic starting point. Keep real captions and datasets local; only synthetic fixtures are committed.

Each JSONL record has `id`, `video_id`, `source_version`, `question`, `answerable`, `evidence_sets`, `reference`, `split`, `category`, `reviewed`, `reviewer`, optional bounded same-video `history`, and `provenance`. Each evidence set is a list of alternative source **segment IDs**; all sets are required for complete evidence coverage. A multi-caption passage can be labeled as several required singleton sets. Changing chunk sizes preserves these labels. Unanswerable cases have no evidence sets and a rubric explaining why to abstain.

Before setting `reviewed: true`, a human must read the source evidence, correct any draft question/reference, verify answerability, check each segment label and follow-up history, and enter their reviewer name. Save the reviewed copy as `eval/local/reviewed.jsonl`. Synthetic labels in unittest fixtures only verify mechanics; they are not real-video gold labels.

The release comparison requires exactly 60 reviewed questions, ten per video, four development and two held-out videos, with direct facts, paraphrases, exact terms, multi-passage questions, follow-ups, unavailable evidence and caption instructions. Experiments reject unreviewed records, source mismatches, missing evidence IDs, duplicate IDs, or videos appearing in both splits. Construct candidates using development data; do not use held-out outcomes to tune them.

## First experiment: retrieval only

Configure embedding and chat models/keys through `.env`; follow-ups may need the chat resolver even in retrieval-only mode. Copy `eval/rates.example.json` to `eval/local/rates.json`, supply exact model names, an ISO verification date, a provider pricing URL, and conservative per-million input/output prices. Include the judge's prices for system experiments. Placeholder rate cards are rejected.

```bash
uv run --locked python -m backend experiment \
  --dataset eval/local/reviewed.jsonl --candidate k8 \
  --rates eval/local/rates.json --mode retrieval
```

This compares the active version with one allowlisted candidate on the same frozen development examples. Available candidates are `chunks600` (600/120 characters), `k8`, and `prompt-v2`; each changes one factor from the initial baseline. The runner rejects pairs differing in more than one factor. The embedding model/endpoint/profile is frozen for both arms.

The report includes Recall@k (support hit rate), reciprocal rank, and required-evidence-set coverage separately from answer quality. It records ranked passages, source/version IDs, cold preparation time, question latency, provider usage and conservative cost reservations. Retrieval-only reports cannot recommend or select a production version.

```bash
uv run --locked python -m backend report REPORT_ID
```

Reports stay in local SQLite. A real baseline has not yet run in this workspace because working provider keys and verified rates are absent. The tests exercise retrieval metrics with deterministic embeddings; those results are not evidence of real retrieval quality.

## Review feedback and add a regression

A tester must opt in before their run and feedback are retained. Helpful/unhelpful feedback is attributed to the request and session; submitting it again updates the same event.

```bash
uv run --locked python -m backend review-queue
uv run --locked python -m backend approve-example REQUEST_ID \
  --example eval/local/proposed-example.json \
  --source eval/local/sources/VIDEO_ID.json --reviewer 'Owner name'
uv run --locked python -m backend export-examples
```

Review the failure against the frozen source first. `approve-example` validates source identity, original question, evidence segment references and the human reviewer. It records rating/reason and session provenance; a rating or a user correction alone is never a reference answer. The managed export is `.vidsage/datasets/approved.jsonl`. Merge approved development regressions into the reviewed dataset before locking a new experiment; keep each example unchanged to preserve its approval identity.

## Paired system comparison and selection

Set independent `JUDGE_MODEL`, `JUDGE_API_KEY` and optional `JUDGE_BASE_URL` on the server. The judge uses a pinned model, rubric hash/version, temperature zero and a 300-token output limit. The answer generator uses 1,200 output tokens. Structural checks validate exact citation excerpts and backend timestamps; the judge scores correctness, support, completeness, abstention and timing separately. Human review must calibrate the judge and inspect changed outcomes.

```bash
uv run --locked python -m backend experiment \
  --dataset eval/local/reviewed.jsonl --candidate prompt-v2 \
  --rates eval/local/rates.json --mode system
uv run --locked python -m backend report DEV_REPORT_ID
uv run --locked python -m backend review-report DEV_REPORT_ID --reviewer 'Owner name'
uv run --locked python -m backend experiment \
  --dataset eval/local/reviewed.jsonl --candidate prompt-v2 \
  --rates eval/local/rates.json --mode system --phase heldout --lock DEV_REPORT_ID
uv run --locked python -m backend report HELDOUT_REPORT_ID
uv run --locked python -m backend review-report HELDOUT_REPORT_ID --reviewer 'Owner name'
uv run --locked python -m backend select prompt-v2 --report HELDOUT_REPORT_ID
uv run --locked python -m backend rollback
```

A held-out run must match the locked development configuration, embedding/chat/judge identity, prompt/rubric hashes, parameters and development dataset version. Recommendation requires an approved, feedback-derived development failure to improve and no new quality regression in either phase. Invalid judge output makes the comparison incomplete. Selection requires a complete passing system report, the full release dataset and human report review. It records the selected configuration/report and retains previous selections for rollback. A retrieval-only report cannot pass this gate.

Cost and latency changes remain visible even when quality improves. Cost per correctly supported answer is reported only when all relevant provider costs are available; otherwise it remains unknown. There is no claim of measured model improvement until these real comparisons and reviews happen.

## Limits, privacy and release gates

The complete experiment preflights and reserves both arms, preparation, question resolution, generation and judging before execution. There are no automatic provider retries. Unknown prices or an estimate above $5 stop before a paid call. Runtime reservations prevent extra unplanned work; incomplete comparisons never become selectable. Rate verification and the real provider smoke test must confirm the assumptions behind these bounds, including output/reasoning billing.

Opted-in traces/feedback expire after 30 days; opening the store or running `python -m backend purge` removes expired rows. Configure that cleanup daily on the actual host. Approved examples survive trace expiry. Deleting a session removes its traces, feedback and approved examples, rewrites the managed export and datasets registered by the experiment CLI, and invalidates comparison reports. Copies made independently and backups need their own deletion process. `python -m backend delete-session SESSION_ID` provides the owner operation; the UI deletes the current tester's data. SQLite files are private and Git-ignored.

Before inviting testers, complete human dataset review, the real retrieval baseline, a provider and judge smoke test, judge calibration, the integrated comparison, host-specific caption access, restricted invited access, and spend/request/retention checks on that host. Run one application process with persistent local SQLite storage; indexes remain session memory. More processes require shared concurrency controls and budgets first.

The separation between retrieval and answer metrics follows the [Ragas metric reference](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/). The reviewed production-feedback-to-offline-evaluation cycle follows [LangSmith's evaluation guidance](https://docs.langchain.com/langsmith/evaluation-types).
