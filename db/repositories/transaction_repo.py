"""
Transaction Repository — queries for transaction history and statements[cite: 1].
Used by the Transactions MCP Server.
"""
import logging
from datetime import datetime, timezone
from db.connection import db

logger = logging.getLogger("transaction_repo")


class TransactionRepo:

    async def get_transactions(
        self, account_id: str, limit: int = 10, category: str = ""
    ) -> list[dict]:
        """Retrieve recent transactions for an account with optional category filtering[cite: 1]."""
        logger.debug("Calling TransactionRepo.get_transactions")
        rows = await db.fetch(
            """
            SELECT transaction_id, account_id, type, amount, balance_after,
                   description, category, reference_id, status,
                   transaction_date, created_at
            FROM banking.transactions
            WHERE account_id = $1
              AND ($2 = '' OR category = $2)
            ORDER BY transaction_date DESC
            LIMIT $3
            """,
            account_id,
            category,
            limit,
        )
        results = []
        for r in rows:
            d = dict(r)
            d["amount"] = float(d["amount"])
            if d.get("balance_after") is not None:
                d["balance_after"] = float(d["balance_after"])
            d["transaction_date"] = str(d["transaction_date"])
            d["created_at"] = str(d["created_at"])
            results.append(d)
        return results

    async def get_statement(
        self, account_id: str, month: int | None = None, year: int | None = None
    ) -> dict:
        """Generate account statement containing aggregation metrics, closing balance, and transaction history[cite: 1]."""
        logger.debug("Calling TransactionRepo.get_statement")
        now = datetime.now(timezone.utc)
        target_month = month if month is not None else now.month
        target_year = year if year is not None else now.year
        start_date = f"{target_year:04d}-{target_month:02d}-01"

        # 1. Aggregation metrics (COUNT, SUM credits, SUM debits)
        summary_row = await db.fetchrow(
            """
            SELECT
                COUNT(*) AS txn_count,
                COALESCE(SUM(CASE WHEN type = 'credit' THEN amount ELSE 0 END), 0) AS total_credits,
                COALESCE(SUM(CASE WHEN type = 'debit' THEN amount ELSE 0 END), 0) AS total_debits
            FROM banking.transactions
            WHERE account_id = $1
              AND DATE_TRUNC('month', transaction_date) = DATE_TRUNC('month', $2::DATE)
            """,
            account_id,
            start_date,
        )

        # 2. Transaction list for the statement period
        tx_rows = await db.fetch(
            """
            SELECT transaction_id, account_id, type, amount, balance_after,
                   description, category, reference_id, status,
                   transaction_date, created_at
            FROM banking.transactions
            WHERE account_id = $1
              AND DATE_TRUNC('month', transaction_date) = DATE_TRUNC('month', $2::DATE)
            ORDER BY transaction_date DESC
            """,
            account_id,
            start_date,
        )

        transactions = []
        for r in tx_rows:
            d = dict(r)
            d["amount"] = float(d["amount"])
            if d.get("balance_after") is not None:
                d["balance_after"] = float(d["balance_after"])
            d["transaction_date"] = str(d["transaction_date"])
            d["created_at"] = str(d["created_at"])
            transactions.append(d)

        # 3. Current closing balance from accounts table[cite: 1]
        balance_val = await db.fetchval(
            """
            SELECT balance
            FROM banking.accounts
            WHERE account_id = $1
            """,
            account_id,
        )
        closing_balance = float(balance_val) if balance_val is not None else 0.0

        return {
            "account_id": account_id,
            "closing_balance": closing_balance,
            "total_credits": float(summary_row["total_credits"]) if summary_row else 0.0,
            "total_debits": float(summary_row["total_debits"]) if summary_row else 0.0,
            "transaction_count": int(summary_row["txn_count"]) if summary_row else 0,
            "transactions": transactions,
        }


# Singleton
transaction_repo = TransactionRepo()