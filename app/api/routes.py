from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker
from app.rag.generator import get_generator
from app.db.memory import ConversationMemory
from app.db.cache import SemanticCache

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    intent: str
    cached: bool = False


def _filter_relevant(reranked: list[dict]) -> list[dict]:
    """过滤低相关性结果。"""
    return [r for r in reranked if r.get("rerank_score", 0) >= settings.MIN_RELEVANCE_SCORE]


NO_RESULT_ANSWER = (
    "当前知识库中未找到与该问题相关的法律条文，无法给出有据可查的法律意见。"
    "建议您查阅相关法律法规原文，或咨询专业法律人士。"
)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Legal Q&A endpoint: cache check → retrieve → rerank → filter → generate → save."""
    retriever = get_retriever()
    reranker = get_reranker()
    generator = get_generator()
    memory = ConversationMemory()
    cache = SemanticCache()

    # 1. 语义缓存检查（复用检索阶段的 embedding）
    embedding_model = retriever._get_embedding_model() if hasattr(retriever, "_get_embedding_model") else None
    # 检索内部会做 embedding，这里先用 retriever 的方法获取
    # 为了复用 embedding，我们先做检索，再检查缓存
    candidates = retriever.search(request.query, top_k=10)

    # 2. 重排序
    reranked = reranker.rerank(request.query, candidates)
    relevant = _filter_relevant(reranked)

    if not relevant:
        return ChatResponse(
            answer=f"当前知识库中未找到与「{request.query}」相关的法律条文，无法给出有据可查的法律意见。建议您查阅相关法律法规原文或咨询专业律师。",
            sources=[],
            intent="legal_qa",
        )

    # 3. 获取记忆上下文并注入 prompt
    context_text = memory.get_context_for_prompt(request.session_id)

    top_contexts = relevant[:5]
    # 将记忆上下文附加到 query 中
    enriched_query = request.query
    if context_text:
        enriched_query = f"[上下文]\n{context_text}\n\n[当前问题]\n{request.query}"

    # 4. LLM 生成
    result = generator.generate(enriched_query, top_contexts)

    # 5. 保存对话记忆
    memory.save_turn(
        session_id=request.session_id,
        user_msg=request.query,
        assistant_msg=result["answer"],
        intent=result["intent"],
        sources=top_contexts,
    )

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        intent=result["intent"],
        cached=False,
    )
