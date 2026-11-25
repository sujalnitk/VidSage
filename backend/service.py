from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from llm import ModelEmbeddings
from .answering import generate_answer, resolve_query, validate_citations
from .budget import PROVIDER_SLOTS
from .indexing import build_index, embedding_profile
from .ingestion import fetch_transcript, parse_video
from .retrieval import assemble_context, retrieve
from .schemas import AnswerResult, CATALOG, FeedbackEvent, PipelineError, RunTrace, version
from .store import redact


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid4().hex)
    conversation_id: str = field(default_factory=lambda: uuid4().hex)
    video_id: str | None = None
    prepared: object = None
    history: list = field(default_factory=list)
    requests: dict = field(default_factory=dict)
    lock: object = field(default_factory=RLock, repr=False)

    def switch(self, video_id=None):
        with self.lock:
            self.video_id = video_id
            self.conversation_id = uuid4().hex
            self.prepared = None
            self.history.clear()
            # Keep bounded request tombstones so old submissions cannot become new turns.
            self.requests = {key: (fingerprint, None) for key, (fingerprint, _) in self.requests.items()}


class QuestionState(TypedDict, total=False):
    query: str
    clarification: str | None
    passages: tuple
    context: object
    draft: object
    result: AnswerResult


def prepare_video(session, video, embedding_config, config=CATALOG["baseline"], language="en", refresh=False, meter=None):
    video_id = parse_video(video)
    profile = embedding_profile(embedding_config)
    with session.lock:
        if session.video_id != video_id:
            session.switch(video_id)
        current = session.prepared
        if (not refresh and current is not None and current.profile == profile
                and current.policy_version == config.chunk_policy.version and current.snapshot.language == language):
            return current
        with PROVIDER_SLOTS:
            snapshot = fetch_transcript(video_id, language)
            embeddings = ModelEmbeddings(embedding_config, meter=meter)
            ready = build_index(snapshot, config.chunk_policy, profile, embeddings, session.id, session.conversation_id)
        session.prepared = ready
        return ready


def ask_question(session, prepared_id, question, request_id, chat_config, embedding_config,
                 config=CATALOG["baseline"], consent=False, store=None, meter=None):
    if consent and store is None:
        raise PipelineError("trace_storage", "Opted-in questions require a local trace store.")
    question = question.strip()
    if not question or len(question) > 2000:
        raise PipelineError("invalid_question", "Enter a question of 1–2,000 characters.")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise PipelineError("invalid_request", "A bounded request ID is required.")
    with session.lock:
        fingerprint = version([session.conversation_id, prepared_id, question, config.version, chat_config["model"], chat_config.get("api_base"), embedding_profile(embedding_config).version, bool(consent)])
        if request_id in session.requests:
            old_fingerprint, result = session.requests[request_id]
            if fingerprint != old_fingerprint:
                raise PipelineError("request_conflict", "This request ID was already used for another question or conversation.")
            if result is None:
                raise PipelineError("request_failed", "This request already failed; submit a new request to retry.")
            return result
        if len(session.requests) >= 100:
            raise PipelineError("request_limit", "This session reached the pilot's 100-question limit.")
        prepared = session.prepared
        if (prepared is None or prepared.id != prepared_id or prepared.session_id != session.id
                or prepared.conversation_id != session.conversation_id):
            raise PipelineError("video_scope", "Prepare this conversation's video before asking a question.")
        if prepared.policy_version != config.chunk_policy.version or prepared.profile != embedding_profile(embedding_config):
            raise PipelineError("profile_mismatch", "Prepare the video again after changing its pipeline or embedding profile.")
        pipeline_version = version([config.version, chat_config["model"], chat_config.get("api_base"), prepared.profile.version])
        session.requests[request_id] = (fingerprint, None)
        conversation_id = session.conversation_id
        usage, latency = [], {}
        stages = {"source_version": prepared.snapshot.source_version, "video_id": prepared.snapshot.video_id,
                  "language": prepared.snapshot.language, "question": question, "config": asdict(config),
                  "embedding_profile": asdict(prepared.profile), "chat_model": chat_config["model"]}
        started = perf_counter()
        failure = None

        def timed(name, fn):
            before = perf_counter()
            try:
                return fn()
            finally:
                latency[name] = perf_counter() - before

        def resolution(state):
            query, clarification = timed("resolution", lambda: resolve_query(question, session.history, chat_config, usage, meter))
            stages["query"] = query
            return {"query": query, "clarification": clarification}

        def retrieval(state):
            if state.get("clarification"):
                return {}
            embeddings = ModelEmbeddings(embedding_config, meter=meter, usage=usage)
            passages = timed("retrieval", lambda: retrieve(state["query"], prepared, embeddings, prepared.profile, config.k))
            context = assemble_context(passages, prepared.snapshot, config.context_tokens)
            stages["passages"] = [asdict(p) for p in passages]
            stages["context"] = asdict(context)
            return {"passages": passages, "context": context}

        def generation(state):
            if state.get("clarification"):
                return {}
            draft = timed("generation", lambda: generate_answer(state["query"], state["context"], chat_config, config.prompt, usage, meter))
            stages["draft"] = asdict(draft)
            return {"draft": draft}

        def validation(state):
            if state.get("clarification"):
                result = AnswerResult(request_id, pipeline_version, prepared.id, "clarification", (), state["clarification"])
            else:
                result = timed("validation", lambda: validate_citations(state["draft"], state["context"], prepared, request_id, pipeline_version))
            return {"result": result}

        graph = StateGraph(QuestionState)
        for name, fn in (("resolve", resolution), ("retrieve", retrieval), ("generate", generation), ("validate", validation)):
            graph.add_node(name, fn)
        for a, b in ((START, "resolve"), ("resolve", "retrieve"), ("retrieve", "generate"), ("generate", "validate"), ("validate", END)):
            graph.add_edge(a, b)
        try:
            with PROVIDER_SLOTS:
                result = graph.compile().invoke({})["result"]
            if session.conversation_id != conversation_id or session.prepared is not prepared:
                raise PipelineError("stale_request", "The active video changed before this answer completed.")
            secrets = [chat_config.get("api_key"), embedding_config.get("api_key")]
            if any(key and key in str(asdict(result)) for key in secrets):
                raise PipelineError("credential_isolation", "The provider returned protected server content.")
            stages["result"] = asdict(result)
        except Exception as error:
            failure = error.category if isinstance(error, PipelineError) else "provider_failure"
            raise
        finally:
            latency["total"] = perf_counter() - started
            if consent and store is not None:
                trace = RunTrace(request_id, session.id, conversation_id, pipeline_version,
                                 datetime.now(timezone.utc).isoformat(), stages, latency, tuple(usage), failure)
                try:
                    store.save_trace(trace, (chat_config.get("api_key"), embedding_config.get("api_key")))
                except Exception:
                    raise PipelineError("trace_storage", "The opted-in trace could not be retained; no turn was completed.") from None
        session.requests[request_id] = (fingerprint, result)
        session.history.append({"request_id": request_id, "video_id": prepared.snapshot.video_id,
                                "question": redact(question, secrets), "answer": result.answer, "result": asdict(result),
                                "consent": bool(consent), "ts": datetime.now(timezone.utc).isoformat()})
        del session.history[:-20]
        return result


def record_feedback(session, request_id, rating, reason, consent, store):
    if not any(t["request_id"] == request_id and t["consent"] for t in session.history):
        raise PipelineError("consent_required", "Feedback needs a locally retained answer from this conversation.")
    store.record_feedback(FeedbackEvent(request_id, session.id, rating, reason, consent))
