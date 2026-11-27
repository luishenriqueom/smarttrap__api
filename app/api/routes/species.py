from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_writer
from app.db.models import CaptureAnnotation, Species, User
from app.db.session import get_db
from app.schemas import SpeciesCreate, SpeciesOut, SpeciesUpdate

router = APIRouter(prefix="/species", tags=["species"])


@router.get("", response_model=list[SpeciesOut])
def list_species(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Species]:
    del user
    return list(db.scalars(select(Species).order_by(Species.position, Species.name)).all())


@router.post("", response_model=SpeciesOut, status_code=201)
def create_species(
    body: SpeciesCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> Species:
    del user
    name = body.name.strip()
    if db.scalar(select(Species.id).where(func.lower(Species.name) == name.lower())) is not None:
        raise HTTPException(status_code=409, detail="Essa espécie já existe")
    position = db.scalar(select(func.coalesce(func.max(Species.position), -1)))
    row = Species(name=name, position=int(position) + 1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{species_id}", response_model=SpeciesOut)
def update_species(
    species_id: UUID,
    body: SpeciesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> Species:
    del user
    row = db.get(Species, species_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Espécie não encontrada")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Informe o nome da espécie")
    taken = db.scalar(select(Species.id).where(func.lower(Species.name) == name.lower(), Species.id != row.id))
    if taken is not None:
        raise HTTPException(status_code=409, detail="Essa espécie já existe")
    row.name = name
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{species_id}", status_code=204)
def delete_species(
    species_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> None:
    del user
    row = db.get(Species, species_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Espécie não encontrada")
    used = db.scalar(select(func.count()).select_from(CaptureAnnotation).where(CaptureAnnotation.species_id == row.id))
    if used:
        raise HTTPException(status_code=409, detail="Essa espécie já está marcada em fotos")
    db.delete(row)
    db.commit()
