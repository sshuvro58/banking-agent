# routes/customer_role.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import CustomerRole
from schemas import CustomerRoleCreate, CustomerRoleOut

router = APIRouter(prefix="/customer-role", tags=["customer-roles"])


@router.get("/get_all", response_model=list[CustomerRoleOut])
def list_customer_roles(db: DBSession = Depends(get_db)):
    print("Calling list_customer_roles")
    return db.query(CustomerRole).all()


@router.post("/create", response_model=CustomerRoleOut, status_code=201)
def assign_role(payload: CustomerRoleCreate, db: DBSession = Depends(get_db)):
    print("Calling assign_role")
    customer_role = CustomerRole(**payload.model_dump())
    db.add(customer_role)
    db.commit()
    db.refresh(customer_role)
    return customer_role


@router.delete("/delete/{customer_id}/{role_id}", status_code=204)
def revoke_role(customer_id: str, role_id: int, db: DBSession = Depends(get_db)):
    print("Calling revoke_role")
    customer_role = db.get(CustomerRole, (customer_id, role_id))
    if customer_role is None:
        raise HTTPException(status_code=404, detail="Customer role not found")
    db.delete(customer_role)
    db.commit()
