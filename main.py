import streamlit as st
import asyncio
import litellm
from langgraph.graph import StateGraph , START , END
from youtube_transcript_api import YouTubeTranscriptApi , TranscriptsDisabled
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from typing import TypedDict
import os
from pathlib import Path
from dotenv import load_dotenv
import nest_asyncio
from llm import ModelEmbeddings, model_config

load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
nest_asyncio.apply()

class AgentState(TypedDict):
  video_id : str
  context_text : str
  question : str
  answer : str

def fetch_transcript(state: AgentState) -> AgentState:
  yt_api = YouTubeTranscriptApi()
  text = yt_api.fetch(state["video_id"])
  text = " ".join([snippet.text for snippet in text.snippets])

  splitter = RecursiveCharacterTextSplitter(chunk_size = 1000 , chunk_overlap = 200)
  chunks = splitter.create_documents([text])

  vector_store = FAISS.from_documents(chunks , embeddings)

  question = state["question"]
  retriever = vector_store.as_retriever(search_type = "similarity" , search_kwags = {"k":4})
  context_text = retriever.invoke(question)
  context_text = "\n\n".join(doc.page_content for doc in context_text)

  state["context_text"] = context_text

  return state

def our_agent(state : AgentState) -> AgentState:
  prompt = PromptTemplate(
      template="""
      You are a helpful assistant.
      Answer ONLY from the provided transcript context.
      If the context is insufficient, Try to give a generalised answer from your knowledge.

      {context}
      Question: {question}
    """,
    input_variables = ['context', 'question']
  )

  final_prompt = prompt.invoke({"context":state["context_text"] , "question" : state["question"]})

  result = litellm.completion(
      messages=[{"role": "user", "content": final_prompt.to_string()}],
      **chat_config,
  )
  answer = result.choices[0].message.content
  if not isinstance(answer, str) or not answer.strip():
      raise ValueError("The chat model returned no text answer.")
  state['answer'] = answer

  return state

graph = StateGraph(AgentState)

graph.add_node("preprocess" , fetch_transcript)
graph.add_node("agent" , our_agent)

graph.add_edge(START , "preprocess")
graph.add_edge("preprocess" , "agent")
graph.add_edge("agent" , END)

app = graph.compile()

st.set_page_config(page_title="YouTube Chat Assistant", page_icon="🤖🎥", layout="wide")

chat_model = os.getenv("LLM_MODEL", "gemini/gemini-3.8-flash").strip()
chat_provider = chat_model.partition("/")[0]
chat_api_key = os.getenv("LLM_API_KEY", "")
chat_base_url = os.getenv("LLM_BASE_URL", "")
default_embedding = {
    "gemini": "gemini/gemini-embedding-001",
    "openai": "openai/text-embedding-3-small",
}.get(chat_provider, "")
embedding_model = os.getenv("EMBEDDING_MODEL", default_embedding).strip()
embedding_provider = embedding_model.partition("/")[0]
embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "")

st.markdown(
    """
    <style>
    .title {
      font-size:34px;
      font-weight:700;
      margin-bottom:0;
    }
    .subtitle {
      color: #6b7280;
      margin-top:4px;
      margin-bottom:14px;
    }
    .card {
      border-radius:12px;
      padding:16px;
      box-shadow: 0 4px 18px rgba(15, 23, 42, 0.06);
      background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(250,250,250,0.9));
    }
    .muted {
      color:#6b7280;
      font-size:13px;
    }
    .small {
      font-size:13px;
    }
    .history-item {
      border-left: 3px solid #ef4444;
      padding-left:10px;
      margin-bottom:8px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown('<div class="title">🤖 YouTube Chat Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Paste a YouTube video ID, ask a question — get answers based on the video transcript.</div>', unsafe_allow_html=True)
with col_h2:
    st.markdown("###")
    st.markdown("**Tips**")
    st.markdown("<div class='muted'>• Use the video ID (not the whole URL).<br>• Example: <code>dQw4w9WgXcQ</code></div>", unsafe_allow_html=True)

st.write("---")

left, right = st.columns([2, 1])

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Video & Question")
    video_id = st.text_input("YouTube Video ID", placeholder="e.g., dQw4w9WgXcQ")
    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None

    if video_id:
        try:
            st.video(video_url)
        except Exception:
            st.info("Preview not available for this video ID.")

    st.markdown("###")
    question = st.text_area("Ask your question about the video", height=130, placeholder="e.g., What is the main argument at 5:10?")
    
    col_a, col_b, col_c = st.columns([1,1,1])
    with col_a:
        get_answer = st.button("💡 Get Answer", use_container_width=True)
    with col_b:
        clear_inputs = st.button("🔁 Clear Fields", use_container_width=True)
    with col_c:
        st.write("")
        st.write("")
        help_toggle = st.checkbox("Show instructions", value=False)

    if help_toggle:
        st.info(
            "1) Enter a YouTube video ID.\n"
            "2) Write a concise question.\n"
            "3) Click **Get Answer** and wait for the result.\n\n"
            "Backend processing (transcript/embedding/agent) runs on the server side."
        )

    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Conversation / History")
    if "history" not in st.session_state:
        st.session_state.history = []

    if st.session_state.history:
        for i, item in enumerate(reversed(st.session_state.history[-10:])):
            idx = len(st.session_state.history) - i
            st.markdown(f"**Q:** {item['question']}")
            st.markdown(f"**A:** {item['answer'][:500]}{'...' if len(item['answer'])>500 else ''}")
            st.markdown(f"<div class='muted small'>video_id: <code>{item['video_id']}</code> • {item['ts']}</div>", unsafe_allow_html=True)
            st.write("---")
    else:
        st.markdown("<div class='muted'>No history yet. Your recent Q&A will appear here.</div>", unsafe_allow_html=True)

    st.markdown("###")
    if st.button("📥 Download Full History (JSON)"):
        import json, datetime
        payload = json.dumps(st.session_state.history, indent=2, default=str)
        st.download_button("Download", payload, file_name="yt_agent_history.json", mime="application/json")
    if st.button("🧹 Clear History"):
        st.session_state.history = []
        st.experimental_rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.write("")
result_area = st.empty()

if clear_inputs:
    question = ""
    st.experimental_rerun()

if get_answer:
    if not video_id:
        st.warning("Please enter a YouTube video ID.")
    elif not question:
        st.warning("Please type a question to ask about the video.")
    else:
        with result_area.container():
            st.info("Processing the video and running the agent. This may take some time depending on video length.")
            progress = st.progress(0)
            chat_config, embedding_config = {}, {}
            try:
                chat_config = model_config(chat_model, chat_api_key, chat_base_url)
                shared_key = ""
                if (embedding_provider == chat_provider
                        and embedding_base_url.strip() == chat_base_url.strip()):
                    shared_key = chat_config["api_key"]
                embedding_config = model_config(
                    embedding_model, embedding_api_key.strip() or shared_key, embedding_base_url,
                )
                embeddings = ModelEmbeddings(embedding_config)
                progress.progress(10)
                initial_state = {
                    "video_id": video_id,
                    "question": question
                }
                progress.progress(30)
                final = asyncio.run(app.ainvoke(initial_state))
                progress.progress(90)
                answer = final.get("answer", "No answer returned.")
                progress.progress(100)

                import datetime
                st.session_state.history.append({
                    "video_id": video_id,
                    "question": question,
                    "answer": answer,
                    "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

                st.success("Answer ready")
                st.markdown("### 📝 Answer")
                st.write(answer)

                st.download_button("💾 Download Answer (txt)", answer, file_name=f"answer_{video_id}.txt", mime="text/plain")

            except Exception as e:
                message = str(e)
                for key in (chat_api_key, embedding_api_key, chat_config.get("api_key"), embedding_config.get("api_key")):
                    if key:
                        message = message.replace(key, "[redacted]")
                st.error(f"Processing failed: {message}")
            finally:
                progress.empty()

st.write("---")
st.markdown("<div style='text-align:center; color:#6b7280;'>Built with ❤️ .</div>", unsafe_allow_html=True)
