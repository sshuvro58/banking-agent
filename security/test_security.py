"""
Test the security layer — auth, authorization, PII redaction.
Run: python test_security.py
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.connection import db
from db.repositories.session_repo import session_repo
from security.authentication import create_token, verify_token
from security.authorization import check_authorisation
from security.pii_redaction import pii_redactor


async def test_authentication():
    """Test JWT creation and verification."""
    print("=" * 50)
    print("  Test 1: Authentication")
    print("=" * 50)

    await db.connect()

    # Valid login
    token = await create_token("cust_001", "demo")
    print(f"  Token: {token[:50]}...")

    # Decode manually to verify contents
    from jose import jwt
    from config import jwt_config
    payload = jwt.decode(token, jwt_config.secret_key, algorithms=[jwt_config.algorithm])
    print(f"  Sub: {payload['sub']}")
    print(f"  Name: {payload['name']}")
    print(f"  Roles: {payload['roles']}")

    assert payload["sub"] == "cust_001"
    assert payload["name"] == "Alice Johnson"
    assert "view_accounts" in payload["roles"]
    assert len(payload["roles"]) == 3  # Alice has all 3 roles

    # Invalid customer
    try:
        await create_token("cust_999", "demo")
        assert False, "Should have raised"
    except Exception as e:
        print(f"  Invalid customer: {e.detail}")

    await db.disconnect()
    print("  ✓ Passed\n")


async def test_authorization():
    """Test RBAC checks."""
    print("=" * 50)
    print("  Test 2: Authorization")
    print("=" * 50)

    alice_roles = ["view_accounts", "view_transactions", "request_services"]
    bob_roles = ["view_accounts", "view_transactions"]

    # Alice can do everything
    assert check_authorisation(alice_roles, "balance_enquiry") is True
    print("  Alice → balance_enquiry: ALLOW")
    assert check_authorisation(alice_roles, "change_address") is True
    print("  Alice → change_address: ALLOW")

    # Bob can view but not request services
    assert check_authorisation(bob_roles, "balance_enquiry") is True
    print("  Bob → balance_enquiry: ALLOW")
    assert check_authorisation(bob_roles, "change_address") is False
    print("  Bob → change_address: DENY")
    assert check_authorisation(bob_roles, "request_chequebook") is False
    print("  Bob → request_chequebook: DENY")

    # Unknown action — denied (fail-closed)
    assert check_authorisation(alice_roles, "launch_missiles") is False
    print("  Alice → launch_missiles: DENY (unknown)")

    print("  ✓ Passed\n")


async def test_pii_redaction():
    """Test PII stripping and restoration."""
    print("=" * 50)
    print("  Test 3: PII Redaction")
    print("=" * 50)

    await db.connect()
    session = await session_repo.create_session("cust_001")
    sid = session["session_id"]

    # Redact
    original = "My SSN is 123-45-6789 and email is alice@test.com"
    redacted = await pii_redactor.redact(original, sid)
    print(f"  Original: {original}")
    print(f"  Redacted: {redacted}")

    assert "123-45-6789" not in redacted, "SSN should be redacted"
    assert "alice@test.com" not in redacted, "Email should be redacted"
    assert "[REDACTED_SSN" in redacted
    assert "[REDACTED_EMAIL" in redacted

    # Restore
    restored = await pii_redactor.restore(redacted, sid)
    print(f"  Restored: {restored}")

    assert restored == original, "Restore should return original text"

    # Verify mappings persisted to DB
    mappings = await session_repo.get_pii_mappings(sid)
    print(f"  DB mappings: {len(mappings)} entries")
    assert len(mappings) == 2  # SSN + email

    # Same value in same session → reuses placeholder
    redacted2 = await pii_redactor.redact("Contact me at alice@test.com", sid)
    print(f"  Same email again: {redacted2}")
    # Should use the same placeholder, not create a new one

    await db.disconnect()
    print("  ✓ Passed\n")


async def test_pii_survives_restart():
    """Test that PII mappings survive (simulated) server restart."""
    print("=" * 50)
    print("  Test 4: PII survives restart")
    print("=" * 50)

    await db.connect()
    session = await session_repo.create_session("cust_001")
    sid = session["session_id"]

    # Redact something
    redacted = await pii_redactor.redact("Call me at 555-123-4567", sid)
    print(f"  Redacted: {redacted}")

    # Simulate restart — create a NEW PIIRedactor instance
    from security.pii_redaction import PIIRedactor
    fresh_redactor = PIIRedactor()

    # Restore using the fresh instance (reads from DB, not memory)
    restored = fresh_redactor.restore(redacted, sid)
    restored = await fresh_redactor.restore(redacted, sid)
    print(f"  Restored after 'restart': {restored}")

    assert "555-123-4567" in restored, "Should restore from DB, not memory"

    await db.disconnect()
    print("  ✓ Passed\n")


async def main():
    await test_authentication()
    await test_authorization()
    await test_pii_redaction()
    await test_pii_survives_restart()

    print("=" * 50)
    print("  All security tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())