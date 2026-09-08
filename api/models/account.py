# models/account.py
import datetime
import decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.customer import Customer
    from models.service_request import ServiceRequest
    from models.transaction import Transaction


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": "banking"}

    account_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("banking.customers.customer_id"))
    type: Mapped[str] = mapped_column(String(20))
    balance: Mapped[decimal.Decimal] = mapped_column(Numeric(15, 2), server_default=text("0.00"))
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'USD'"))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"))
    opened_date: Mapped[datetime.date] = mapped_column(Date, server_default=func.current_date())
    closed_date: Mapped[datetime.date | None] = mapped_column(Date)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="account")
