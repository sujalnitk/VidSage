"""Streamlit caller; providers and credentials are resolved only on the server."""
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import streamlit as st

from backend.budget import Meter, load_rates
from backend.ingestion import parse_video
from backend.schemas import PipelineError
from backend.service import Session, ask_question, prepare_video, record_feedback
from backend.store import Store, redact
from llm import server_configs

load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
st.set_page_config(page_title="VidSage", page_icon="🎥", layout="wide")


def clear_fields():
    st.session_state.video_input = ""
    st.session_state.question_input = ""
    st.session_state.pop("submission", None)
    st.session_state.session.switch()
    st.session_state.history = st.session_state.session.history


def clear_history():
    session = st.session_state.session
    st.session_state.pop("submission", None)
    session.switch(session.video_id)
    st.session_state.history = session.history


def submit_message():
    submission = st.session_state.get("submission")
    if submission and submission["status"] in {"pending", "processing", "failed"}:
        return
    st.session_state.submission = {
        "id": uuid4().hex, "question": st.session_state.question_input,
        "status": "pending", "consent": st.session_state.retain_consent,
        "video": st.session_state.video_input,
    }


def retry_message():
    submission = st.session_state.get("submission")
    if submission and submission["status"] == "failed":
        submission.update(id=uuid4().hex, status="pending")
        submission.pop("error", None)


if "session" not in st.session_state:
    st.session_state.session = Session()
    st.session_state.history = st.session_state.session.history
session = st.session_state.session

st.title("🎥 VidSage")
st.caption("Ask about a captioned YouTube video. Answers cite the original caption timestamps.")
left, right = st.columns([2, 1])
with left:
    video = st.text_input("YouTube Video ID", key="video_input", placeholder="YouTube URL or 11-character ID")
    active_video = None
    if video.strip():
        try:
            active_video = parse_video(video)
            if session.video_id != active_video:
                if st.session_state.get("submission", {}).get("video") != video:
                    st.session_state.pop("submission", None)
                session.switch(active_video)
            st.video(f"https://www.youtube.com/watch?v={active_video}")
        except PipelineError:
            if session.video_id is not None:
                st.session_state.pop("submission", None)
                session.switch()
    elif session.video_id is not None:
        st.session_state.pop("submission", None)
        session.switch()
    st.checkbox("Keep this question, answer, and feedback locally for 30 days", value=False, key="retain_consent")
    st.caption("Reviewed evaluation examples remain until deleted. You can delete your retained data below.")
    refresh = st.checkbox("Refresh captions on the next question", value=False)
    st.button("🔁 Clear Fields", on_click=clear_fields)
    if st.checkbox("Show instructions"):
        st.info("Enter a YouTube URL or ID, then send a message below. Follow-up questions use recent exchanges from this video. Switching videos starts a new conversation.")

    st.caption("Session-only conversation: a reload or closed session may lose this discussion. Download it to keep a copy.")
    if active_video:
        st.caption(f"Video conversation: {active_video}")
    submission = st.session_state.get("submission")
    if submission and submission["status"] == "pending":
        submission["status"] = "processing"
        question = submission["question"]
        chat, embedding = {}, {}
        try:
            if not video.strip():
                st.warning("Please enter a YouTube video ID.")
                submission["status"] = "completed"
            elif not question.strip():
                st.warning("Please type a question to ask about the video.")
                submission["status"] = "completed"
            else:
                parse_video(video)
                if len(question.strip()) > 2000:
                    raise ValueError("Enter a question of 1–2,000 characters.")
                chat, embedding = server_configs()
                store = Store(os.getenv("VIDSAGE_DB", ".vidsage/pilot.sqlite3"))
                config = store.selected()
                rate_file = os.getenv("VIDSAGE_RATE_CARD", "")
                # shortcut: local development can run without price estimates; require a rate card for the invited pilot.
                meter = Meter(load_rates(Path(rate_file)), 0.25, max_attempts=24) if rate_file else None
                if os.getenv("VIDSAGE_PILOT", "0") == "1" and meter is None:
                    raise ValueError("Configure a verified server rate card before opening the pilot.")
                store.reserve(0.25 if meter else 0)
                with st.spinner("Preparing captions and finding evidence…"):
                    prepared = prepare_video(session, video, embedding, config, refresh=refresh, meter=meter)
                    ask_question(session, prepared.id, question, submission["id"], chat, embedding, config,
                                 submission["consent"], store, meter)
                submission["status"] = "completed"
                st.success("Answer ready")
        except Exception as error:
            keys = [chat.get("api_key"), embedding.get("api_key"), os.getenv("LLM_API_KEY"), os.getenv("EMBEDDING_API_KEY")]
            submission["question"] = redact(question, keys)
            submission["error"] = f"Processing failed: {redact(str(error), keys)}"
            submission["status"] = "failed"

    st.chat_input("Ask about this video", key="question_input", on_submit=submit_message,
                  disabled=bool(submission and submission["status"] in {"pending", "processing", "failed"}))

    for turn in session.history:
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            result = turn["result"]
            st.write(result["answer"])
            for claim in result["claims"]:
                for citation in claim["citations"]:
                    st.link_button(f"Caption at {citation['start']:.1f}s", citation["url"])
                    st.text(citation["excerpt"])
            st.download_button("💾 Download Answer (txt)", result["answer"], file_name=f"answer_{turn['video_id']}.txt", key=f"download_{turn['request_id']}")
            if turn["consent"]:
                rating = st.radio("Was this answer helpful?", ["helpful", "unhelpful"], horizontal=True, key=f"rating_{turn['request_id']}")
                reason = st.selectbox("Feedback reason", ["helpful", "wrong_passage", "unsupported_answer", "wrong_timestamp", "incomplete_answer", "slow_response"], key=f"reason_{turn['request_id']}")
                if st.button("Save feedback", key=f"feedback_{turn['request_id']}"):
                    try:
                        record_feedback(session, turn["request_id"], rating, reason, True,
                                        Store(os.getenv("VIDSAGE_DB", ".vidsage/pilot.sqlite3")))
                        st.success("Feedback saved locally.")
                    except Exception:
                        st.error("Feedback could not be saved. Your retained run may have expired or been deleted.")

    if submission and submission["status"] == "failed":
        with st.chat_message("user"):
            st.write(submission["question"])
            st.error(submission["error"])
            st.caption("Retry makes another attempt under the same request and spending limits. Clear the conversation to discard this message.")
            st.button("Retry", on_click=retry_message)

with right:
    st.subheader("Conversation controls")
    if not session.history and not (submission and submission["status"] == "failed"):
        st.caption("No messages yet.")
    st.download_button("📥 Download Full History (JSON)", json.dumps(session.history, indent=2),
                       file_name="vidsage_history.json", mime="application/json")
    st.button("🧹 Clear History", on_click=clear_history)
    if st.button("Delete my retained data"):
        Store(os.getenv("VIDSAGE_DB", ".vidsage/pilot.sqlite3")).delete_session(session.id)
        session.switch(session.video_id)
        st.session_state.pop("submission", None)
        st.rerun()
