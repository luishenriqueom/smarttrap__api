from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import _normalize_email
from app.core.deps import require_superadmin
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_superadmin)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)).all())


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin),
) -> User:
    email = _normalize_email(body.email)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail")
    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role="common",
        is_demo=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_superadmin),
) -> User:
    from uuid import UUID

    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Usuário não encontrado") from exc
    user = db.get(User, parsed_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    changes = body.model_fields_set
    if "is_active" in changes and body.is_active is False:
        if user.is_demo:
            raise HTTPException(status_code=400, detail="A conta de demonstração não pode ser desativada")
        if user.id == actor.id:
            raise HTTPException(status_code=400, detail="Você não pode desativar a própria conta")
        user.is_active = False
    elif "is_active" in changes and body.is_active is True:
        user.is_active = True

    if "name" in changes and body.name is not None:
        user.name = body.name.strip()
    if "email" in changes and body.email is not None:
        email = _normalize_email(body.email)
        taken = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if taken is not None:
            raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail")
        user.email = email
    if "password" in changes and body.password is not None:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return user
