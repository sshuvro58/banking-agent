# routes/cost_record.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import CostRecord
from schemas import CostRecordCreate, CostRecordOut, CostRecordUpdate

router = APIRouter(prefix="/cost-record", tags=["cost-records"])


@router.get("/get_all", response_model=list[CostRecordOut])
def list_cost_records(db: DBSession = Depends(get_db)):
    return db.query(CostRecord).all()


@router.get("/get/{cost_id}", response_model=CostRecordOut)
def get_cost_record(cost_id: int, db: DBSession = Depends(get_db)):
    cost_record = db.get(CostRecord, cost_id)
    if cost_record is None:
        raise HTTPException(status_code=404, detail="Cost record not found")
    return cost_record


@router.post("/create", response_model=CostRecordOut, status_code=201)
def create_cost_record(payload: CostRecordCreate, db: DBSession = Depends(get_db)):
    cost_record = CostRecord(**payload.model_dump())
    db.add(cost_record)
    db.commit()
    db.refresh(cost_record)
    return cost_record


@router.patch("/update/{cost_id}", response_model=CostRecordOut)
def update_cost_record(cost_id: int, payload: CostRecordUpdate, db: DBSession = Depends(get_db)):
    cost_record = db.get(CostRecord, cost_id)
    if cost_record is None:
        raise HTTPException(status_code=404, detail="Cost record not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cost_record, field, value)
    db.commit()
    db.refresh(cost_record)
    return cost_record


@router.delete("/delete/{cost_id}", status_code=204)
def delete_cost_record(cost_id: int, db: DBSession = Depends(get_db)):
    cost_record = db.get(CostRecord, cost_id)
    if cost_record is None:
        raise HTTPException(status_code=404, detail="Cost record not found")
    db.delete(cost_record)
    db.commit()
