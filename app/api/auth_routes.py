"""认证路由 — 注册、登录、刷新、登出、用户管理."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_user_by_username,
    get_current_user,
    require_admin,
)
from app.db.mysql_client import get_db
from app.db.models import User, RefreshToken

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])


# ---- 请求/响应模型 ----

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserInfoResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: str | None = None


# ---- 注册 ----

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册，成功后自动登录返回 token。"""
    # 检查用户名长度
    if len(request.username) < 2 or len(request.username) > 50:
        raise HTTPException(status_code=400, detail="用户名长度需在 2-50 之间")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少 6 位")

    # 检查用户名是否已存在
    existing = get_user_by_username(request.username, db)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    # 创建用户
    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user_registered", username=request.username, user_id=user.id)

    # 自动生成 token
    access_token = create_access_token(user.id, user.username, user.role)
    refresh_token, _ = create_refresh_token(user.id, db)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---- 登录 ----

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户登录，返回双令牌。"""
    user = get_user_by_username(request.username, db)
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    access_token = create_access_token(user.id, user.username, user.role)
    refresh_token, _ = create_refresh_token(user.id, db)

    logger.info("user_logged_in", username=request.username, user_id=user.id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---- 刷新 Token ----

@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    """用 Refresh Token 换取新的 Access Token。"""
    payload = verify_refresh_token(request.refresh_token, db)
    user_id = int(payload["sub"])

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # 吊销旧的 refresh token
    jti = payload.get("jti")
    db.query(RefreshToken).filter(RefreshToken.token_jti == jti).delete()

    # 生成新的双令牌
    access_token = create_access_token(user.id, user.username, user.role)
    refresh_token, _ = create_refresh_token(user.id, db)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---- 获取当前用户 ----

@router.get("/me", response_model=UserInfoResponse)
def get_me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    from app.db.mysql_client import SessionLocal
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user["user_id"]).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        return UserInfoResponse(
            id=db_user.id,
            username=db_user.username,
            role=db_user.role,
            is_active=db_user.is_active,
            created_at=db_user.created_at.isoformat() if db_user.created_at else None,
        )
    finally:
        db.close()


# ---- 登出 ----

@router.post("/logout")
def logout(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登出：吊销该用户所有 Refresh Token。"""
    deleted = db.query(RefreshToken).filter(RefreshToken.user_id == user["user_id"]).delete()
    db.commit()
    logger.info("user_logged_out", username=user["username"], revoked_tokens=deleted)
    return {"message": "已登出", "revoked_tokens": deleted}


# ---- 管理员：用户列表 ----

@router.get("/users")
def list_users(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看所有用户。"""
    users = db.query(User).order_by(User.id).all()
    return [u.to_dict() for u in users]


# ---- 管理员：删除用户 ----

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员删除用户。"""
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="不能删除自己")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    logger.info("user_deleted_by_admin", admin=admin["username"], deleted_user=user.username)
    return {"message": f"用户 {user.username} 已删除"}
