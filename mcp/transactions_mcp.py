"""
Transaction MCP Server — tools for transaction-related operations.
Each tool is an async function that calls transaction_repo.

Pattern:
  1. Define an async handler function
  2. The handler calls the repo
  3. Converts types (Decimal → float, date → str) for JSON
  4. Raises ValueError for expected errors (not found, bad input)
  5. Register the handler with name, description, parameters
"""

import logging
from mcp.base import BaseMCPServer
from db.repositories.transaction_repo import transaction_repo

logger = logging.getLogger("mcp.transactions")

async def _get_transaction(account_id: str, limit: int = 10, category: str = "") -> list[dict]:
    """Get recent transactions for an account, optionally filtered by category."""
    logger.debug("Calling _get_transaction")
    if not account_id:
        raise ValueError("account_id is required")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return await transaction_repo.get_transactions(account_id, limit=limit, category=category)


async def _get_statement(account_id: str, month: int | None = None, year: int | None = None) -> dict:
    """Generate an account statement for a given month and year."""
    logger.debug("Calling _get_statement")
    if not account_id:
        raise ValueError("account_id is required")
    return await transaction_repo.get_statement(account_id, month=month, year=year) 

transactions_mcp = BaseMCPServer("transactions")

transactions_mcp.register_tool(
    name="get_transaction",
    description="Retrieve recent transactions for a specific bank account, optionally filtered by category",
    parameters={
        "properties": {
            "account_id": {
                "type": "string",
                "description": "The account ID, e.g. acc_1001",
            },
            "limit": {
                "type": "integer",
                "description": "The maximum number of transactions to retrieve (default 10)",
            },
            "category": {
                "type": "string",
                "description": "Optional category filter for transactions",
            },
        },
        "required": ["account_id"],
    },
    handler=_get_transaction,
)   


transactions_mcp.register_tool(
    name="get_statement",
    description="Generate an account statement for a specific month and year, including aggregation metrics and transaction history",
    parameters={
        "properties": {
            "account_id": {
                "type": "string",
                "description": "The account ID, e.g. acc_1001",
            },
            "month": {
                "type": "integer",
                "description": "The month for the statement (1-12). Defaults to current month if not provided.",
            },
            "year": {
                "type": "integer",
                "description": "The year for the statement (e.g., 2023). Defaults to current year if not provided.",
            },
        },
        "required": ["account_id"],
    },
    handler=_get_statement,
)
