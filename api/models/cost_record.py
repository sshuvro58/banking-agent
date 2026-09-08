# models/cost_record.py
import datetime
import decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.session import Session


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = {"schema": "banking"}

    cost_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("banking.sessions.session_id"))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column()
    output_tokens: Mapped[int] = mapped_column()
    estimated_cost: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="cost_records")
