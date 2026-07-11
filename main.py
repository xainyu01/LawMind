import uvicorn
from fastapi import FastAPI

from app.api.routes import router as chat_router
from app.core.rate_limit import RateLimitMiddleware
from app.core.config import settings

app = FastAPI(title="法律RAG系统", version="0.3.0")

# 限流中间件
if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)

app.include_router(chat_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
