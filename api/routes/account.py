# routes/account.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Account
from schemas import AccountCreate, AccountOut, AccountUpdate

router = APIRouter(prefix="/account", tags=["accounts"])


@router.get("/get_all", response_model=list[AccountOut])
def list_accounts(db: DBSession = Depends(get_db)):
    print("Calling list_accounts")
    return db.query(Account).all()


@router.get("/get/{account_id}", response_model=AccountOut)
def get_account(account_id: str, db: DBSession = Depends(get_db)):
    print("Calling get_account")
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/create", response_model=AccountOut, status_code=201)
def create_account(payload: AccountCreate, db: DBSession = Depends(get_db)):
    print("Calling create_account")
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/update/{account_id}", response_model=AccountOut)
def update_account(account_id: str, payload: AccountUpdate, db: DBSession = Depends(get_db)):
    print("Calling update_account")
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/delete/{account_id}", status_code=204)
def delete_account(account_id: str, db: DBSession = Depends(get_db)):
    print("Calling delete_account")
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
