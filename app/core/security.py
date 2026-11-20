import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import HTTPException, status

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def api_key_matches(api_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(api_key), stored_hash)


def create_access_token(*, user_id: UUID, role: str, is_demo: bool) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    payload = {
        "sub": str(user_id),
        "role": role,
        "is_demo": is_demo,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
