# models/transaction.py
import datetime
import decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.account import Account


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = {"schema": "banking"}

    transaction_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("banking.accounts.account_id"))
    type: Mapped[str] = mapped_column(String(10))
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2))
    balance_after: Mapped[decimal.Decimal | None] = mapped_column(Numeric(15, 2))
    description: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'completed'"))
    transaction_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(back_populates="transactions")
