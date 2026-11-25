"""Streamlit caller; providers and credentials are resolved only on the server."""
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import streamlit as st

from backend.budget import Meter, load_rates
from backend.ingestion import parse_video
from backend.schemas import PipelineError, version
from backend.service import Session, ask_question, prepare_video, record_feedback
from backend.store import Store, redact
from llm import server_configs

load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
st.set_page_config(page_title="VidSage", page_icon="🎥", layout="wide")


def clear_fields():
    st.session_state.video_input = ""
    st.session_state.question_input = ""
    st.session_state.session.switch()
    st.session_state.history = st.session_state.session.history


def clear_history():
    session = st.session_state.session
    session.switch(session.video_id)
    st.session_state.history = session.history


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
                session.switch(active_video)
            st.video(f"https://www.youtube.com/watch?v={active_video}")
        except PipelineError:
            if session.video_id is not None:
                session.switch()
    elif session.video_id is not None:
        session.switch()
    question = st.text_area("Ask your question about the video", key="question_input", height=130)
    consent = st.checkbox("Keep this question, answer, and feedback locally for 30 days", value=False)
    st.caption("Reviewed evaluation examples remain until deleted. You can delete your retained data below.")
    refresh = st.checkbox("Refresh captions on the next question", value=False)
    get_answer = st.button("💡 Get Answer", use_container_width=True)
    st.button("🔁 Clear Fields", on_click=clear_fields)
    if st.checkbox("Show instructions"):
        st.info("Enter a YouTube URL or ID, ask a question, and select Get Answer. Follow-up questions use the last three turns from this video. Switching videos starts a new conversation.")

    if get_answer:
        chat, embedding = {}, {}
        try:
            if not video.strip():
                st.warning("Please enter a YouTube video ID.")
            elif not question.strip():
                st.warning("Please type a question to ask about the video.")
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
                signature = version([session.conversation_id, active_video, question.strip(), config.version,
                                     chat["model"], chat["api_base"], embedding["model"], embedding["api_base"], bool(consent)])
                if refresh or st.session_state.get("completed_submission") != signature:
                    store.reserve(0.25 if meter else 0)
                    with st.spinner("Preparing captions and finding evidence…"):
                        prepared = prepare_video(session, video, embedding, config, refresh=refresh, meter=meter)
                        ask_question(session, prepared.id, question, uuid4().hex, chat, embedding, config,
                                     consent, store, meter)
                    st.session_state.completed_submission = signature
                st.success("Answer ready")
        except Exception as error:
            keys = [chat.get("api_key"), embedding.get("api_key"), os.getenv("LLM_API_KEY"), os.getenv("EMBEDDING_API_KEY")]
            st.error(f"Processing failed: {redact(str(error), keys)}")

    if session.history:
        turn = session.history[-1]
        result = turn["result"]
        st.subheader("📝 Answer")
        st.write(result["answer"])
        for claim in result["claims"]:
            for citation in claim["citations"]:
                st.link_button(f"Caption at {citation['start']:.1f}s", citation["url"])
                st.text(citation["excerpt"])
        st.download_button("💾 Download Answer (txt)", result["answer"], file_name=f"answer_{turn['video_id']}.txt")
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

with right:
    st.subheader("Conversation / History")
    for item in reversed(session.history[-10:]):
        st.markdown(f"**Q:** {item['question']}")
        st.write(item["answer"])
        st.caption(f"Video: {item['video_id']} · {item['ts']}")
    if not session.history:
        st.caption("No history yet.")
    st.download_button("📥 Download Full History (JSON)", json.dumps(session.history, indent=2),
                       file_name="vidsage_history.json", mime="application/json")
    st.button("🧹 Clear History", on_click=clear_history)
    if st.button("Delete my retained data"):
        Store(os.getenv("VIDSAGE_DB", ".vidsage/pilot.sqlite3")).delete_session(session.id)
        session.switch(session.video_id)
        st.rerun()
