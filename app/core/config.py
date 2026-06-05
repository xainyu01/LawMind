import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # Embedding
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh")
    EMBEDDING_DEVICE: str = "cuda"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "legal_knowledge"

    # Text splitter
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # Reranker
    RERANKER_MODEL_NAME: str = os.getenv("RERANKER_MODEL_NAME", "BAAI/bge-reranker-base")
    RERANKER_DEVICE: str = "cuda"

    # Retriever
    BM25_TOP_K: int = 10
    VECTOR_TOP_K: int = 10
    FINAL_TOP_K: int = 5
    MIN_RELEVANCE_SCORE: float = 0.1  # 低于此分数的法条不传给 LLM

    # LLM
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048

    # Redis (Phase 4)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")


settings = Settings()
