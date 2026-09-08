# models/pii_redaction_map.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.session import Session


class PiiRedactionMap(Base):
    __tablename__ = "pii_redaction_map"
    __table_args__ = {"schema": "banking"}

    map_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("banking.sessions.session_id", ondelete="CASCADE"))
    placeholder: Mapped[str] = mapped_column(String(50))
    original: Mapped[str] = mapped_column(String(500))
    pii_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="pii_redaction_map")
