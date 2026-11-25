from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


def version(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class PipelineError(ValueError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class Segment:
    id: str
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class TranscriptSnapshot:
    video_id: str
    language: str
    generated: bool
    source_version: str
    fetched_at: str
    segments: tuple[Segment, ...]


@dataclass(frozen=True)
class ChunkPolicy:
    size: int = 1000
    overlap: int = 200

    def __post_init__(self):
        if not 0 <= self.overlap < self.size:
            raise ValueError("Chunk overlap must be smaller than its positive size.")

    @property
    def version(self):
        return version(asdict(self))


@dataclass(frozen=True)
class SourceSpan:
    segment_id: str
    begin: int
    end: int


@dataclass(frozen=True)
class Chunk:
    id: str
    source_version: str
    spans: tuple[SourceSpan, ...]
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class EmbeddingProfile:
    model: str
    endpoint: str | None = None
    revision: str = "unspecified"
    metric: str = "squared_l2"
    normalization: str = "none"

    @property
    def version(self):
        return version(asdict(self))


@dataclass(frozen=True)
class PipelineConfig:
    name: str = "baseline"
    chunk_policy: ChunkPolicy = ChunkPolicy()
    k: int = 4
    prompt: str = "grounded-v1"
    context_tokens: int = 4096

    @property
    def version(self):
        return version(asdict(self))


CATALOG = {
    "baseline": PipelineConfig(),
    "chunks600": PipelineConfig("chunks600", ChunkPolicy(600, 120)),
    "k8": PipelineConfig("k8", k=8),
    "prompt-v2": PipelineConfig("prompt-v2", prompt="grounded-v2"),
}


@dataclass(frozen=True)
class PreparedVideo:
    id: str
    session_id: str
    conversation_id: str
    snapshot: TranscriptSnapshot
    policy_version: str
    profile: EmbeddingProfile
    chunks: tuple[Chunk, ...]
    dimension: int
    index: Any = field(repr=False, compare=False)
    preparation_seconds: float = 0


@dataclass(frozen=True)
class RetrievedPassage:
    chunk: Chunk
    rank: int
    score: float
    prepared_id: str
    score_kind: str = "squared_l2_lower_is_better"


@dataclass(frozen=True)
class Source:
    id: str
    segment_id: str
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class RetrievedContext:
    sources: tuple[Source, ...]
    text: str
    token_upper_bound: int


@dataclass(frozen=True)
class Evidence:
    source_id: str
    excerpt: str


@dataclass(frozen=True)
class Claim:
    text: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class AnswerDraft:
    outcome: str
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class Citation:
    source_id: str
    segment_id: str
    excerpt: str
    start: float
    end: float
    url: str


@dataclass(frozen=True)
class ResolvedClaim:
    text: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True)
class AnswerResult:
    request_id: str
    pipeline_version: str
    prepared_id: str
    outcome: str
    claims: tuple[ResolvedClaim, ...]
    answer: str


@dataclass(frozen=True)
class RunTrace:
    request_id: str
    session_id: str
    conversation_id: str
    pipeline_version: str
    created_at: str
    stages: dict
    latency: dict
    usage: tuple[dict, ...]
    failure_category: str | None = None


@dataclass(frozen=True)
class FeedbackEvent:
    request_id: str
    session_id: str
    rating: str
    reason: str
    consent: bool
