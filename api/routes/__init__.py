# routes/__init__.py
from routes.account import router as account_router
from routes.agent_trace import router as agent_trace_router
from routes.audit_log import router as audit_log_router
from routes.conversation_message import router as conversation_message_router
from routes.cost_record import router as cost_record_router
from routes.customer import router as customer_router
from routes.customer_role import router as customer_role_router
from routes.pii_redaction_map import router as pii_redaction_map_router
from routes.role import router as role_router
from routes.service_request import router as service_request_router
from routes.session import router as session_router
from routes.transaction import router as transaction_router

routers = [
    customer_router,
    account_router,
    transaction_router,
    service_request_router,
    session_router,
    conversation_message_router,
    agent_trace_router,
    cost_record_router,
    pii_redaction_map_router,
    audit_log_router,
    role_router,
    customer_role_router,
]

__all__ = ["routers"]
