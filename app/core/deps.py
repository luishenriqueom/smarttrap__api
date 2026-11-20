from uuid import UUID

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import api_key_matches, decode_access_token
from app.db.models import Gateway, User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Não autenticado", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(payload.get("sub", ""))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Sessão inválida") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return user


def require_writer(user: User = Depends(get_current_user)) -> User:
    if user.is_demo:
        raise HTTPException(status_code=403, detail="A conta de demonstração é somente leitura")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Apenas o SuperAdmin pode fazer isso")
    return user


def get_gateway(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Gateway:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key ausente")
    gateways = db.scalars(select(Gateway)).all()
    for gateway in gateways:
        if api_key_matches(x_api_key, gateway.api_key_hash):
            return gateway
    raise HTTPException(status_code=401, detail="API key inválida")
