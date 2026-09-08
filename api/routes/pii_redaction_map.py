# routes/pii_redaction_map.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import PiiRedactionMap
from schemas import PiiRedactionMapCreate, PiiRedactionMapOut, PiiRedactionMapUpdate

router = APIRouter(prefix="/pii-redaction", tags=["pii-redactions"])


@router.get("/get_all", response_model=list[PiiRedactionMapOut])
def list_pii_redactions(db: DBSession = Depends(get_db)):
    return db.query(PiiRedactionMap).all()


@router.get("/get/{map_id}", response_model=PiiRedactionMapOut)
def get_pii_redaction(map_id: int, db: DBSession = Depends(get_db)):
    entry = db.get(PiiRedactionMap, map_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="PII redaction entry not found")
    return entry


@router.post("/create", response_model=PiiRedactionMapOut, status_code=201)
def create_pii_redaction(payload: PiiRedactionMapCreate, db: DBSession = Depends(get_db)):
    entry = PiiRedactionMap(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/update/{map_id}", response_model=PiiRedactionMapOut)
def update_pii_redaction(map_id: int, payload: PiiRedactionMapUpdate, db: DBSession = Depends(get_db)):
    entry = db.get(PiiRedactionMap, map_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="PII redaction entry not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/delete/{map_id}", status_code=204)
def delete_pii_redaction(map_id: int, db: DBSession = Depends(get_db)):
    entry = db.get(PiiRedactionMap, map_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="PII redaction entry not found")
    db.delete(entry)
    db.commit()
