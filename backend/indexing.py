from time import perf_counter

import faiss
import numpy as np
from llm import LOCAL_EMBEDDING_MODEL, LOCAL_REVISION

from .schemas import Chunk, ChunkPolicy, EmbeddingProfile, PipelineError, PreparedVideo, SourceSpan, version


def chunk_transcript(snapshot, policy=ChunkPolicy(), tokenizer=None):
    text = " ".join(s.text for s in snapshot.segments)
    offsets, cursor = [], 0
    for segment in snapshot.segments:
        offsets.append((cursor, cursor + len(segment.text), segment))
        cursor += len(segment.text) + 1
    chunks = []
    begin = 0
    while begin < len(text):
        end = min(begin + policy.size, len(text))
        if tokenizer is not None:
            tokens = tokenizer(text[begin:end], add_special_tokens=False, return_offsets_mapping=True)
            while len(tokens["input_ids"]) > 254:
                end = begin + tokens["offset_mapping"][253][1]
                tokens = tokenizer(text[begin:end], add_special_tokens=False, return_offsets_mapping=True)
        covered = [(a, b, s) for a, b, s in offsets if a < end and b > begin]
        if covered:
            spans = tuple(SourceSpan(s.id, max(begin - a, 0), min(end, b) - a) for a, b, s in covered)
            chunks.append(Chunk(version([snapshot.source_version, policy.version, begin, end]),
                                snapshot.source_version, spans, text[begin:end],
                                min(s.start for _, _, s in covered), max(s.end for _, _, s in covered)))
        if end == len(text):
            break
        begin = max(begin + 1, end - policy.overlap)
    return tuple(chunks)


def embedding_profile(config):
    if config["model"] == LOCAL_EMBEDDING_MODEL:
        return EmbeddingProfile(config["model"], revision=LOCAL_REVISION, normalization="l2")
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
    chunks = chunk_transcript(snapshot, policy, embeddings.tokenizer)
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
