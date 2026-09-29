"""
Test the Coordinator Agent — full routing + delegation chain.
Run: python test_coordinator.py
"""
import asyncio
import sys
from pathlib import Path

# Allow running this file directly (`python agents/test_coordinator.py`) even
# though it lives in a subdirectory — Python only puts the script's own
# folder on sys.path, not the repo root where db/, agents/, and security/ live.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import db
from db.repositories.session_repo import session_repo
from db.repositories.observability_repo import observability_repo
from agents.coordinator import coordinator


async def test_routing_accounts():
    """Balance question → should route to accounts_agent."""
    print("=" * 60)
    print("  Test 1: Route to accounts_agent")
    print("=" * 60)

    await db.connect()
    session = await session_repo.create_session("cust_001")

    result = await coordinator.handle_message(
        message="What's my account balance?",
        session_id=session["session_id"],
        user_claims={
            "sub": "cust_001",
            "name": "Alice Johnson",
            "roles": ["view_accounts", "view_transactions", "request_services"],
        },
    )

    print(f"  Agent used: {result['agent_used']}")
    print(f"  Reply: {result['reply'][:150]}...")
    print(f"  Cost: ${result['cost']['total_cost_usd']:.6f}")

    assert result["agent_used"] == "accounts_agent", f"Expected accounts_agent, got {result['agent_used']}"
    print("  ✓ Passed\n")
    await db.disconnect()


async def test_routing_transactions():
    """Transaction question → should route to transaction_agent."""
    print("=" * 60)
    print("  Test 2: Route to transaction_agent")
    print("=" * 60)

    await db.connect()
    session = await session_repo.create_session("cust_001")

    result = await coordinator.handle_message(
        message="Show me my recent transactions",
        session_id=session["session_id"],
        user_claims={
            "sub": "cust_001",
            "name": "Alice Johnson",
            "roles": ["view_accounts", "view_transactions", "request_services"],
        },
    )

    print(f"  Agent used: {result['agent_used']}")
    print(f"  Reply: {result['reply'][:150]}...")

    assert result["agent_used"] == "transaction_agent", f"Expected transaction_agent, got {result['agent_used']}"
    print("  ✓ Passed\n")
    await db.disconnect()


async def test_routing_service():
    """Service request → should route to service_agent."""
    print("=" * 60)
    print("  Test 3: Route to service_agent")
    print("=" * 60)

    await db.connect()
    session = await session_repo.create_session("cust_001")

    result = await coordinator.handle_message(
        message="I want to request a cheque book",
        session_id=session["session_id"],
        user_claims={
            "sub": "cust_001",
            "name": "Alice Johnson",
            "roles": ["view_accounts", "view_transactions", "request_services"],
        },
    )

    print(f"  Agent used: {result['agent_used']}")
    print(f"  Reply: {result['reply'][:150]}...")

    assert result["agent_used"] == "service_agent", f"Expected service_agent, got {result['agent_used']}"
    print("  ✓ Passed\n")
    await db.disconnect()


async def test_routing_general():
    """Greeting → should stay in general, no sub-agent."""
    print("=" * 60)
    print("  Test 4: Route to general")
    print("=" * 60)

    await db.connect()
    session = await session_repo.create_session("cust_001")

    result = await coordinator.handle_message(
        message="Hello! What can you do?",
        session_id=session["session_id"],
        user_claims={
            "sub": "cust_001",
            "name": "Alice Johnson",
            "roles": ["view_accounts", "view_transactions", "request_services"],
        },
    )

    print(f"  Agent used: {result['agent_used']}")
    print(f"  Reply: {result['reply'][:150]}...")

    assert result["agent_used"] == "general", f"Expected general, got {result['agent_used']}"
    print("  ✓ Passed\n")
    await db.disconnect()


async def test_authorization_denied():
    """Bob requests a service → should be denied (no request_services role)."""
    print("=" * 60)
    print("  Test 5: Authorization denied")
    print("=" * 60)

    await db.connect()
    session = await session_repo.create_session("cust_002")

    result = await coordinator.handle_message(
        message="I want to change my address",
        session_id=session["session_id"],
        user_claims={
            "sub": "cust_002",
            "name": "Bob Smith",
            "roles": ["view_accounts", "view_transactions"],  # no request_services
        },
    )

    print(f"  Agent used: {result['agent_used']}")
    print(f"  Reply: {result['reply'][:150]}...")

    assert result["agent_used"] == "coordinator", "Should be denied by coordinator"
    assert "permission" in result["reply"].lower(), "Should mention permission"
    print("  ✓ Passed\n")
    await db.disconnect()


async def test_trace_recorded():
    """Verify traces were written to database."""
    print("=" * 60)
    print("  Test 6: Traces in database")
    print("=" * 60)

    await db.connect()
    traces = await observability_repo.get_all_traces(limit=5)

    print(f"  Recent traces: {len(traces)}")
    for t in traces[:3]:
        print(f"    {t['agent']}: {t['action']} ({t['input_tokens']}+{t['output_tokens']} tokens)")

    assert len(traces) > 0, "Should have traces in database"
    print("  ✓ Passed\n")
    await db.disconnect()


async def main():
    await test_routing_accounts()
    await test_routing_transactions()
    await test_routing_service()
    await test_routing_general()
    await test_authorization_denied()
    await test_trace_recorded()

    print("=" * 60)
    print("  All coordinator tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())