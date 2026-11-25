from time import perf_counter

import faiss
import numpy as np

from .schemas import Chunk, ChunkPolicy, EmbeddingProfile, PipelineError, PreparedVideo, SourceSpan, version


def chunk_transcript(snapshot, policy=ChunkPolicy()):
    text = " ".join(s.text for s in snapshot.segments)
    offsets, cursor = [], 0
    for segment in snapshot.segments:
        offsets.append((cursor, cursor + len(segment.text), segment))
        cursor += len(segment.text) + 1
    chunks = []
    for begin in range(0, len(text), policy.size - policy.overlap):
        end = min(begin + policy.size, len(text))
        covered = [(a, b, s) for a, b, s in offsets if a < end and b > begin]
        if covered:
            spans = tuple(SourceSpan(s.id, max(begin - a, 0), min(end, b) - a) for a, b, s in covered)
            chunks.append(Chunk(version([snapshot.source_version, policy.version, begin, end]),
                                snapshot.source_version, spans, text[begin:end],
                                min(s.start for _, _, s in covered), max(s.end for _, _, s in covered)))
        if end == len(text):
            break
    return tuple(chunks)


def embedding_profile(config):
    return EmbeddingProfile(config["model"], config.get("api_base"))


def vector_matrix(vectors, count, dimension=None):
    try:
        array = np.asarray(vectors, dtype="float32")
        if (array.ndim != 2 or array.shape[0] != count or array.shape[1] == 0
                or not np.isfinite(array).all() or (dimension is not None and array.shape[1] != dimension)):
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise PipelineError("invalid_vectors", "The embedding provider returned invalid vectors or dimensions.") from None
    return array


def build_index(snapshot, policy, profile, embeddings, session_id, conversation_id):
    started = perf_counter()
    chunks = chunk_transcript(snapshot, policy)
    if not chunks or len(chunks) > 2000:
        raise PipelineError("chunk_limit", "The caption track exceeds the pilot's chunk limit.")
    vectors = vector_matrix(embeddings.embed_documents([c.text for c in chunks]), len(chunks))
    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(vectors)
    if index.ntotal != len(chunks) or len({c.id for c in chunks}) != len(chunks):
        raise PipelineError("index_integrity", "The index does not map to its complete chunk set.")
    identifier = version([session_id, conversation_id, snapshot.source_version, policy.version, profile.version])
    return PreparedVideo(identifier, session_id, conversation_id, snapshot, policy.version, profile,
                         chunks, vectors.shape[1], index, perf_counter() - started)
