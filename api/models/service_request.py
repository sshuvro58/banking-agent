# models/service_request.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.account import Account
    from models.customer import Customer


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = {"schema": "banking"}

    request_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("banking.customers.customer_id"))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("banking.accounts.account_id"))
    type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'submitted'"))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer"] = relationship(back_populates="service_requests")
    account: Mapped["Account | None"] = relationship(back_populates="service_requests")
