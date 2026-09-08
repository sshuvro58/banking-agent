# routes/audit_log.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import AuditLog
from schemas import AuditLogCreate, AuditLogOut

router = APIRouter(prefix="/audit-log", tags=["audit-log"])

# Audit log entries are append-only: no update or delete routes are exposed.


@router.get("/get_all", response_model=list[AuditLogOut])
def list_audit_log(db: DBSession = Depends(get_db)):
    return db.query(AuditLog).all()


@router.get("/get/{log_id}", response_model=AuditLogOut)
def get_audit_log_entry(log_id: int, db: DBSession = Depends(get_db)):
    entry = db.get(AuditLog, log_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return entry


@router.post("/create", response_model=AuditLogOut, status_code=201)
def create_audit_log_entry(payload: AuditLogCreate, db: DBSession = Depends(get_db)):
    entry = AuditLog(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
