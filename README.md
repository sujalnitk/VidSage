# VidSage — YouTube Conversational QA Agent

A retrieval-augmented QA assistant that lets you ask natural language questions about a YouTube video.  
VidSage extracts the video transcript, chunks and indexes it (FAISS + Google Generative AI embeddings), then uses a Gemini-class LLM (via `langchain_google_genai`) to answer questions **only** from the retrieved transcript context. A polished Streamlit frontend provides video preview, conversation history and export/download utilities.

---

## 🔍 Project summary (one-liner)

**VidSage** — Retrieval-augmented YouTube Q&A: extract transcripts, index with FAISS + Google embeddings, and answer video questions using a Gemini LLM through a Streamlit UI.

---

## 🚀 Features

- Fetches YouTube transcripts and converts them to searchable chunks.
- Embeds chunks using `GoogleGenerativeAIEmbeddings` and indexes with FAISS for fast retrieval.
- Uses a Gemini-based LLM (via `langchain_google_genai`) to generate context-grounded answers.
- Streamlit frontend with:
  - Video preview (by video ID)
  - Question input & “Get Answer” flow
  - Conversation history persisted in `st.session_state`
  - Downloadable answers & full history

---
