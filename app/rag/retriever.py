import os
import pickle
from typing import List, Dict, Optional

import bm25s
import jieba
import numpy as np

from app.core.config import settings
from app.rag import vector_store

_retriever: Optional["HybridRetriever"] = None

BM25_CACHE_DIR = os.path.join(settings.CHROMA_PERSIST_DIR, "bm25_cache")


def _jieba_tokenize(texts: List[str]) -> List[List[str]]:
    """Tokenize Chinese texts with jieba, return list of token lists."""
    return [list(jieba.cut(t)) for t in texts]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度。"""
    a_np = np.array(a)
    b_np = np.array(b)
    dot = np.dot(a_np, b_np)
    norm = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    return dot / norm if norm > 0 else 0.0


def mmr_rerank(
    query_embedding: List[float],
    candidates: List[dict],
    lambda_param: float = 0.5,
    top_k: int = 5,
) -> List[dict]:
    """MMR 去重：平衡相关性与多样性。

    lambda_param: 0 = 纯多样性, 1 = 纯相关性
    """
    if not candidates:
        return []

    selected = []
    remaining = candidates.copy()

    while len(selected) < top_k and remaining:
        best_score = -1
        best_idx = -1

        for i, cand in enumerate(remaining):
            # 相关性分数（使用 RRF 分数）
            relevance = cand.get("rrf_score", 0)

            # 与已选结果的最大相似度
            max_sim = 0
            for sel in selected:
                if "embedding" in cand and "embedding" in sel:
                    sim = _cosine_similarity(cand["embedding"], sel["embedding"])
                    max_sim = max(max_sim, sim)

            # MMR 分数
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        if best_idx >= 0:
            selected.append(remaining.pop(best_idx))

    return selected


class HybridRetriever:
    """BM25 + vector hybrid retrieval with Reciprocal Rank Fusion.

    BM25 索引首次构建后持久化到磁盘，后续启动直接加载，大幅减少启动时间。
    """

    def __init__(self):
        self._bm25: Optional[bm25s.BM25] = None
        self._bm25_doc_ids: List[str] = []
        self._doc_count: int = -1
        self._loaded = False

    def _needs_rebuild(self) -> bool:
        return self._bm25 is None or vector_store.get_collection_count() != self._doc_count

    def _try_load_cache(self) -> bool:
        """尝试从磁盘加载缓存的 BM25 索引."""
        index_path = os.path.join(BM25_CACHE_DIR, "bm25_idx.pkl")
        ids_path = os.path.join(BM25_CACHE_DIR, "doc_ids.pkl")
        count_path = os.path.join(BM25_CACHE_DIR, "doc_count.txt")

        if not all(os.path.exists(p) for p in [index_path, ids_path, count_path]):
            return False

        try:
            with open(count_path) as f:
                cached_count = int(f.read())
            if cached_count != vector_store.get_collection_count():
                return False

            with open(ids_path, "rb") as f:
                self._bm25_doc_ids = pickle.load(f)
            self._bm25 = bm25s.BM25.load(index_path)
            self._doc_count = cached_count
            return True
        except Exception:
            return False

    def _save_cache(self) -> None:
        """持久化 BM25 索引到磁盘."""
        if self._bm25 is None:
            return
        os.makedirs(BM25_CACHE_DIR, exist_ok=True)
        self._bm25.save(os.path.join(BM25_CACHE_DIR, "bm25_idx.pkl"))
        with open(os.path.join(BM25_CACHE_DIR, "doc_ids.pkl"), "wb") as f:
            pickle.dump(self._bm25_doc_ids, f)
        with open(os.path.join(BM25_CACHE_DIR, "doc_count.txt"), "w") as f:
            f.write(str(self._doc_count))

    def _build_bm25(self) -> None:
        all_data = vector_store.get_all_documents()
        ids = all_data.get("ids", [])
        if not ids:
            self._bm25 = None
            self._bm25_doc_ids = []
            self._doc_count = 0
            return

        corpus = all_data.get("documents", [])
        self._bm25_doc_ids = list(ids)
        self._doc_count = len(ids)

        tokens = _jieba_tokenize(corpus)
        self._bm25 = bm25s.BM25()
        self._bm25.index(tokens, show_progress=False)
        self._save_cache()

    def _ensure_index(self) -> None:
        if self._needs_rebuild():
            if not self._loaded:
                if self._try_load_cache():
                    self._loaded = True
                    return
                self._loaded = True
            self._build_bm25()

    def search(self, query: str, top_k: int | None = None, filter_repealed: bool = True) -> List[dict]:
        if top_k is None:
            top_k = settings.FINAL_TOP_K
        self._ensure_index()

        total_docs = max(self._doc_count, 1)

        # 过滤已废止法条的条件
        where_filter = None
        if filter_repealed:
            where_filter = {"status": {"$ne": "repealed"}}

        # --- BM25 ---
        bm25_rank: Dict[str, int] = {}
        if self._bm25 is not None:
            bm25_k = min(settings.BM25_TOP_K, self._doc_count)
            query_tokens = _jieba_tokenize([query])
            results, _scores = self._bm25.retrieve(query_tokens, k=bm25_k, show_progress=False)
            for rank, idx in enumerate(results[0]):
                doc_id = self._bm25_doc_ids[idx]
                bm25_rank[doc_id] = rank + 1  # 1-indexed

        # --- Vector ---
        vector_k = min(settings.VECTOR_TOP_K, total_docs)
        vector_hits = vector_store.search(query, top_k=vector_k, where=where_filter)
        vector_rank: Dict[str, int] = {}
        for rank, hit in enumerate(vector_hits):
            vector_rank[hit["id"]] = rank + 1

        # --- RRF fusion ---
        rrf_scores: Dict[str, float] = {}
        doc_store: Dict[str, dict] = {}
        k = 60

        for doc_id, rank in bm25_rank.items():
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank)

        for doc_id, rank in vector_rank.items():
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank)

        # Build doc lookup from vector hits (they have content + metadata)
        for hit in vector_hits:
            doc_store[hit["id"]] = hit

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)

        fused = []
        for doc_id in sorted_ids[:top_k * 2]:  # 多取一些用于 MMR 筛选
            entry = doc_store.get(doc_id, {"id": doc_id, "content": "", "metadata": {}, "distance": None})
            entry["rrf_score"] = rrf_scores[doc_id]
            # 如果启用了过滤，跳过已废止法条
            if filter_repealed and entry.get("metadata", {}).get("status") == "repealed":
                continue
            fused.append(entry)

        # MMR 去重
        if settings.MMR_ENABLED and len(fused) > top_k:
            # 获取查询向量用于 MMR
            from app.rag.embedding import get_embedding
            query_emb = get_embedding(query)
            # 获取候选文档的向量（从 ChromaDB 查询）
            candidate_ids = [e["id"] for e in fused[:top_k * 2]]
            if candidate_ids:
                emb_data = vector_store.get_embeddings_by_ids(candidate_ids)
                for entry in fused:
                    if entry["id"] in emb_data:
                        entry["embedding"] = emb_data[entry["id"]]
                fused = mmr_rerank(
                    query_embedding=query_emb,
                    candidates=fused,
                    lambda_param=settings.MMR_LAMBDA,
                    top_k=top_k,
                )

        return fused[:top_k]


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
