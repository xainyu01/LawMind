"""后台 Worker 进程 — 消费 Redis Stream 任务队列."""

import sys
import os
import logging

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")


def process_chat_task(task_data: dict) -> dict:
    """处理问答任务。"""
    from app.rag.retriever import get_retriever
    from app.rag.reranker import get_reranker
    from app.rag.generator import get_generator

    query = task_data.get("query", "")
    session_id = task_data.get("session_id", "default")

    if not query:
        return {"error": "empty query"}

    retriever = get_retriever()
    reranker = get_reranker()
    generator = get_generator()

    # 检索
    candidates = retriever.search(query, top_k=10)
    reranked = reranker.rerank(query, candidates)
    relevant = [r for r in reranked if r.get("rerank_score", 0) >= settings.MIN_RELEVANCE_SCORE]

    if not relevant:
        return {
            "answer": f"当前知识库中未找到与「{query}」相关的法律条文。",
            "sources": [],
            "intent": "legal_qa",
        }

    # 生成
    top_contexts = relevant[:5]
    result = generator.generate(query, top_contexts)

    # 保存对话记忆
    from app.db.memory import ConversationMemory
    memory = ConversationMemory()
    memory.save_turn(
        session_id=session_id,
        user_msg=query,
        assistant_msg=result["answer"],
        intent=result["intent"],
        sources=top_contexts,
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "intent": result["intent"],
    }


def main():
    """启动 Worker 消费任务。"""
    from app.db.queue import TaskQueue

    consumer_name = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    logger.info("worker_starting", consumer=consumer_name, redis=settings.REDIS_URL)

    queue = TaskQueue()
    queue.ensure_group()
    logger.info("worker_ready", consumer=consumer_name)

    for message_id, task_data in queue.consume(consumer_name=consumer_name):
        task_type = task_data.get("type", "chat")
        logger.info("task_received", message_id=message_id, type=task_type)

        try:
            if task_type == "chat":
                result = process_chat_task(task_data)
            else:
                result = {"error": f"unknown task type: {task_type}"}

            queue.set_result(message_id, result)
            queue.ack(message_id)
            logger.info("task_completed", message_id=message_id)

        except Exception as e:
            logger.error("task_failed", message_id=message_id, error=str(e))
            queue.set_result(message_id, {"error": str(e)})
            queue.ack(message_id)


if __name__ == "__main__":
    main()
