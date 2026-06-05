from typing import List, Optional

from sentence_transformers import CrossEncoder

from app.core.config import settings

_reranker: Optional["LegalReranker"] = None


class LegalReranker:
    """Cross-Encoder reranker using BGE-reranker for legal document precision."""

    def __init__(self):
        self.model = CrossEncoder(
            settings.RERANKER_MODEL_NAME,
            device=settings.RERANKER_DEVICE,
        )

    def rerank(self, query: str, candidates: List[dict]) -> List[dict]:
        """Score (query, doc) pairs and return re-sorted list."""
        if not candidates:
            return []

        pairs = [(query, c["content"]) for c in candidates]
        scores = self.model.predict(pairs)

        for i, c in enumerate(candidates):
            c["rerank_score"] = float(scores[i]) if hasattr(scores, "__iter__") else float(scores[i])

        candidates.sort(key=lambda c: c.get("rerank_score", 0), reverse=True)
        return candidates


def get_reranker() -> LegalReranker:
    global _reranker
    if _reranker is None:
        _reranker = LegalReranker()
    return _reranker
