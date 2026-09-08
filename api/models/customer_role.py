# models/customer_role.py
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.customer import Customer
    from models.role import Role


class CustomerRole(Base):
    __tablename__ = "customer_roles"
    __table_args__ = {"schema": "banking"}

    customer_id: Mapped[str] = mapped_column(
        ForeignKey("banking.customers.customer_id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("banking.roles.role_id", ondelete="CASCADE"), primary_key=True
    )
    granted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship(back_populates="customer_roles")
    role: Mapped["Role"] = relationship(back_populates="customer_roles")
