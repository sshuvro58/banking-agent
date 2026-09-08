# routes/service_request.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import ServiceRequest
from schemas import ServiceRequestCreate, ServiceRequestOut, ServiceRequestUpdate

router = APIRouter(prefix="/service-request", tags=["service-requests"])


@router.get("/get_all", response_model=list[ServiceRequestOut])
def list_service_requests(db: DBSession = Depends(get_db)):
    return db.query(ServiceRequest).all()


@router.get("/get/{request_id}", response_model=ServiceRequestOut)
def get_service_request(request_id: str, db: DBSession = Depends(get_db)):
    service_request = db.get(ServiceRequest, request_id)
    if service_request is None:
        raise HTTPException(status_code=404, detail="Service request not found")
    return service_request


@router.post("/create", response_model=ServiceRequestOut, status_code=201)
def create_service_request(payload: ServiceRequestCreate, db: DBSession = Depends(get_db)):
    service_request = ServiceRequest(**payload.model_dump())
    db.add(service_request)
    db.commit()
    db.refresh(service_request)
    return service_request


@router.patch("/update/{request_id}", response_model=ServiceRequestOut)
def update_service_request(request_id: str, payload: ServiceRequestUpdate, db: DBSession = Depends(get_db)):
    service_request = db.get(ServiceRequest, request_id)
    if service_request is None:
        raise HTTPException(status_code=404, detail="Service request not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(service_request, field, value)
    db.commit()
    db.refresh(service_request)
    return service_request


@router.delete("/delete/{request_id}", status_code=204)
def delete_service_request(request_id: str, db: DBSession = Depends(get_db)):
    service_request = db.get(ServiceRequest, request_id)
    if service_request is None:
        raise HTTPException(status_code=404, detail="Service request not found")
    db.delete(service_request)
    db.commit()
