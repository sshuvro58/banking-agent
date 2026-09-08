# models/session.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.agent_trace import AgentTrace
    from models.conversation_message import ConversationMessage
    from models.cost_record import CostRecord
    from models.customer import Customer
    from models.pii_redaction_map import PiiRedactionMap


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "banking"}

    session_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("banking.customers.customer_id"))
    shared_state: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    agent_context: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship(back_populates="sessions")
    conversation_messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="session", passive_deletes=True
    )
    agent_traces: Mapped[list["AgentTrace"]] = relationship(back_populates="session")
    cost_records: Mapped[list["CostRecord"]] = relationship(back_populates="session")
    pii_redaction_map: Mapped[list["PiiRedactionMap"]] = relationship(
        back_populates="session", passive_deletes=True
    )
