"""
Service Request Repository — operations for creating and querying service tickets[cite: 1].
Handles customer service workflows including address updates, KYC changes, and chequebook orders[cite: 1].
"""
import json
import uuid
from db.connection import db


class ServiceRepo:

    async def create_request(
        self,
        customer_id: str,
        request_type: str,
        details: dict,
        account_id: str | None = None,
        status: str = "submitted",
    ) -> dict:
        """Insert a service request using a generated request ID and return the record[cite: 1]."""
        print("Calling ServiceRepo.create_request")
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        details_json = json.dumps(details)

        row = await db.fetchrow(
            """
            INSERT INTO banking.service_requests (
                request_id, customer_id, account_id, type, status, details
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            RETURNING request_id, customer_id, account_id, type, status,
                      details, notes, created_at, updated_at, completed_at
            """,
            request_id,
            customer_id,
            account_id,
            request_type,
            status,
            details_json,
        )
        record = dict(row)
        if isinstance(record.get("details"), str):
            record["details"] = json.loads(record["details"])
        record["created_at"] = str(record["created_at"])
        record["updated_at"] = str(record["updated_at"])
        if record.get("completed_at"):
            record["completed_at"] = str(record["completed_at"])
        return record

    async def change_address(self, customer_id: str, new_address: str) -> dict:
        """Fetch old address, update customer record, and create an audit service request[cite: 1]."""
        print("Calling ServiceRepo.change_address")
        old_address = await db.fetchval(
            "SELECT address FROM banking.customers WHERE customer_id = $1",
            customer_id,
        )

        await db.execute(
            """
            UPDATE banking.customers
            SET address = $2
            WHERE customer_id = $1
            """,
            customer_id,
            new_address,
        )

        details = {
            "old_address": old_address,
            "new_address": new_address,
        }
        return await self.create_request(
            customer_id=customer_id,
            request_type="change_address",
            details=details,
            account_id=None,
            status="completed",
        )

    async def request_chequebook(
        self, customer_id: str, account_id: str, pages: int = 25
    ) -> dict:
        """Verify account ownership and create a chequebook service request[cite: 1]."""
        print("Calling ServiceRepo.request_chequebook")
        owner_id = await db.fetchval(
            "SELECT customer_id FROM banking.accounts WHERE account_id = $1",
            account_id,
        )
        if not owner_id or owner_id != customer_id:
            raise ValueError(f"Account {account_id} does not belong to customer {customer_id}")

        details = {
            "pages": pages,
        }
        return await self.create_request(
            customer_id=customer_id,
            request_type="chequebook_request",
            details=details,
            account_id=account_id,
            status="submitted",
        )

    async def update_kyc(
        self, customer_id: str, doc_type: str, doc_number: str
    ) -> dict:
        """Fetch current KYC status, set status to under_review, and log the request[cite: 1]."""
        print("Calling ServiceRepo.update_kyc")
        current_status = await db.fetchval(
            "SELECT kyc_status FROM banking.customers WHERE customer_id = $1",
            customer_id,
        )

        await db.execute(
            """
            UPDATE banking.customers
            SET kyc_status = 'under_review',
                kyc_last_updated = NOW()
            WHERE customer_id = $1
            """,
            customer_id,
        )

        details = {
            "previous_kyc_status": current_status,
            "doc_type": doc_type,
            "doc_number": doc_number,
        }
        return await self.create_request(
            customer_id=customer_id,
            request_type="kyc_update",
            details=details,
            account_id=None,
            status="submitted",
        )

    async def get_requests(self, customer_id: str, limit: int = 10) -> list[dict]:
        """Fetch recent service requests filed by the customer[cite: 1]."""
        print("Calling ServiceRepo.get_requests")
        rows = await db.fetch(
            """
            SELECT request_id, customer_id, account_id, type, status,
                   details, notes, created_at, updated_at, completed_at
            FROM banking.service_requests
            WHERE customer_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            customer_id,
            limit,
        )
        results = []
        for r in rows:
            record = dict(r)
            if isinstance(record.get("details"), str):
                record["details"] = json.loads(record["details"])
            record["created_at"] = str(record["created_at"])
            record["updated_at"] = str(record["updated_at"])
            if record.get("completed_at"):
                record["completed_at"] = str(record["completed_at"])
            results.append(record)
        return results


# Singleton
service_repo = ServiceRepo()