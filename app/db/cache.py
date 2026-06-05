"""语义缓存 — 基于 embedding 相似度的 LLM 回答缓存."""

import hashlib
import json
import logging
import time
from typing import List, Optional

import numpy as np

from app.core.config import settings
from app.db.backend import get_backend

logger = logging.getLogger(__name__)

# 缓存前缀
CACHE_EMBED_PREFIX = "cache:emb:"
CACHE_DATA_PREFIX = "cache:data:"
CACHE_INDEX_KEY = "cache:index"  # 存储所有缓存 key 的列表

INTENT_TTL_MAP = {
    "statute_lookup": settings.STATUTE_CACHE_TTL,
    "case_analysis": settings.CASE_CACHE_TTL,
    "legal_qa": settings.LEGAL_QA_CACHE_TTL,
    "contract_review": settings.CONTRACT_CACHE_TTL,
}


class SemanticCache:
    """语义缓存：相似问题命中时直接返回缓存答案，跳过 LLM 调用."""

    def __init__(self):
        self._backend = get_backend()

    def _cache_key(self, text: str) -> str:
        normalized = text.strip().lower()
        return hashlib.md5(normalized.encode()).hexdigest()

    def store(
        self,
        query_embedding: np.ndarray,
        answer_data: dict,
        intent: str = "legal_qa",
    ) -> None:
        """存储缓存：embedding + 回答数据."""
        if intent == "chitchat":
            return  # 闲聊不缓存

        key = self._cache_key(answer_data.get("query", ""))
        ttl = INTENT_TTL_MAP.get(intent, settings.LEGAL_QA_CACHE_TTL)

        # 存储 embedding
        emb_bytes = query_embedding.astype(np.float32).tobytes()
        self._backend.set(f"{CACHE_EMBED_PREFIX}{key}", emb_bytes, ttl=ttl)

        # 存储回答数据
        data = {
            "answer": answer_data.get("answer", ""),
            "sources": answer_data.get("sources", []),
            "intent": intent,
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._backend.set(
            f"{CACHE_DATA_PREFIX}{key}",
            json.dumps(data, ensure_ascii=False),
            ttl=ttl,
        )

        # 更新索引
        self._add_to_index(key, ttl)

        logger.debug("缓存已存储: %s (TTL=%ds)", key[:8], ttl)

    def _add_to_index(self, key: str, ttl: int) -> None:
        """将 key 加入索引列表."""
        raw = self._backend.get(CACHE_INDEX_KEY)
        index = json.loads(raw) if raw else {}
        index[key] = int(time.time()) + ttl
        # 清理过期条目
        now = int(time.time())
        index = {k: v for k, v in index.items() if v > now}
        self._backend.set(CACHE_INDEX_KEY, json.dumps(index), ttl=max(ttl, 86400))

    def lookup_by_embedding(
        self, query_embedding: np.ndarray
    ) -> Optional[dict]:
        """通过 embedding 相似度查找缓存，返回命中结果或 None."""
        raw = self._backend.get(CACHE_INDEX_KEY)
        if not raw:
            return None

        index = json.loads(raw)
        now = int(time.time())
        best_score = 0.0
        best_key = None

        for key, expire_at in index.items():
            if expire_at <= now:
                continue
            emb_bytes = self._backend.get(f"{CACHE_EMBED_PREFIX}{key}")
            if emb_bytes is None:
                continue
            cached_emb = np.frombuffer(emb_bytes, dtype=np.float32)
            # 余弦相似度
            score = float(
                np.dot(query_embedding, cached_emb)
                / (np.linalg.norm(query_embedding) * np.linalg.norm(cached_emb) + 1e-8)
            )
            if score > best_score:
                best_score = score
                best_key = key

        if best_key and best_score >= settings.SEMANTIC_CACHE_THRESHOLD:
            data_raw = self._backend.get(f"{CACHE_DATA_PREFIX}{best_key}")
            if data_raw:
                data = json.loads(data_raw)
                data["similarity"] = best_score
                logger.info("缓存命中: %.4f (阈值 %.2f)", best_score, settings.SEMANTIC_CACHE_THRESHOLD)
                return data

        return None
