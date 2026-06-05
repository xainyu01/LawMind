from typing import List

from sentence_transformers import SentenceTransformer

from app.core.config import settings


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
