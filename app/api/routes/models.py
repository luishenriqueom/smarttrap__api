from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_writer
from app.db.models import Device, TrainedModel, User
from app.db.session import get_db
from app.schemas import ModelOut, TrainRequest
from app.services.training import models_root, run_training

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
        images_from=row.images_from,
        images_to=row.images_to,
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
    body: TrainRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> ModelOut:
    del user
    images_from, images_to = _period(body)
    if not settings.ei_api_key or not settings.ei_project_id or not settings.ei_learn_id:
        raise HTTPException(status_code=422, detail="Edge Impulse não está configurado")
    busy = db.scalar(select(TrainedModel.id).where(TrainedModel.status == "training"))
    if busy is not None:
        raise HTTPException(status_code=409, detail="Já existe um treino em andamento")
    row = TrainedModel(status="training", class_labels=[], images_from=images_from, images_to=images_to)
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


@router.delete("/{model_id}", status_code=204)
def delete_model(
    model_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> None:
    del user
    row = db.get(TrainedModel, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    if row.status == "training":
        raise HTTPException(status_code=409, detail="Esse treino ainda está em andamento")
    used = db.scalar(select(func.count()).select_from(Device).where(Device.model_id == row.id))
    if used:
        raise HTTPException(status_code=409, detail="Esse modelo está vinculado a uma armadilha")
    _delete_files(row)
    db.delete(row)
    db.commit()


def _period(body: TrainRequest | None) -> tuple:
    if body is None:
        return None, None
    if body.images_from is not None and body.images_to is not None and body.images_to < body.images_from:
        raise HTTPException(status_code=422, detail="O fim do período é anterior ao início")
    return body.images_from, body.images_to


def _delete_files(row: TrainedModel) -> None:
    root = models_root()
    if row.file_path:
        path = (root / row.file_path).resolve()
        if path.is_relative_to(root) and path.is_file():
            path.unlink()
    meta = (root / f"{row.id}.json").resolve()
    if meta.is_relative_to(root) and meta.is_file():
        meta.unlink()
