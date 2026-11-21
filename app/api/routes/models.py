from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_writer
from app.db.models import TrainedModel, User
from app.db.session import get_db
from app.schemas import ModelOut
from app.services.training import run_training

router = APIRouter(prefix="/models", tags=["models"])


def _out(row: TrainedModel) -> ModelOut:
    return ModelOut(
        id=row.id,
        status=row.status,
        sha256=row.sha256,
        class_labels=list(row.class_labels or []),
        input_size=row.input_size,
        window=row.window,
        stride=row.stride,
        error=row.error,
        created_at=row.created_at,
    )


@router.get("", response_model=list[ModelOut])
def list_models(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ModelOut]:
    del user
    rows = db.scalars(select(TrainedModel).order_by(TrainedModel.created_at.desc())).all()
    return [_out(row) for row in rows]


@router.post("/train", response_model=ModelOut, status_code=202)
def train_model(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> ModelOut:
    del user
    if not settings.ei_api_key or not settings.ei_project_id or not settings.ei_learn_id:
        raise HTTPException(status_code=422, detail="Edge Impulse não está configurado")
    busy = db.scalar(select(TrainedModel.id).where(TrainedModel.status == "training"))
    if busy is not None:
        raise HTTPException(status_code=409, detail="Já existe um treino em andamento")
    row = TrainedModel(status="training", class_labels=[])
    db.add(row)
    db.commit()
    db.refresh(row)
    background.add_task(run_training, row.id)
    return _out(row)


@router.get("/{model_id}", response_model=ModelOut)
def get_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelOut:
    del user
    row = db.get(TrainedModel, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    return _out(row)
