"""请求限流 — 基于滑动窗口的速率限制，支持 Redis 和 DiskCache 后端."""

import time
import json
import logging
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """滑动窗口限流器，使用 Sorted Set（Redis）或时间桶计数（DiskCache）。"""

    def __init__(self, backend):
        self._backend = backend

    def check(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """检查是否超过限流阈值。

        Returns:
            (allowed, remaining, reset_ts)
        """
        if isinstance(self._backend, _RedisLike):
            return self._check_sorted_set(key, max_requests, window_seconds)
        return self._check_bucket(key, max_requests, window_seconds)

    def _check_sorted_set(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """Redis Sorted Set 滑动窗口。"""
        now = time.time()
        window_start = now - window_seconds
        redis = self._backend._client

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}": now})
        pipe.expire(key, window_seconds)
        results = pipe.execute()

        count = results[1]
        remaining = max(0, max_requests - count - 1)
        reset_ts = int(now + window_seconds)

        if count >= max_requests:
            # 回滚：移除刚添加的记录
            redis.zrem(key, f"{now}")
            return False, 0, reset_ts

        return True, remaining, reset_ts

    def _check_bucket(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """固定时间桶计数（DiskCache 兼容）。"""
        now = time.time()
        bucket_key = f"{key}:{int(now // window_seconds)}"
        reset_ts = int((int(now // window_seconds) + 1) * window_seconds)

        raw = self._backend.get(bucket_key)
        count = 0
        if raw:
            try:
                count = int(raw)
            except (ValueError, TypeError):
                count = 0

        remaining = max(0, max_requests - count - 1)

        if count >= max_requests:
            return False, 0, reset_ts

        self._backend.set(bucket_key, str(count + 1), ttl=window_seconds * 2)
        return True, remaining, reset_ts


class _RedisLike:
    """类型标记，用于区分后端类型。"""
    _client = None


def _get_backend():
    """获取缓存后端实例。"""
    from app.db.backend import get_backend
    return get_backend()


def get_rate_limiter() -> RateLimiter:
    """获取限流器实例。"""
    return RateLimiter(_get_backend())


def get_client_identifier(request: Request) -> str:
    """从请求中提取限流标识（优先 API Key，其次 IP）。"""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"rate:apikey:{api_key}"
    client_ip = request.client.host if request.client else "unknown"
    return f"rate:ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI 限流中间件。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # 跳过健康检查和指标端点
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        identifier = get_client_identifier(request)
        limiter = get_rate_limiter()

        try:
            allowed, remaining, reset_ts = limiter.check(
                identifier,
                settings.RATE_LIMIT_PER_MINUTE,
                60,
            )
        except Exception as e:
            logger.warning("rate_limit_error", error=str(e))
            return await call_next(request)

        if not allowed:
            logger.warning("rate_limited", identifier=identifier)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
                headers={
                    "X-RateLimit-Limit": str(settings.RATE_LIMIT_PER_MINUTE),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response
