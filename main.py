import uvicorn
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router as chat_router
from app.api.auth_routes import router as auth_router
from app.core.rate_limit import RateLimitMiddleware
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库和默认管理员。"""
    from app.db.mysql_client import init_db
    from app.core.auth import hash_password, get_user_by_username
    from app.db.mysql_client import SessionLocal
    from app.db.models import User

    init_db()

    # 自动创建默认管理员
    db = SessionLocal()
    try:
        existing = get_user_by_username(settings.ADMIN_USERNAME, db)
        if not existing:
            admin = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info("admin_created", username=settings.ADMIN_USERNAME)
    finally:
        db.close()

    yield


app = FastAPI(title="法律RAG系统", version="0.4.0", lifespan=lifespan)

# 限流中间件
if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)

app.include_router(auth_router)
app.include_router(chat_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
