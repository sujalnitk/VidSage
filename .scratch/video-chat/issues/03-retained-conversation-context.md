# 03: Make all retained conversation context usable

Status: resolved
Blocked by: 01, 02.

**What to build:** Let a viewer refer to any visible retained video exchange, keeping visible history aligned with usable follow-up context. Clearly explain removal of older exchanges rather than guessing at unavailable references.

**Specification:** [Same-video chat](../spec.md), AC06–08; AC20 applies throughout.

**Why blocked:** Ticket 01 establishes the chronological display; ticket 02 preserves conversational intent through resolution and generation. Both must exist to align what the viewer sees with what a follow-up can use.

- [x] A reference to a visible exchange more than three exchanges back makes that exchange available for resolution and generation without losing the viewer's original intent.
- [x] Retain and display the latest 20 completed video exchanges. The 21st exchange removes the oldest and displays a clear older-context removal notice.
- [x] References to removed or otherwise unavailable context prompt restatement or clarification; never silently map an old reference onto a newer exchange.
- [x] History removal does not break remaining caption links, downloads, feedback, consent controls, or retained-data deletion. Session history bounds do not redefine persistent retention policy.
- [x] Add Streamlit AppTest scenarios for an older visible reference, the 21st exchange, and a removed reference, with focused service checks for context boundaries where needed.
- [x] Preserve credential isolation and existing spending/request limits as conversational context grows; pass the documented dependency, compilation, and full unittest checks.

## Testing boundary

Use synthetic exchanges/captions, mocked providers and dotenv loading, and temporary stores/configuration. Verify retained visible context and outcomes rather than private slicing logic. Mocks do not establish real model reference accuracy; no paid calls are part of deterministic acceptance.

## Verified completion

Integrated on `codex/video-chat-integration` from `8b180e1dce4f3e14c1895e82711fe4028d3eadee`, preserving refresh, Retry, and correction behavior during conflict resolution. Dependency check, compilation, and all 101 combined deterministic tests passed. Full retained context, stable numbering, pruning notice, and conservative evaluation reservations are covered; real-model reference accuracy remains unverified.
