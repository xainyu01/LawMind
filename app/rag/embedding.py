from typing import List, Optional

from sentence_transformers import SentenceTransformer

from app.core.config import settings

_embedder: Optional[BgeEmbedding] = None


class BgeEmbedding:
    def __init__(self):
        self.model = SentenceTransformer(
            settings.EMBEDDING_MODEL_NAME,
            device=settings.EMBEDDING_DEVICE,
            cache_folder="./models",
            local_files_only=False,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()


def get_embedding(text: str) -> List[float]:
    """便捷函数：获取单条文本的 embedding。"""
    global _embedder
    if _embedder is None:
        _embedder = BgeEmbedding()
    return _embedder.embed_query(text)
