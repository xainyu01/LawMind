"""认证模块 — Access Token + Refresh Token 双令牌方案.

- Access Token：短命（60分钟），用于 API 请求认证
- Refresh Token：长命（7天），用于刷新 Access Token，存 MySQL 支持吊销
- 密码存储：bcrypt 哈希
"""

import uuid
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


# ---- 密码工具 ----

def hash_password(password: str) -> str:
    """bcrypt 哈希密码。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码。"""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---- Token 生成 ----

def create_access_token(user_id: int, username: str, role: str) -> str:
    """生成 Access Token（短命）。"""
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_ACCESS_SECRET, algorithm="HS256")


def create_refresh_token(user_id: int, db) -> tuple[str, str]:
    """生成 Refresh Token 并存入数据库。

    Returns:
        (token_string, jti)
    """
    from app.db.models import RefreshToken

    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
    }
    token = jwt.encode(payload, settings.JWT_REFRESH_SECRET, algorithm="HS256")

    # 存入数据库（支持吊销）
    refresh_record = RefreshToken(
        user_id=user_id,
        token_jti=jti,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
    )
    db.add(refresh_record)
    db.commit()

    return token, jti


# ---- Token 验证 ----

def verify_access_token(token: str) -> dict:
    """验证 Access Token，返回 payload。"""
    try:
        payload = jwt.decode(token, settings.JWT_ACCESS_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid access token")


def verify_refresh_token(token: str, db) -> dict:
    """验证 Refresh Token（检查签名 + 数据库存在性）。"""
    from app.db.models import RefreshToken

    try:
        payload = jwt.decode(token, settings.JWT_REFRESH_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # 检查数据库中是否存在（未被吊销）
    jti = payload.get("jti")
    record = db.query(RefreshToken).filter(RefreshToken.token_jti == jti).first()
    if not record:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    return payload


# ---- 用户查询 ----

def get_user_by_username(username: str, db):
    """从 MySQL 查询用户。"""
    from app.db.models import User
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(user_id: int, db):
    """从 MySQL 按 ID 查询用户。"""
    from app.db.models import User
    return db.query(User).filter(User.id == user_id).first()


# ---- FastAPI 依赖 ----

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """从 Authorization 头获取当前用户（Access Token）。

    Returns:
        dict: {"user_id": int, "username": str, "role": str}
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_access_token(credentials.credentials)

    # 从数据库查询用户（确认用户仍然存在且活跃）
    from app.db.mysql_client import SessionLocal
    db = SessionLocal()
    try:
        user = get_user_by_id(int(payload["sub"]), db)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return {"user_id": user.id, "username": user.username, "role": user.role}
    finally:
        db.close()


def require_admin(user: dict = Depends(get_current_user)):
    """要求管理员权限。"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
