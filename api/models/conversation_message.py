# models/conversation_message.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.session import Session


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = {"schema": "banking"}

    message_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("banking.sessions.session_id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    agent_used: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="conversation_messages")
