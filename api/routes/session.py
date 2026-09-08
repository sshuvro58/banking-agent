# routes/session.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Session as SessionModel
from schemas import SessionCreate, SessionOut, SessionUpdate

router = APIRouter(prefix="/session", tags=["sessions"])


@router.get("/get_all", response_model=list[SessionOut])
def list_sessions(db: DBSession = Depends(get_db)):
    return db.query(SessionModel).all()


@router.get("/get/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/create", response_model=SessionOut, status_code=201)
def create_session(payload: SessionCreate, db: DBSession = Depends(get_db)):
    session = SessionModel(**payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/update/{session_id}", response_model=SessionOut)
def update_session(session_id: str, payload: SessionUpdate, db: DBSession = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    db.commit()
    db.refresh(session)
    return session


@router.delete("/delete/{session_id}", status_code=204)
def delete_session(session_id: str, db: DBSession = Depends(get_db)):
    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
