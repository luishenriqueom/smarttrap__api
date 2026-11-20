from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _token(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user_id=user.id, role=user.role, is_demo=user.is_demo),
        user=UserOut.model_validate(user),
    )


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@") or " " in email:
        raise HTTPException(status_code=422, detail="E-mail inválido")
    return email


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    email = _normalize_email(body.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return _token(user)


@router.post("/demo", response_model=TokenOut)
def login_demo(db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.is_demo.is_(True), User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=404, detail="Conta de demonstração indisponível")
    return _token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
