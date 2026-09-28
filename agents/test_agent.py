"""
Test script for the Base Agent — your first real agent run.
Run: python test_agent.py

This tests the FULL chain:
  User message → LLM → tool call → PostgreSQL → result → LLM → final reply

You'll see the agent:
  1. Receive "What are my account balances?"
  2. Ask the LLM what to do
  3. LLM decides to call list_accounts tool
  4. Tool queries PostgreSQL via account_repo
  5. Result goes back to LLM
  6. LLM might call balance_enquiry for each account
  7. LLM generates a natural language response
"""
import asyncio
import json
import sys
from pathlib import Path

# Allow running this file directly (`python agents/test_agent.py`) even though
# it lives in a subdirectory — Python only puts the script's own folder on
# sys.path, not the repo root where db/, llm/, and mcp/ live.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import db
from agents.base_agent import BaseAgent
from mcp.accounts_mcp import accounts_mcp


async def test_agent_with_tools():
    """Test: agent calls tools and gets a real answer."""
    print("Calling test_agent_with_tools")
    print("=" * 60)
    print("  Test 1: Agent with tool use")
    print("=" * 60)

    await db.connect()
    # Create session first — in production, the API route does this
    from db.repositories.session_repo import session_repo
    session = await session_repo.create_session("cust_001")
    session_id = session["session_id"]
    # Create a temporary agent (Phase 5 will create proper ones)
    agent = BaseAgent(
        name="test_accounts_agent",
        system_prompt=(
            "You are a banking assistant that helps with account queries. "
            "Use the available tools to get real data. Never make up numbers."
        ),
        mcp_server=accounts_mcp,
    )

    # Run with context (this is what the coordinator will inject later)
    result = await agent.run(
        user_message="What are my account balances?",
        session_id=session_id,
        context={
            "customer_id": "cust_001",
            "customer_name": "Alice Johnson",
            "account_ids": ["acc_1001", "acc_1002"],
        },
    )

    print(f"\n  Reply:\n  {result['reply'][:200]}...")
    print(f"\n  Tool calls made: {len(result['tool_calls'])}")
    for tc in result["tool_calls"]:
        print(f"    Round {tc['round']}: {tc['tool']}({tc['input']}) → success={tc['success']}")
    print(f"\n  Tokens: {result['total_input_tokens']} in, {result['total_output_tokens']} out")
    print(f"  Cost: ${result['total_cost']:.6f}")
    print(f"  Latency: {result['total_latency_ms']:.0f}ms")

    assert result["reply"] is not None, "Should have a reply"
    assert len(result["tool_calls"]) > 0, "Should have called at least one tool"
    print("\n  ✓ Passed\n")

    await db.disconnect()


async def test_agent_error_handling():
    """Test: agent handles tool errors gracefully."""
    print("Calling test_agent_error_handling")
    print("=" * 60)
    print("  Test 2: Agent error handling")
    print("=" * 60)

    await db.connect()
    from db.repositories.session_repo import session_repo
    session = await session_repo.get_session("sess_78b252dc5eb7")
    print(f"  Using session: {session}")
    session_id = session["session_id"]
    agent = BaseAgent(
        name="test_accounts_agent",
        system_prompt=(
            "You are a banking assistant. Use tools to get data. "
            "If a tool returns an error, tell the user what went wrong."
        ),
        mcp_server=accounts_mcp,
    )

    # Ask about a non-existent customer
    result = await agent.run(
        user_message="Show me the accounts for customer cust_999",
        session_id=session_id ,
        context={"customer_id": "cust_999"},
    )

    print(f"\n  Reply:\n  {result['reply'][:200]}...")
    print(f"\n  Tool calls: {len(result['tool_calls'])}")
    for tc in result["tool_calls"]:
        print(f"    {tc['tool']}: success={tc['success']} error_type={tc.get('error_type')}")

    assert result["reply"] is not None, "Should still have a reply even on error"
    print("\n  ✓ Passed\n")

    await db.disconnect()


async def test_cost_tracking():
    """Test: verify costs were recorded in database."""
    print("Calling test_cost_tracking")
    print("=" * 60)
    print("  Test 3: Cost tracking in database")
    print("=" * 60)

    await db.connect()

    from db.repositories.observability_repo import observability_repo

    cost = await observability_repo.get_session_cost("test_agent_001")
    print(f"  Session test_agent_001:")
    print(f"    Total calls: {cost['total_calls']}")
    print(f"    Total tokens: {cost['total_input_tokens']} in, {cost['total_output_tokens']} out")
    print(f"    Total cost: ${cost['total_cost_usd']:.6f}")

    assert cost["total_calls"] > 0, "Should have recorded cost entries"
    print("\n  ✓ Passed\n")

    await db.disconnect()


async def main():
    print("Calling main")
    await test_agent_with_tools()
    await test_agent_error_handling()
    await test_cost_tracking()

    print("=" * 60)
    print("  All agent tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())