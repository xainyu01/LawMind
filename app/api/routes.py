from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker
from app.rag.generator import get_generator

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    intent: str


def _filter_relevant(reranked: list[dict]) -> list[dict]:
    """过滤低相关性结果。"""
    return [r for r in reranked if r.get("rerank_score", 0) >= settings.MIN_RELEVANCE_SCORE]


NO_RESULT_ANSWER = (
    "当前知识库中未找到与该问题相关的法律条文，无法给出有据可查的法律意见。"
    "建议您查阅相关法律法规原文，或咨询专业法律人士。"
)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Legal Q&A endpoint: retrieve → rerank → filter → generate."""
    retriever = get_retriever()
    reranker = get_reranker()
    generator = get_generator()

    candidates = retriever.search(request.query, top_k=10)
    reranked = reranker.rerank(request.query, candidates)
    relevant = _filter_relevant(reranked)

    if not relevant:
        # 检索结果全部低于阈值，直接返回"未找到"
        return ChatResponse(
            answer=f"当前知识库中未找到与「{request.query}」相关的法律条文，无法给出有据可查的法律意见。建议您查阅相关法律法规原文或咨询专业律师。",
            sources=[],
            intent="legal_qa",
        )

    top_contexts = relevant[:5]
    result = generator.generate(request.query, top_contexts)
    return ChatResponse(**result)
