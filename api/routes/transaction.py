# routes/transaction.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Transaction
from schemas import TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(prefix="/transaction", tags=["transactions"])


@router.get("/get_all", response_model=list[TransactionOut])
def list_transactions(db: DBSession = Depends(get_db)):
    return db.query(Transaction).all()


@router.get("/get/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: str, db: DBSession = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.post("/create", response_model=TransactionOut, status_code=201)
def create_transaction(payload: TransactionCreate, db: DBSession = Depends(get_db)):
    transaction = Transaction(**payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.patch("/update/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: str, payload: TransactionUpdate, db: DBSession = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(transaction, field, value)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/delete/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: str, db: DBSession = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(transaction)
    db.commit()
