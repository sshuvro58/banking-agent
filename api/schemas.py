# schemas.py
import datetime
import decimal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    name: str
    email: str
    phone: str | None
    address: str | None
    kyc_status: str
    kyc_last_updated: datetime.datetime | None
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CustomerCreate(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: str | None = None
    address: str | None = None
    password_hash: str
    kyc_status: str = "pending"
    is_active: bool = True


class CustomerUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    password_hash: str | None = None
    kyc_status: str | None = None
    kyc_last_updated: datetime.datetime | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: str
    customer_id: str
    type: str
    balance: decimal.Decimal
    currency: str
    status: str
    opened_date: datetime.date
    closed_date: datetime.date | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AccountCreate(BaseModel):
    account_id: str
    customer_id: str
    type: str
    balance: decimal.Decimal = decimal.Decimal("0.00")
    currency: str = "USD"
    status: str = "active"


class AccountUpdate(BaseModel):
    type: str | None = None
    balance: decimal.Decimal | None = None
    currency: str | None = None
    status: str | None = None
    closed_date: datetime.date | None = None


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------
class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    account_id: str
    type: str
    amount: decimal.Decimal
    balance_after: decimal.Decimal | None
    description: str
    category: str
    reference_id: str | None
    status: str
    transaction_date: datetime.datetime
    created_at: datetime.datetime


class TransactionCreate(BaseModel):
    transaction_id: str
    account_id: str
    type: str
    amount: decimal.Decimal
    balance_after: decimal.Decimal | None = None
    description: str
    category: str
    reference_id: str | None = None
    status: str = "completed"


class TransactionUpdate(BaseModel):
    status: str | None = None
    balance_after: decimal.Decimal | None = None
    description: str | None = None
    category: str | None = None


# ---------------------------------------------------------------------------
# ServiceRequest
# ---------------------------------------------------------------------------
class ServiceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    customer_id: str
    account_id: str | None
    type: str
    status: str
    details: dict
    notes: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    completed_at: datetime.datetime | None


class ServiceRequestCreate(BaseModel):
    request_id: str
    customer_id: str
    account_id: str | None = None
    type: str
    status: str = "submitted"
    details: dict = {}
    notes: str | None = None


class ServiceRequestUpdate(BaseModel):
    status: str | None = None
    details: dict | None = None
    notes: str | None = None
    completed_at: datetime.datetime | None = None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    customer_id: str
    shared_state: dict
    agent_context: dict
    is_active: bool
    created_at: datetime.datetime
    last_activity: datetime.datetime


class SessionCreate(BaseModel):
    session_id: str
    customer_id: str
    shared_state: dict = {}
    agent_context: dict = {}
    is_active: bool = True


class SessionUpdate(BaseModel):
    shared_state: dict | None = None
    agent_context: dict | None = None
    is_active: bool | None = None
    last_activity: datetime.datetime | None = None


# ---------------------------------------------------------------------------
# ConversationMessage
# ---------------------------------------------------------------------------
class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    session_id: str
    role: str
    content: str
    agent_used: str | None
    created_at: datetime.datetime


class ConversationMessageCreate(BaseModel):
    session_id: str
    role: str
    content: str
    agent_used: str | None = None


class ConversationMessageUpdate(BaseModel):
    content: str | None = None
    agent_used: str | None = None


# ---------------------------------------------------------------------------
# AgentTrace
# ---------------------------------------------------------------------------
class AgentTraceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trace_id: int
    session_id: str
    agent: str
    action: str
    tool_calls: list
    input_tokens: int
    output_tokens: int
    latency_ms: float
    error: str | None
    created_at: datetime.datetime


class AgentTraceCreate(BaseModel):
    session_id: str
    agent: str
    action: str
    tool_calls: list = []
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    error: str | None = None


class AgentTraceUpdate(BaseModel):
    error: str | None = None
    latency_ms: float | None = None


# ---------------------------------------------------------------------------
# CostRecord
# ---------------------------------------------------------------------------
class CostRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cost_id: int
    session_id: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: decimal.Decimal
    created_at: datetime.datetime


class CostRecordCreate(BaseModel):
    session_id: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: decimal.Decimal


class CostRecordUpdate(BaseModel):
    estimated_cost: decimal.Decimal | None = None


# ---------------------------------------------------------------------------
# PiiRedactionMap
# ---------------------------------------------------------------------------
class PiiRedactionMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    map_id: int
    session_id: str
    placeholder: str
    original: str
    pii_type: str
    created_at: datetime.datetime


class PiiRedactionMapCreate(BaseModel):
    session_id: str
    placeholder: str
    original: str
    pii_type: str


class PiiRedactionMapUpdate(BaseModel):
    placeholder: str | None = None
    pii_type: str | None = None


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    customer_id: str | None
    action: str
    resource: str | None
    details: dict
    ip_address: str | None
    created_at: datetime.datetime


class AuditLogCreate(BaseModel):
    customer_id: str | None = None
    action: str
    resource: str | None = None
    details: dict = {}
    ip_address: str | None = None


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------
class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    role_name: str
    description: str | None


class RoleCreate(BaseModel):
    role_name: str
    description: str | None = None


class RoleUpdate(BaseModel):
    role_name: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# CustomerRole
# ---------------------------------------------------------------------------
class CustomerRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    role_id: int
    granted_at: datetime.datetime


class CustomerRoleCreate(BaseModel):
    customer_id: str
    role_id: int
