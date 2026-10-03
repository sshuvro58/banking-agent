"""
Service MCP Server — tools for service-related operations.
Each tool is an async function that calls service_repo.

Pattern:
  1. Define an async handler function
  2. The handler calls the repo
  3. Converts types (Decimal → float, date → str) for JSON
  4. Raises ValueError for expected errors (not found, bad input)
  5. Register the handler with name, description, parameters
"""
import logging
from mcp.base import BaseMCPServer
from db.repositories.service_repo import service_repo

logger = logging.getLogger("mcp.service")

async def _change_address(customer_id: str, new_address: str) -> dict:
    """Change the address for a specific account."""
    logger.debug("Calling _change_address")
    if not customer_id:
        raise ValueError("customer_id is required")
    if not new_address:
        raise ValueError("new_address is required")
    return await service_repo.change_address(customer_id, new_address)

async def _request_checkbook(customer_id: str, account_id: str, pages: int) -> dict:
    """Request a checkbook for a specific account."""
    logger.debug("Calling _request_checkbook")
    if not customer_id:
        raise ValueError("customer_id is required")
    if not account_id:
        raise ValueError("account_id is required")
    return await service_repo.request_checkbook(customer_id, account_id, pages)

async def _update_kyc(customer_id:str,document_type:str,document_number:str) -> dict:
    """Update KYC information for a specific customer."""
    logger.debug("Calling _update_kyc")
    if not customer_id:
        raise ValueError("customer_id is required")
    if not document_type:
        raise ValueError("document_type is required")
    if not document_number:
        raise ValueError("document_number is required")
    return await service_repo.update_kyc(customer_id, document_type, document_number)


service_mcp = BaseMCPServer("service")

service_mcp.register_tool(
    name="change_address",
    description="Change the address for a specific customer",
    parameters={
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "The customer ID, e.g. cust_1001",
            },
            "new_address": {
                "type": "string",
                "description": "The new address for the customer",
            },
        },
        "required": ["customer_id", "new_address"],
    },
    handler=_change_address,
) 

service_mcp.register_tool(
    name="request_checkbook",
    description="Request a checkbook for a specific account",
    parameters={
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "The customer ID, e.g. cust_1001",
            },
            "account_id": {
                "type": "string",
                "description": "The account ID, e.g. acc_1001",
            },
            "pages": {
                "type": "integer",
                "description": "The number of pages for the checkbook (default 25)",
            },
        },
        "required": ["customer_id", "account_id"],
    },
    handler=_request_checkbook,
)

service_mcp.register_tool(
    name="update_kyc",
    description="Update KYC information for a specific customer",
    parameters={
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "The customer ID, e.g. cust_1001",
            },
            "document_type": {
                "type": "string",
                "description": "The type of document for KYC (e.g., passport, driver's license)",
            },
            "document_number": {
                "type": "string",
                "description": "The document number for KYC",
            },
        },
        "required": ["customer_id", "document_type", "document_number"],
    },
    handler=_update_kyc,
) 