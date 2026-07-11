import os
import json
from dotenv import load_dotenv

load_dotenv()


def _parse_api_keys(raw: str) -> list[str]:
    """解析 API_KEYS 环境变量（JSON 数组或逗号分隔）。"""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [k.strip() for k in raw.split(",") if k.strip()]


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

    # MMR 去重
    MMR_ENABLED: bool = True          # 是否启用 MMR 去重
    MMR_LAMBDA: float = 0.5           # 0=纯多样性, 1=纯相关性

    # LLM
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048

    # Redis / Cache Backend
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    CACHE_BACKEND_TYPE: str = os.getenv("CACHE_BACKEND", "auto")  # auto / redis / disk
    DISK_CACHE_DIR: str = "./data/cache"

    # Conversation Memory
    MAX_MEMORY_TURNS: int = 10       # 每会话最多保留轮数
    SESSION_TTL: int = 3600          # 会话过期时间（秒）

    # Semantic Cache
    SEMANTIC_CACHE_THRESHOLD: float = 0.92  # 缓存命中相似度阈值
    STATUTE_CACHE_TTL: int = 604800        # 法条缓存 7 天（秒）
    CASE_CACHE_TTL: int = 2592000          # 案例缓存 30 天
    LEGAL_QA_CACHE_TTL: int = 604800       # 知识问答缓存 7 天
    CONTRACT_CACHE_TTL: int = 86400        # 合同审查缓存 1 天

    # MySQL
    MYSQL_URL: str = os.getenv("MYSQL_URL", "mysql+pymysql://root:1234@localhost:3306/legal_rag")

    # 认证
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    JWT_ACCESS_SECRET: str = os.getenv("JWT_ACCESS_SECRET", "legal-rag-access-secret-key")
    JWT_REFRESH_SECRET: str = os.getenv("JWT_REFRESH_SECRET", "legal-rag-refresh-secret-key")
    JWT_ACCESS_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))
    API_KEYS: list[str] = _parse_api_keys(os.getenv("API_KEYS", ""))

    # 默认管理员（首次启动自动创建）
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    # 限流
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_PER_HOUR: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))


settings = Settings()
