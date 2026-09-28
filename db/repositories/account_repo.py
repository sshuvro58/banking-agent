"""
Account Repository — queries for balance enquiries and account listings.
Used later by the Accounts MCP Server.
"""
from db.connection import db


class AccountRepo:

    async def get_balance(self, account_id: str) -> dict | None:
        """Get balance for a specific account."""
        print("Calling AccountRepo.get_balance")
        row = await db.fetchrow(
            """
            SELECT account_id, customer_id, type, balance,
                   currency, status
            FROM banking.accounts
            WHERE account_id = $1
            """,
            account_id,
        )
        if not row:
            return None
        result = dict(row)
        result["balance"] = float(result["balance"])  # Decimal → float
        return result

    async def list_by_customer(self, customer_id: str) -> list[dict]:
        """List all accounts belonging to a customer."""
        print("Calling AccountRepo.list_by_customer")
        rows = await db.fetch(
            """
            SELECT account_id, type, balance, currency, status, opened_date
            FROM banking.accounts
            WHERE customer_id = $1
            ORDER BY opened_date
            """,
            customer_id,
        )
        results = []
        for r in rows:
            d = dict(r)
            d["balance"] = float(d["balance"])      # Decimal → float
            d["opened_date"] = str(d["opened_date"])  # date → string
            results.append(d)
        return results

    async def verify_ownership(self, account_id: str, customer_id: str) -> bool:
        """Check if an account belongs to a customer."""
        print("Calling AccountRepo.verify_ownership")
        owner = await db.fetchval(
            "SELECT customer_id FROM banking.accounts WHERE account_id = $1",
            account_id,
        )
        return owner == customer_id


# Singleton
account_repo = AccountRepo()