"""法律 RAG 助手 — 带登录认证的聊天界面

用法:
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run streamlit run app.py
"""

import uuid
import json
import requests
from pathlib import Path
from datetime import datetime

import streamlit as st

from app.core.config import settings

API_BASE = "http://localhost:8000"
DOCS_DIR = Path("data/docs")
FEEDBACK_FILE = Path("data/feedback.jsonl")

st.set_page_config(page_title="法律 RAG 助手", page_icon="⚖️", layout="wide")


# ---- API 工具函数 ----

def api_post(path: str, data: dict, token: str = None) -> dict:
    """发送 POST 请求到后端 API。"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(f"{API_BASE}{path}", json=data, headers=headers, timeout=30)
    return resp.json(), resp.status_code


def api_get(path: str, token: str = None) -> dict:
    """发送 GET 请求到后端 API。"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(f"{API_BASE}{path}", headers=headers, timeout=10)
    return resp.json(), resp.status_code


def api_delete(path: str, token: str = None) -> dict:
    """发送 DELETE 请求到后端 API。"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.delete(f"{API_BASE}{path}", headers=headers, timeout=10)
    return resp.json(), resp.status_code


def refresh_access_token():
    """用 refresh_token 刷新 access_token。"""
    refresh_token = st.session_state.get("refresh_token")
    if not refresh_token:
        return False
    try:
        data, code = api_post("/auth/refresh", {"refresh_token": refresh_token})
        if code == 200:
            st.session_state.access_token = data["access_token"]
            st.session_state.refresh_token = data["refresh_token"]
            return True
    except Exception:
        pass
    return False


def api_request(method: str, path: str, data: dict = None, token: str = None) -> tuple:
    """带自动刷新的 API 请求。"""
    token = token or st.session_state.get("access_token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        if method == "POST":
            resp = requests.post(f"{API_BASE}{path}", json=data, headers=headers, timeout=30)
        elif method == "GET":
            resp = requests.get(f"{API_BASE}{path}", headers=headers, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(f"{API_BASE}{path}", headers=headers, timeout=10)
        else:
            return None, 400

        # 如果 401，尝试刷新 token
        if resp.status_code == 401 and st.session_state.get("refresh_token"):
            if refresh_access_token():
                headers["Authorization"] = f"Bearer {st.session_state.access_token}"
                if method == "POST":
                    resp = requests.post(f"{API_BASE}{path}", json=data, headers=headers, timeout=30)
                elif method == "GET":
                    resp = requests.get(f"{API_BASE}{path}", headers=headers, timeout=10)
                elif method == "DELETE":
                    resp = requests.delete(f"{API_BASE}{path}", headers=headers, timeout=10)

        return resp.json(), resp.status_code
    except requests.exceptions.ConnectionError:
        return {"detail": "无法连接到后端服务，请确认 API 已启动"}, 503
    except Exception as e:
        return {"detail": str(e)}, 500


# ---- 登录/注册页面 ----

def show_login_page():
    """显示登录/注册页面。"""
    st.title("⚖️ 法律 RAG 助手")
    st.caption("请登录或注册以继续使用")

    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("用户名", key="login_username")
            password = st.text_input("密码", type="password", key="login_password")
            submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("请输入用户名和密码")
                else:
                    data, code = api_post("/auth/login", {"username": username, "password": password})
                    if code == 200:
                        st.session_state.access_token = data["access_token"]
                        st.session_state.refresh_token = data["refresh_token"]
                        st.session_state.logged_in = True
                        st.rerun()
                    else:
                        st.error(data.get("detail", "登录失败"))

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("用户名", key="reg_username")
            new_password = st.text_input("密码", type="password", key="reg_password")
            confirm_password = st.text_input("确认密码", type="password", key="reg_confirm")
            reg_submitted = st.form_submit_button("注册", type="primary", use_container_width=True)

            if reg_submitted:
                if not new_username or not new_password:
                    st.error("请输入用户名和密码")
                elif new_password != confirm_password:
                    st.error("两次输入的密码不一致")
                elif len(new_password) < 6:
                    st.error("密码长度至少 6 位")
                else:
                    data, code = api_post("/auth/register", {
                        "username": new_username,
                        "password": new_password,
                    })
                    if code == 200:
                        st.session_state.access_token = data["access_token"]
                        st.session_state.refresh_token = data["refresh_token"]
                        st.session_state.logged_in = True
                        st.success("注册成功！")
                        st.rerun()
                    else:
                        st.error(data.get("detail", "注册失败"))


# ---- 获取用户信息 ----

def get_current_user_info() -> dict | None:
    """获取当前用户信息。"""
    data, code = api_request("GET", "/auth/me")
    if code == 200:
        return data
    return None


# ---- 管理员面板 ----

def show_admin_panel():
    """管理员用户管理面板。"""
    st.header("👥 用户管理")

    data, code = api_request("GET", "/auth/users")
    if code != 200:
        st.error("获取用户列表失败")
        return

    for user in data:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            st.write(f"**{user['username']}**")
        with col2:
            st.write(f"`{user['role']}`")
        with col3:
            st.write("✅ 活跃" if user["is_active"] else "❌ 禁用")
        with col4:
            if user["role"] != "admin":
                if st.button("删除", key=f"del_{user['id']}"):
                    resp, code = api_request("DELETE", f"/auth/users/{user['id']}")
                    if code == 200:
                        st.success(f"已删除用户 {user['username']}")
                        st.rerun()
                    else:
                        st.error(resp.get("detail", "删除失败"))


# ---- 主应用 ----

def main_app():
    """主应用（已登录状态）。"""
    # 获取用户信息
    user_info = get_current_user_info()
    if not user_info:
        st.session_state.logged_in = False
        st.rerun()
        return

    # ---- Session state ----
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())[:8]
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "cache_hits" not in st.session_state:
        st.session_state.cache_hits = 0

    st.title("⚖️ 法律 RAG 助手")
    st.caption("基于检索增强生成的法律智能问答系统")

    # ---- Sidebar ----
    with st.sidebar:
        # 用户信息
        st.header(f"👤 {user_info['username']}")
        st.caption(f"角色: {user_info['role']}")

        if st.button("🚪 登出", use_container_width=True):
            api_request("POST", "/auth/logout")
            st.session_state.clear()
            st.rerun()

        st.divider()

        # 管理员面板
        if user_info["role"] == "admin":
            with st.expander("👥 用户管理"):
                show_admin_panel()
            st.divider()

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
            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            save_path = DOCS_DIR / uploaded_file.name

            with open(save_path, "wb") as f:
                f.write(uploaded_file.getvalue())

            st.success(f"文件已保存: {uploaded_file.name}")

            if st.button("开始入库", type="primary"):
                with st.spinner("正在解析并入库..."):
                    try:
                        from app.rag.document_loader import load_and_split
                        from app.rag.vector_store import add_documents
                        docs = load_and_split(str(save_path))
                        add_documents(docs)
                        st.success(f"入库成功！共 {len(docs)} 个分段")
                        from app.rag.retriever import get_retriever
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
            from app.rag.retriever import get_retriever
            from app.rag.reranker import get_reranker
            from app.rag.generator import get_generator
            retriever = get_retriever()
            reranker = get_reranker()
            generator = get_generator()
        return retriever, reranker, generator

    retriever, reranker, generator = load_models()
    from app.db.memory import ConversationMemory
    from app.db.cache import SemanticCache
    memory = ConversationMemory()
    cache = SemanticCache()

    # ---- Helper ----
    def save_feedback(session_id: str, query: str, answer: str, rating: str, intent: str):
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "query": query,
            "answer": answer,
            "rating": rating,
            "intent": intent,
            "user": user_info["username"],
        }
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ---- Chat history ----
    for msg_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📚 参考法条"):
                    for i, src in enumerate(msg["sources"]):
                        st.caption(f"来源 {i+1}: {src.get('source', '未知')} (score: {src.get('score', 0):.4f})")
                        st.text(src.get("content", "")[:300])

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
                            msg["content"], "positive", msg.get("intent", "unknown"),
                        )
                        st.toast("感谢反馈！")
                with col2:
                    if st.button("👎", key=f"neg_{msg_idx}", help="回答不够准确"):
                        st.session_state[feedback_key] = "negative"
                        save_feedback(
                            st.session_state.session_id,
                            st.session_state.messages[msg_idx - 1]["content"] if msg_idx > 0 else "",
                            msg["content"], "negative", msg.get("intent", "unknown"),
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
                context_text = memory.get_context_for_prompt(st.session_state.session_id)
                enriched_query = query
                if context_text:
                    enriched_query = f"[上下文]\n{context_text}\n\n[当前问题]\n{query}"

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

                memory.save_turn(
                    session_id=st.session_state.session_id,
                    user_msg=query, assistant_msg=answer,
                    intent=intent, sources=relevant[:5],
                )

            intent_labels = {
                "statute_lookup": "法条查询", "case_analysis": "案例分析",
                "legal_qa": "法律知识问答", "contract_review": "合同审查", "chitchat": "闲聊",
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
                "role": "assistant", "content": answer,
                "sources": sources, "intent": intent,
            })

    st.divider()
    st.caption("免责声明：本系统仅供学习参考，不构成法律建议。")


# ---- 入口 ----

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_app()
else:
    show_login_page()
