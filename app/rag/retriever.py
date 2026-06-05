import os
import pickle
from typing import List, Dict, Optional

import bm25s
import jieba

from app.core.config import settings
from app.rag import vector_store

_retriever: Optional["HybridRetriever"] = None

BM25_CACHE_DIR = os.path.join(settings.CHROMA_PERSIST_DIR, "bm25_cache")


def _jieba_tokenize(texts: List[str]) -> List[List[str]]:
    """Tokenize Chinese texts with jieba, return list of token lists."""
    return [list(jieba.cut(t)) for t in texts]


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

    def search(self, query: str, top_k: int | None = None) -> List[dict]:
        if top_k is None:
            top_k = settings.FINAL_TOP_K
        self._ensure_index()

        total_docs = max(self._doc_count, 1)

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
        vector_hits = vector_store.search(query, top_k=vector_k)
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
        for doc_id in sorted_ids[:top_k]:
            entry = doc_store.get(doc_id, {"id": doc_id, "content": "", "metadata": {}, "distance": None})
            entry["rrf_score"] = rrf_scores[doc_id]
            fused.append(entry)

        return fused


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
