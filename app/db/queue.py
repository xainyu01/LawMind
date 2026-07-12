"""任务队列 — 基于 Redis Stream 的异步任务队列."""

import json
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskQueue:
    """基于 Redis Stream 的任务队列，支持生产/消费模式。"""

    def __init__(self, stream_name: str = "chat_tasks"):
        self._stream = stream_name
        self._group = "chat_workers"
        self._redis = None

    def _get_redis(self):
        """延迟获取 Redis 连接（必须是真实 Redis，不支持 DiskCache）。"""
        if self._redis is not None:
            return self._redis
        import redis as _redis
        self._redis = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        # 验证连接
        try:
            self._redis.ping()
        except Exception as e:
            raise ConnectionError(
                f"Redis Stream 队列需要真实 Redis 实例，当前不可用: {e}"
            )
        return self._redis

    def ensure_group(self):
        """确保消费者组存在。"""
        r = self._get_redis()
        try:
            r.xgroup_create(self._stream, self._group, id="0", mkstream=True)
            logger.info("consumer_group_created", stream=self._stream, group=self._group)
        except Exception:
            pass  # 组已存在

    def publish(self, task_data: dict) -> str:
        """发布任务到队列，返回任务 ID。"""
        r = self._get_redis()
        task_id = r.xadd(self._stream, {"data": json.dumps(task_data, ensure_ascii=False)})
        logger.info("task_published", task_id=task_id, stream=self._stream)
        return task_id

    def consume(self, consumer_name: str = "worker-1", count: int = 1, block_ms: int = 5000):
        """消费任务（阻塞式迭代器）。

        Yields:
            (message_id, task_data)
        """
        r = self._get_redis()
        self.ensure_group()

        while True:
            try:
                messages = r.xreadgroup(
                    self._group,
                    consumer_name,
                    {self._stream: ">"},
                    count=count,
                    block=block_ms,
                )
                if not messages:
                    continue

                for stream_name, entries in messages:
                    for message_id, data in entries:
                        task_data = json.loads(data["data"])
                        yield message_id, task_data
            except Exception as e:
                logger.error("consume_error", error=str(e))
                raise

    def ack(self, message_id: str):
        """确认任务完成。"""
        r = self._get_redis()
        r.xack(self._stream, self._group, message_id)

    def set_result(self, task_id: str, result: dict, ttl: int = 3600):
        """存储任务结果。"""
        r = self._get_redis()
        key = f"task_results:{task_id}"
        r.set(key, json.dumps(result, ensure_ascii=False), ex=ttl)

    def get_result(self, task_id: str) -> Optional[dict]:
        """获取任务结果。"""
        r = self._get_redis()
        raw = r.get(f"task_results:{task_id}")
        return json.loads(raw) if raw else None

    def pending_count(self) -> int:
        """获取队列中待处理任务数。"""
        r = self._get_redis()
        try:
            info = r.xinfo_stream(self._stream)
            return info.get("length", 0)
        except Exception:
            return 0
