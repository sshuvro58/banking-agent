"""
Customer Repository — queries for customer profiles, authentication, and role management.
Used by the Customer & Auth MCP components.
"""
from db.connection import db
import bcrypt


class CustomerRepo:

    async def get_by_id(self, customer_id: str) -> dict | None:
        """Fetch customer details by customer ID."""
        row = await db.fetchrow(
            """
            SELECT customer_id, name, email, phone, address,
                   kyc_status, kyc_last_updated, is_active,
                   created_at, updated_at
            FROM banking.customers
            WHERE customer_id = $1
            """,
            customer_id,
        )
        if not row:
            return None
        result = dict(row)
        if result.get("kyc_last_updated"):
            result["kyc_last_updated"] = str(result["kyc_last_updated"])
        result["created_at"] = str(result["created_at"])
        result["updated_at"] = str(result["updated_at"])
        return result

    async def get_by_email(self, email: str) -> dict | None:
        """Fetch customer details by email address."""
        row = await db.fetchrow(
            """
            SELECT customer_id, name, email, phone, address,
                   kyc_status, kyc_last_updated, is_active,
                   created_at, updated_at
            FROM banking.customers
            WHERE email = $1
            """,
            email,
        )
        if not row:
            return None
        result = dict(row)
        if result.get("kyc_last_updated"):
            result["kyc_last_updated"] = str(result["kyc_last_updated"])
        result["created_at"] = str(result["created_at"])
        result["updated_at"] = str(result["updated_at"])
        return result

    async def get_roles(self, customer_id: str) -> list[str]:
        """Fetch all role names assigned to a customer."""
        rows = await db.fetch(
            """
            SELECT r.role_name
            FROM banking.customer_roles cr
            JOIN banking.roles r ON cr.role_id = r.role_id
            WHERE cr.customer_id = $1
            ORDER BY r.role_name
            """,
            customer_id,
        )
        return [r["role_name"] for r in rows]

    async def get_profile_with_roles(self, customer_id: str) -> dict | None:
        """Fetch consolidated customer profile with aggregated roles from view."""
        row = await db.fetchrow(
            """
            SELECT customer_id, name, email, phone, address,
                   kyc_status, is_active, roles
            FROM banking.v_customer_profile
            WHERE customer_id = $1
            """,
            customer_id,
        )
        if not row:
            return None
        result = dict(row)
        # Handle PostgreSQL array if NULL
        result["roles"] = list(result["roles"]) if result.get("roles") is not None else []
        return result

    async def update_address(self, customer_id: str, new_address: str) -> bool:
        """Update customer's primary address."""
        status = await db.execute(
            """
            UPDATE banking.customers
            SET address = $2
            WHERE customer_id = $1
            """,
            customer_id,
            new_address,
        )
        return status == "UPDATE 1"

    async def update_kyc_status(self, customer_id: str, status: str) -> bool:
        """Update KYC verification status and record the update timestamp."""
        res = await db.execute(
            """
            UPDATE banking.customers
            SET kyc_status = $2,
                kyc_last_updated = NOW()
            WHERE customer_id = $1
            """,
            customer_id,
            status,
        )
        return res == "UPDATE 1"

    async def verify_password(self, customer_id: str, password: str) -> bool:
        """Verify password against stored bcrypt hash, supporting 'demo' shortcut."""
        password_hash = await db.fetchval(
            """
            SELECT password_hash
            FROM banking.customers
            WHERE customer_id = $1
            """,
            customer_id,
        )
        if not password_hash:
            return False

        # Development/testing shortcut
        if password == "demo":
            return True

        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )


# Singleton
customer_repo = CustomerRepo()