"""存储后端抽象层 — Redis（生产）+ DiskCache（本地开发）."""

import json
import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """统一缓存后端接口，支持 List / Hash / KV 操作."""

    # ---- List 操作（对话记忆） ----
    @abstractmethod
    def lpush(self, key: str, *values: str) -> int: ...

    @abstractmethod
    def lrange(self, key: str, start: int, end: int) -> List[str]: ...

    @abstractmethod
    def ltrim(self, key: str, start: int, end: int) -> None: ...

    # ---- Hash 操作（上下文提取） ----
    @abstractmethod
    def hset(self, key: str, mapping: dict) -> int: ...

    @abstractmethod
    def hgetall(self, key: str) -> dict: ...

    # ---- KV 操作 ----
    @abstractmethod
    def get(self, key: str) -> Optional[str]: ...

    @abstractmethod
    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def expire(self, key: str, ttl: int) -> None: ...

    @abstractmethod
    def ping(self) -> bool: ...


class RedisBackend(CacheBackend):
    """Redis 后端，适用于生产环境."""

    def __init__(self, url: str):
        import redis as _redis
        self._client = _redis.from_url(url, decode_responses=True)

    def lpush(self, key: str, *values: str) -> int:
        return self._client.lpush(key, *values)

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        return self._client.lrange(key, start, end)

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._client.ltrim(key, start, end)

    def hset(self, key: str, mapping: dict) -> int:
        return self._client.hset(key, mapping=mapping)

    def hgetall(self, key: str) -> dict:
        return self._client.hgetall(key)

    def get(self, key: str) -> Optional[str]:
        return self._client.get(key)

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        self._client.set(key, value, ex=ttl)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def expire(self, key: str, ttl: int) -> None:
        self._client.expire(key, ttl)

    def ping(self) -> bool:
        return self._client.ping()


class DiskBackend(CacheBackend):
    """基于 diskcache 的本地文件存储后端，Windows 开发环境无需 Redis."""

    def __init__(self, directory: str):
        import diskcache
        self._cache = diskcache.Cache(directory)
        # 用单独的 dict 存储 List/Hash 结构
        self._index = diskcache.Index(directory=directory)

    def _ensure_list(self, key: str) -> list:
        return self._index.get(key, [])

    def lpush(self, key: str, *values: str) -> int:
        lst = self._ensure_list(key)
        for v in values:
            lst.insert(0, v)
        self._index[key] = lst
        return len(lst)

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        lst = self._ensure_list(key)
        if end == -1:
            return lst[start:]
        return lst[start : end + 1]

    def ltrim(self, key: str, start: int, end: int) -> None:
        lst = self._ensure_list(key)
        if end == -1:
            self._index[key] = lst[start:]
        else:
            self._index[key] = lst[start : end + 1]

    def hset(self, key: str, mapping: dict) -> int:
        h = self._index.get(key, {})
        h.update(mapping)
        self._index[key] = h
        return len(mapping)

    def hgetall(self, key: str) -> dict:
        return self._index.get(key, {})

    def get(self, key: str) -> Optional[str]:
        val = self._cache.get(key)
        return val

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        self._cache.set(key, value, expire=ttl)

    def delete(self, key: str) -> None:
        self._cache.delete(key)
        if key in self._index:
            del self._index[key]

    def expire(self, key: str, ttl: int) -> None:
        # diskcache 不直接支持 expire on index，用 cache 做代理
        val = self._index.get(key)
        if val is not None:
            self._cache.set(key, json.dumps(val, ensure_ascii=False), expire=ttl)

    def ping(self) -> bool:
        return True


_backend: Optional[CacheBackend] = None


def get_backend() -> CacheBackend:
    """获取缓存后端，自动探测 Redis 并降级到 DiskCache."""
    global _backend
    if _backend is not None:
        return _backend

    backend_type = settings.CACHE_BACKEND_TYPE

    if backend_type == "disk":
        logger.info("强制使用 DiskBackend")
        _backend = DiskBackend(settings.DISK_CACHE_DIR)
        return _backend

    if backend_type == "redis":
        backend = RedisBackend(settings.REDIS_URL)
        if backend.ping():
            logger.info("使用 RedisBackend")
            _backend = backend
            return _backend
        raise ConnectionError(f"Redis 不可用: {settings.REDIS_URL}")

    # auto 模式：先尝试 Redis，失败降级
    try:
        backend = RedisBackend(settings.REDIS_URL)
        backend.ping()
        logger.info("Redis 可用，使用 RedisBackend")
        _backend = backend
    except Exception:
        logger.warning("Redis 不可用，降级为 DiskBackend")
        _backend = DiskBackend(settings.DISK_CACHE_DIR)

    return _backend
