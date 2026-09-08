# models/role.py
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.customer_role import CustomerRole


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "banking"}

    role_id: Mapped[int] = mapped_column(primary_key=True)
    role_name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(String(200))

    customer_roles: Mapped[list["CustomerRole"]] = relationship(back_populates="role", passive_deletes=True)
