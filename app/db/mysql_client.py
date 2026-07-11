"""MySQL 客户端 — SQLAlchemy 引擎、会话管理、建表."""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.MYSQL_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖：获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表（幂等操作）。"""
    from app.db import models  # noqa: F401 — 触发模型注册
    Base.metadata.create_all(bind=engine)
    logger.info("mysql_tables_created")
