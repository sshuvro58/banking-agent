# models/agent_trace.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.session import Session


class AgentTrace(Base):
    __tablename__ = "agent_traces"
    __table_args__ = {"schema": "banking"}

    trace_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("banking.sessions.session_id"))
    agent: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(50))
    tool_calls: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    input_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    latency_ms: Mapped[float] = mapped_column(Float, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="agent_traces")
