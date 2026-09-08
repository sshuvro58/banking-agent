# models/customer.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.account import Account
    from models.customer_role import CustomerRole
    from models.service_request import ServiceRequest
    from models.session import Session


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "banking"}

    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(String(255))
    kyc_status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"))
    kyc_last_updated: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")
    service_requests: Mapped[list["ServiceRequest"]] = relationship(back_populates="customer")
    sessions: Mapped[list["Session"]] = relationship(back_populates="customer")
    customer_roles: Mapped[list["CustomerRole"]] = relationship(back_populates="customer", passive_deletes=True)
