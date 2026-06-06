"""法律 RAG 助手 — 简易聊天界面

用法:
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
"""

import uuid
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

from app.core.config import settings
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker
from app.rag.generator import get_generator
from app.rag.document_loader import load_and_split
from app.rag.vector_store import add_documents
from app.db.memory import ConversationMemory
from app.db.cache import SemanticCache

DOCS_DIR = Path("data/docs")
FEEDBACK_FILE = Path("data/feedback.jsonl")

st.set_page_config(page_title="法律 RAG 助手", page_icon="⚖️", layout="wide")

st.title("⚖️ 法律 RAG 助手")
st.caption("基于检索增强生成的法律智能问答系统")

# ---- Session state ----
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if "messages" not in st.session_state:
    st.session_state.messages = []
if "cache_hits" not in st.session_state:
    st.session_state.cache_hits = 0

# ---- Helper functions ----
def save_feedback(session_id: str, query: str, answer: str, rating: str, intent: str):
    """保存用户反馈到 feedback.jsonl"""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "query": query,
        "answer": answer,
        "rating": rating,
        "intent": intent,
    }
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def ingest_uploaded_file(file_path: str) -> int:
    """解析并入库上传的文档，返回分段数"""
    docs = load_and_split(file_path)
    add_documents(docs)
    return len(docs)


# ---- Sidebar ----
with st.sidebar:
    st.header("关于")
    st.markdown("""
    **能力范围：**
    - 📜 法条查询
    - 📋 案例分析
    - ❓ 法律知识问答
    - 📝 合同审查
    """)
    st.divider()

    # 文件上传功能
    st.header("📁 文档上传")
    uploaded_file = st.file_uploader(
        "上传法律文档",
        type=["pdf", "docx", "txt"],
        help="支持 PDF、Word、TXT 格式",
    )

    if uploaded_file is not None:
        # 保存文件到 data/docs/
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        save_path = DOCS_DIR / uploaded_file.name

        with open(save_path, "wb") as f:
            f.write(uploaded_file.getvalue())

        st.success(f"文件已保存: {uploaded_file.name}")

        # 入库按钮
        if st.button("开始入库", type="primary"):
            with st.spinner("正在解析并入库..."):
                try:
                    chunk_count = ingest_uploaded_file(str(save_path))
                    st.success(f"入库成功！共 {chunk_count} 个分段")
                    # 重置 retriever 的 BM25 索引
                    retriever = get_retriever()
                    retriever._loaded = False
                except Exception as e:
                    st.error(f"入库失败: {e}")

    st.divider()
    st.caption(f"检索策略：BM25 + 向量 + Cross-Encoder 重排序")
    st.caption(f"LLM：DeepSeek API")
    st.divider()
    st.caption(f"会话 ID: `{st.session_state.session_id}`")
    st.caption(f"缓存命中: {st.session_state.cache_hits} 次")

    if st.button("新会话"):
        st.session_state.session_id = str(uuid.uuid4())[:8]
        st.session_state.messages = []
        st.session_state.cache_hits = 0
        st.rerun()

# ---- Lazy load models ----
@st.cache_resource
def load_models():
    with st.spinner("正在加载模型（嵌入 + 重排序），请稍候..."):
        retriever = get_retriever()
        reranker = get_reranker()
        generator = get_generator()
    return retriever, reranker, generator

retriever, reranker, generator = load_models()
memory = ConversationMemory()
cache = SemanticCache()

# ---- Chat history ----
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander("📚 参考法条"):
                for i, src in enumerate(msg["sources"]):
                    st.caption(f"来源 {i+1}: {src.get('source', '未知')} (score: {src.get('score', 0):.4f})")
                    st.text(src.get("content", "")[:300])

        # 为 assistant 消息添加反馈按钮
        if msg["role"] == "assistant":
            feedback_key = f"feedback_{msg_idx}"
            if feedback_key not in st.session_state:
                st.session_state[feedback_key] = None

            col1, col2, col3 = st.columns([1, 1, 8])
            with col1:
                if st.button("👍", key=f"pos_{msg_idx}", help="回答有帮助"):
                    st.session_state[feedback_key] = "positive"
                    save_feedback(
                        st.session_state.session_id,
                        st.session_state.messages[msg_idx - 1]["content"] if msg_idx > 0 else "",
                        msg["content"],
                        "positive",
                        msg.get("intent", "unknown"),
                    )
                    st.toast("感谢反馈！")
            with col2:
                if st.button("👎", key=f"neg_{msg_idx}", help="回答不够准确"):
                    st.session_state[feedback_key] = "negative"
                    save_feedback(
                        st.session_state.session_id,
                        st.session_state.messages[msg_idx - 1]["content"] if msg_idx > 0 else "",
                        msg["content"],
                        "negative",
                        msg.get("intent", "unknown"),
                    )
                    st.toast("感谢反馈，我们会改进！")
            with col3:
                if st.session_state[feedback_key]:
                    st.caption(f"已反馈: {'👍' if st.session_state[feedback_key] == 'positive' else '👎'}")

# ---- Input ----
if query := st.chat_input("请输入您的法律问题..."):
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        # 检索阶段
        with st.spinner("正在检索..."):
            candidates = retriever.search(query, top_k=10)
            reranked = reranker.rerank(query, candidates)
            relevant = [r for r in reranked if r.get("rerank_score", 0) >= settings.MIN_RELEVANCE_SCORE]

        if not relevant:
            answer = (
                f"当前知识库中未找到与「{query}」相关的法律条文，无法给出有据可查的法律意见。\n\n"
                "建议您查阅相关法律法规原文或咨询专业律师。"
            )
            st.markdown(answer)
            sources = []
            intent = "legal_qa"
        else:
            # 获取记忆上下文
            context_text = memory.get_context_for_prompt(st.session_state.session_id)
            enriched_query = query
            if context_text:
                enriched_query = f"[上下文]\n{context_text}\n\n[当前问题]\n{query}"

            # 流式生成，逐 token 输出
            stream = generator.generate_stream(enriched_query, relevant[:5])

            placeholder = st.empty()
            full_answer = ""
            sources = []
            intent = "legal_qa"

            for chunk in stream:
                if chunk.get("done"):
                    sources = chunk.get("sources", [])
                    intent = chunk.get("intent", "legal_qa")
                    break
                full_answer += chunk["token"]
                placeholder.markdown(full_answer + "▌")

            placeholder.markdown(full_answer)
            answer = full_answer

            # 保存对话记忆
            memory.save_turn(
                session_id=st.session_state.session_id,
                user_msg=query,
                assistant_msg=answer,
                intent=intent,
                sources=relevant[:5],
            )

        intent_labels = {
            "statute_lookup": "法条查询",
            "case_analysis": "案例分析",
            "legal_qa": "法律知识问答",
            "contract_review": "合同审查",
            "chitchat": "闲聊",
        }
        st.caption(f"意图: {intent_labels.get(intent, intent)}")

        if sources:
            with st.expander(f"🔍 参考法条 ({len(sources)} 条)"):
                for i, src in enumerate(sources):
                    score = src.get("score", 0)
                    if isinstance(score, float):
                        score = f"{score:.4f}"
                    st.caption(f"**{i+1}.** {src.get('source', '未知')}  (相关性: {score})")
                    st.text(src.get("content", "")[:500])

        # 为新生成的消息添加反馈按钮
        msg_idx = len(st.session_state.messages)
        col1, col2, col3 = st.columns([1, 1, 8])
        with col1:
            if st.button("👍", key=f"pos_{msg_idx}", help="回答有帮助"):
                save_feedback(st.session_state.session_id, query, answer, "positive", intent)
                st.toast("感谢反馈！")
        with col2:
            if st.button("👎", key=f"neg_{msg_idx}", help="回答不够准确"):
                save_feedback(st.session_state.session_id, query, answer, "negative", intent)
                st.toast("感谢反馈，我们会改进！")

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "intent": intent,
        })

# ---- Footer ----
st.divider()
st.caption("免责声明：本系统仅供学习参考，不构成法律建议。")
