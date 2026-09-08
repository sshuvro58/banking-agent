# models/audit_log.py
import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "banking"}

    log_id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(50))
    resource: Mapped[str | None] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
