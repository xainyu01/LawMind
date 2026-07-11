"""API 认证鉴权 — 支持 API Key 和 JWT 双模式."""

import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Security, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

security = HTTPBearer(auto_error=False)


# ---- API Key 认证 ----

def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")) -> bool:
    """验证 API Key（通过 X-API-Key 请求头）。"""
    if not settings.AUTH_ENABLED:
        return True

    if not x_api_key or x_api_key not in settings.API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


# ---- JWT 认证 ----

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """生成 JWT Token。"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """验证 JWT Token（通过 Authorization: Bearer 头）。"""
    if not settings.AUTH_ENABLED:
        return {}

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---- 统一认证依赖 ----

def verify_auth(
    x_api_key: str = Header(None, alias="X-API-Key"),
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """统一认证入口：根据 AUTH_MODE 选择认证方式。

    - api_key: 仅验证 X-API-Key
    - jwt: 仅验证 Bearer Token
    - both: 任一通过即可
    """
    if not settings.AUTH_ENABLED:
        return {}

    mode = settings.AUTH_MODE

    if mode == "api_key":
        if not x_api_key or x_api_key not in settings.API_KEYS:
            raise HTTPException(status_code=401, detail="Invalid or missing API Key")
        return {"method": "api_key"}

    if mode == "jwt":
        if credentials is None:
            raise HTTPException(status_code=401, detail="Missing authorization token")
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.JWT_SECRET,
                algorithms=["HS256"],
            )
            payload["method"] = "jwt"
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    if mode == "both":
        # 任一通过即可
        if x_api_key and x_api_key in settings.API_KEYS:
            return {"method": "api_key"}
        if credentials:
            try:
                payload = jwt.decode(
                    credentials.credentials,
                    settings.JWT_SECRET,
                    algorithms=["HS256"],
                )
                payload["method"] = "jwt"
                return payload
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                pass
        raise HTTPException(status_code=401, detail="Authentication required (API Key or JWT)")

    raise HTTPException(status_code=500, detail=f"Unknown AUTH_MODE: {mode}")
