import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker
from app.rag.generator import get_generator
from app.db.memory import ConversationMemory
from app.db.cache import SemanticCache

logger = get_logger(__name__)
router = APIRouter()

# Prometheus 指标
REQUEST_COUNT = Counter("rag_requests_total", "Total requests", ["intent", "status"])
REQUEST_DURATION = Histogram("rag_request_duration_seconds", "Request duration")
RETRIEVAL_DURATION = Histogram("rag_retrieval_duration_seconds", "Retrieval duration")
LLM_DURATION = Histogram("rag_llm_duration_seconds", "LLM generation duration")
CACHE_HITS = Counter("rag_cache_hits_total", "Cache hits", ["type"])
INTENT_DISTRIBUTION = Counter("rag_intent_distribution", "Intent distribution", ["intent"])


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
    start_time = time.time()
    logger.info("chat_request", query=request.query, session_id=request.session_id)

    retriever = get_retriever()
    reranker = get_reranker()
    generator = get_generator()
    memory = ConversationMemory()
    cache = SemanticCache()

    # 0. 先判断意图，闲聊直接返回（不需要检索）
    from app.rag.generator import _classify_intent_with_llm, CHITCHAT_RESPONSES
    intent = _classify_intent_with_llm(request.query)
    logger.info("intent_classified", intent=intent, query=request.query)
    if intent == "chitchat":
        for pattern, response in CHITCHAT_RESPONSES.items():
            if pattern in request.query:
                REQUEST_COUNT.labels(intent="chitchat", status="success").inc()
                INTENT_DISTRIBUTION.labels(intent="chitchat").inc()
                logger.info("chitchat_response", pattern=pattern, duration=time.time() - start_time)
                return ChatResponse(answer=response, sources=[], intent="chitchat")
        REQUEST_COUNT.labels(intent="chitchat", status="success").inc()
        INTENT_DISTRIBUTION.labels(intent="chitchat").inc()
        logger.info("chitchat_response", duration=time.time() - start_time)
        return ChatResponse(answer="您好！有什么法律问题需要我帮忙吗？", sources=[], intent="chitchat")

    # 1. 语义缓存检查（复用检索阶段的 embedding）
    embedding_model = retriever._get_embedding_model() if hasattr(retriever, "_get_embedding_model") else None
    # 检索内部会做 embedding，这里先用 retriever 的方法获取
    # 为了复用 embedding，我们先做检索，再检查缓存
    retrieval_start = time.time()
    candidates = retriever.search(request.query, top_k=10)
    retrieval_time = time.time() - retrieval_start
    RETRIEVAL_DURATION.observe(retrieval_time)
    logger.info("retrieval_done", candidates=len(candidates), duration=retrieval_time)

    # 2. 重排序
    reranked = reranker.rerank(request.query, candidates)
    relevant = _filter_relevant(reranked)
    logger.info("rerank_done", reranked=len(reranked), relevant=len(relevant))

    if not relevant:
        REQUEST_COUNT.labels(intent="legal_qa", status="no_result").inc()
        logger.info("no_relevant_results", query=request.query)
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
    llm_start = time.time()
    result = generator.generate(enriched_query, top_contexts)
    llm_time = time.time() - llm_start
    LLM_DURATION.observe(llm_time)
    logger.info("llm_generation_done", intent=result["intent"], duration=llm_time)

    # 5. 保存对话记忆
    memory.save_turn(
        session_id=request.session_id,
        user_msg=request.query,
        assistant_msg=result["answer"],
        intent=result["intent"],
        sources=top_contexts,
    )

    # 记录指标
    total_time = time.time() - start_time
    REQUEST_COUNT.labels(intent=result["intent"], status="success").inc()
    REQUEST_DURATION.observe(total_time)
    INTENT_DISTRIBUTION.labels(intent=result["intent"]).inc()
    logger.info("chat_success", intent=result["intent"], sources=len(result["sources"]), duration=total_time)

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        intent=result["intent"],
        cached=False,
    )


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
