import json

from .indexing import vector_matrix
from .schemas import PipelineError, RetrievedContext, RetrievedPassage, Source


def retrieve(query, prepared, embeddings, profile, k=4):
    if profile != prepared.profile:
        raise PipelineError("profile_mismatch", "Prepare the video again after changing its embedding profile.")
    if k not in (4, 8) or prepared.index.ntotal != len(prepared.chunks):
        raise PipelineError("index_integrity", "The retrieval configuration or index is invalid.")
    vector = vector_matrix([embeddings.embed_query(query)], 1, prepared.dimension)
    scores, indexes = prepared.index.search(vector, min(k, len(prepared.chunks)))
    return tuple(RetrievedPassage(prepared.chunks[int(i)], rank + 1, float(score), prepared.id)
                 for rank, (i, score) in enumerate(zip(indexes[0], scores[0])))


def assemble_context(passages, snapshot, token_budget=4096):
    if not isinstance(token_budget, int) or token_budget < 2:
        raise PipelineError("invalid_context_budget", "The context budget must allow at least an empty JSON source list.")
    segments = {s.id: s for s in snapshot.segments}
    seen, sources = {}, []
    for passage in passages:
        if passage.chunk.source_version != snapshot.source_version:
            raise PipelineError("source_mismatch", "Retrieved evidence belongs to a different caption snapshot.")
        for span in passage.chunk.spans:
            segment = segments.get(span.segment_id)
            if segment is None or not 0 <= span.begin < span.end <= len(segment.text):
                raise PipelineError("source_mismatch", "Retrieved evidence has an invalid segment reference.")
            intervals = [(span.begin, span.end)]
            for a, b in seen.get(span.segment_id, []):
                intervals = [(x, y) for lo, hi in intervals for x, y in ((lo, min(hi, a)), (max(lo, b), hi)) if x < y]
            for lo, hi in intervals:
                source = Source(f"S{len(sources) + 1}", segment.id, segment.text[lo:hi], segment.start, segment.end)
                trial = sources + [source]
                encoded = json.dumps([{"id": s.id, "text": s.text} for s in trial], ensure_ascii=False)
                # UTF-8 bytes conservatively bound tokens without downloading a provider tokenizer.
                if len(encoded.encode()) > token_budget:
                    continue
                sources.append(source)
                seen.setdefault(span.segment_id, []).append((lo, hi))
    text = json.dumps([{"id": s.id, "text": s.text} for s in sources], ensure_ascii=False)
    return RetrievedContext(tuple(sources), text, len(text.encode()))
