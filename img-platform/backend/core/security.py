from datetime import datetime, timedelta, timezone
from typing import Optional
import os

from dotenv import load_dotenv
load_dotenv()

import bcrypt
import jwt
from pydantic import BaseModel

# ─── 配置 ───────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable must be set. "
        "Generate one with: openssl rand -hex 32"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时


# ─── 密码工具 ───────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码是否匹配"""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


# ─── JWT Token ──────────────────────────────────────────────────────────────
class TokenData(BaseModel):
    user_id: int
    username: str
    is_admin: bool = False


def create_access_token(data: TokenData, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT access token"""
    to_encode = {
        "user_id": data.user_id,
        "username": data.username,
        "is_admin": data.is_admin,
    }
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[TokenData]:
    """解码 JWT token，返回 None 表示无效"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(
            user_id=payload["user_id"],
            username=payload["username"],
            is_admin=payload.get("is_admin", False),
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
