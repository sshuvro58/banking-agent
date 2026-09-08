# routes/customer.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Customer
from schemas import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/customer", tags=["customers"])


@router.get("/get_all", response_model=list[CustomerOut])
def list_customers(db: DBSession = Depends(get_db)):
    return db.query(Customer).all()


@router.get("/get/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: DBSession = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.post("/create", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerCreate, db: DBSession = Depends(get_db)):
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.patch("/update/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, payload: CustomerUpdate, db: DBSession = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/delete/{customer_id}", status_code=204)
def delete_customer(customer_id: str, db: DBSession = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    db.delete(customer)
    db.commit()
