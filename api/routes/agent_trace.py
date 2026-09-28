# routes/agent_trace.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import AgentTrace
from schemas import AgentTraceCreate, AgentTraceOut, AgentTraceUpdate

router = APIRouter(prefix="/agent-trace", tags=["agent-traces"])


@router.get("/get_all", response_model=list[AgentTraceOut])
def list_agent_traces(db: DBSession = Depends(get_db)):
    print("Calling list_agent_traces")
    return db.query(AgentTrace).all()


@router.get("/get/{trace_id}", response_model=AgentTraceOut)
def get_agent_trace(trace_id: int, db: DBSession = Depends(get_db)):
    print("Calling get_agent_trace")
    trace = db.get(AgentTrace, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Agent trace not found")
    return trace


@router.post("/create", response_model=AgentTraceOut, status_code=201)
def create_agent_trace(payload: AgentTraceCreate, db: DBSession = Depends(get_db)):
    print("Calling create_agent_trace")
    trace = AgentTrace(**payload.model_dump())
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace


@router.patch("/update/{trace_id}", response_model=AgentTraceOut)
def update_agent_trace(trace_id: int, payload: AgentTraceUpdate, db: DBSession = Depends(get_db)):
    print("Calling update_agent_trace")
    trace = db.get(AgentTrace, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Agent trace not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(trace, field, value)
    db.commit()
    db.refresh(trace)
    return trace


@router.delete("/delete/{trace_id}", status_code=204)
def delete_agent_trace(trace_id: int, db: DBSession = Depends(get_db)):
    print("Calling delete_agent_trace")
    trace = db.get(AgentTrace, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Agent trace not found")
    db.delete(trace)
    db.commit()
