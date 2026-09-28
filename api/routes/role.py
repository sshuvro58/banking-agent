# routes/role.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Role
from schemas import RoleCreate, RoleOut, RoleUpdate

router = APIRouter(prefix="/role", tags=["roles"])


@router.get("/get_all", response_model=list[RoleOut])
def list_roles(db: DBSession = Depends(get_db)):
    print("Calling list_roles")
    return db.query(Role).all()


@router.get("/get/{role_id}", response_model=RoleOut)
def get_role(role_id: int, db: DBSession = Depends(get_db)):
    print("Calling get_role")
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.post("/create", response_model=RoleOut, status_code=201)
def create_role(payload: RoleCreate, db: DBSession = Depends(get_db)):
    print("Calling create_role")
    role = Role(**payload.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.patch("/update/{role_id}", response_model=RoleOut)
def update_role(role_id: int, payload: RoleUpdate, db: DBSession = Depends(get_db)):
    print("Calling update_role")
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(role, field, value)
    db.commit()
    db.refresh(role)
    return role


@router.delete("/delete/{role_id}", status_code=204)
def delete_role(role_id: int, db: DBSession = Depends(get_db)):
    print("Calling delete_role")
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    db.delete(role)
    db.commit()
