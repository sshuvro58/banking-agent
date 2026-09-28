"""
Accounts MCP Server — tools for account-related operations.
Each tool is an async function that calls account_repo.

Pattern:
  1. Define an async handler function
  2. The handler calls the repo
  3. Converts types (Decimal → float, date → str) for JSON
  4. Raises ValueError for expected errors (not found, bad input)
  5. Register the handler with name, description, parameters
"""
from mcp.base import BaseMCPServer
from db.repositories.account_repo import account_repo


# ── Tool handlers ─────────────────────────────────────
# Each handler is an async function with typed parameters.
# Parameter names MUST match the "properties" keys in the
# tool registration below — the LLM generates these names.

async def _balance_enquiry(account_id: str) -> dict:
    """Look up the balance for a given account."""
    print("Calling _balance_enquiry")
    result = await account_repo.get_balance(account_id)
    if not result:
        raise ValueError(f"Account {account_id} not found")
    return result


async def _list_accounts(customer_id: str) -> dict:
    """List all accounts for a customer."""
    print("Calling _list_accounts")
    accounts = await account_repo.list_by_customer(customer_id)
    if not accounts:
        raise ValueError(f"No accounts found for customer {customer_id}")
    return {"customer_id": customer_id, "accounts": accounts}


# ── Build the MCP server ─────────────────────────────
# Server name is used in logs: [MCP:accounts]

accounts_mcp = BaseMCPServer("accounts")

accounts_mcp.register_tool(
    name="balance_enquiry",
    description="Get the current balance of a specific bank account",
    parameters={
        "properties": {
            "account_id": {
                "type": "string",
                "description": "The account ID, e.g. acc_1001",
            }
        },
        "required": ["account_id"],
    },
    handler=_balance_enquiry,
)

accounts_mcp.register_tool(
    name="list_accounts",
    description="List all bank accounts belonging to a customer",
    parameters={
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "The customer ID, e.g. cust_001",
            }
        },
        "required": ["customer_id"],
    },
    handler=_list_accounts,
)