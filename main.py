import asyncio
from db.connection import db
from db.repositories.account_repo import account_repo
from db.repositories.customer_repo import customer_repo
from db.repositories.observability_repo import observability_repo
from db.repositories.service_repo import service_repo
from db.repositories.session_repo import session_repo
from db.repositories.transaction_repo import transaction_repo
from llm import llm_client
from llm.base_client import BaseLLMClient
from mcp.accounts_mcp import accounts_mcp
import json

async def test_connection():
    """Phase 0: can we talk to the database?"""
    print("Calling test_connection")
    print("=" * 50)
    print("  Testing database connection")
    print("=" * 50)
 
    await db.connect()
 
    row = await db.fetchrow(
        "SELECT customer_id, name FROM banking.customers WHERE customer_id = $1",
        "cust_001",
    )
    print(f"  ✓ Connected! Found: {row['name']}")
 
    await db.disconnect()
    print()

async def test_account_repo():
    """Phase 1: does account_repo work?"""
    print("Calling test_account_repo")
    print("=" * 50)
    print("  Testing account_repo")
    print("=" * 50)
 
    await db.connect()
 
    # Test get_balance
    balance = await account_repo.get_balance("acc_1001")
    assert balance is not None, "acc_1001 should exist"
    assert isinstance(balance["balance"], float), "balance should be float, not Decimal"
    print(f"  ✓ get_balance: acc_1001 = ${balance['balance']} ({balance['type']}, {balance['status']})")
 
    # Test get_balance with non-existent account
    missing = await account_repo.get_balance("acc_9999")
    assert missing is None, "non-existent account should return None"
    print(f"  ✓ get_balance: acc_9999 = None (correctly handled)")
 
    # Test list_by_customer
    accounts = await account_repo.list_by_customer("cust_001")
    assert len(accounts) == 2, f"Alice should have 2 accounts, got {len(accounts)}"
    assert isinstance(accounts[0]["balance"], float), "balance should be float"
    assert isinstance(accounts[0]["opened_date"], str), "opened_date should be string"
    print(f"  ✓ list_by_customer: Alice has {len(accounts)} accounts")
    for acc in accounts:
        print(f"      {acc['account_id']}: {acc['type']} ${acc['balance']}")
 
    # Test list_by_customer with no accounts
    empty = await account_repo.list_by_customer("cust_999")
    assert empty == [], "non-existent customer should return empty list"
    print(f"  ✓ list_by_customer: cust_999 = [] (correctly handled)")
 
    # Test verify_ownership
    owns = await account_repo.verify_ownership("acc_1001", "cust_001")
    assert owns is True, "Alice should own acc_1001"
    print(f"  ✓ verify_ownership: Alice owns acc_1001 = {owns}")
 
    not_owns = await account_repo.verify_ownership("acc_1001", "cust_002")
    assert not_owns is False, "Bob should NOT own acc_1001"
    print(f"  ✓ verify_ownership: Bob owns acc_1001 = {not_owns}")
 
    await db.disconnect()
    print()


async def test_customer_repo():
    """Phase 2: does customer_repo work?"""
    print("Calling test_customer_repo")
    print("=" * 50)
    print("  Testing customer_repo")
    print("=" * 50)

    await db.connect()

    customer = await customer_repo.get_by_id("cust_001")
    assert customer is not None, "cust_001 should exist"
    print(f"  [OK] get_by_id: {customer['name']}")

    by_email = await customer_repo.get_by_email(customer["email"])
    assert by_email is not None and by_email["customer_id"] == "cust_001"
    print(f"  [OK] get_by_email: {customer['email']}")

    roles = await customer_repo.get_roles("cust_001")
    profile = await customer_repo.get_profile_with_roles("cust_001")
    assert profile is not None and profile["roles"] == roles
    print(f"  [OK] get_roles/get_profile_with_roles: {roles}")

    assert await customer_repo.update_address("cust_001", customer["address"])
    assert await customer_repo.update_kyc_status("cust_001", customer["kyc_status"])
    print("  [OK] update_address/update_kyc_status")

    assert await customer_repo.verify_password("cust_001", "demo123")
    assert not await customer_repo.verify_password("cust_001", "wrong-password")
    print("  [OK] verify_password")

    await db.disconnect()
    print()


async def test_session_repo():
    """Phase 3: does session_repo work?"""
    print("Calling test_session_repo")
    print("=" * 50)
    print("  Testing session_repo")
    print("=" * 50)

    await db.connect()

    session = await session_repo.create_session("cust_001")
    session_id = session["session_id"]
    loaded = await session_repo.get_session(session_id)
    assert loaded is not None and loaded["session_id"] == session_id
    await session_repo.touch_session(session_id)
    await session_repo.add_message(session_id, "user", "repository test", "test")
    history = await session_repo.get_history(session_id)
    assert any(message["content"] == "repository test" for message in history)
    await session_repo.set_shared_state(session_id, "test", {"ok": True})
    await session_repo.set_agent_context(session_id, "test_agent", {"ok": True})
    loaded = await session_repo.get_session(session_id)
    assert loaded["shared_state"]["test"] == {"ok": True}
    assert loaded["agent_context"]["test_agent"] == {"ok": True}
    await session_repo.store_pii_mapping(session_id, "[TEST_EMAIL]", "test@example.com", "EMAIL")
    mappings = await session_repo.get_pii_mappings(session_id)
    assert mappings["[TEST_EMAIL]"] == "test@example.com"
    print(f"  [OK] all session methods for {session_id}")

    await db.execute("DELETE FROM banking.sessions WHERE session_id = $1", session_id)
    await db.disconnect()
    print()


async def test_observability_repo():
    """Phase 4: does observability_repo work?"""
    print("Calling test_observability_repo")
    print("=" * 50)
    print("  Testing observability_repo")
    print("=" * 50)

    await db.connect()

    session = await session_repo.create_session("cust_001")
    session_id = session["session_id"]
    trace_id = await observability_repo.record_trace(
        session_id, "test_agent", "repository_test", [{"tool": "test"}], 10, 20, 1.5
    )
    traces = await observability_repo.get_session_traces(session_id)
    all_traces = await observability_repo.get_all_traces()
    assert any(trace["trace_id"] == trace_id for trace in traces)
    assert any(trace["trace_id"] == trace_id for trace in all_traces)
    cost_id = await observability_repo.record_cost(session_id, "test-model", 10, 20, 0.01)
    session_cost = await observability_repo.get_session_cost(session_id)
    total_cost = await observability_repo.get_total_cost()
    assert session_cost["total_calls"] == 1
    assert session_cost["total_input_tokens"] == 10
    assert total_cost["total_calls"] >= 1
    await observability_repo.audit("repository_test", "cust_001", "main_test", {"ok": True})
    print(f"  [OK] traces, costs, and audit (trace_id={trace_id}, cost_id={cost_id})")

    await db.execute("DELETE FROM banking.audit_log WHERE action = $1 AND resource = $2", "repository_test", "main_test")
    await db.execute("DELETE FROM banking.agent_traces WHERE trace_id = $1", trace_id)
    await db.execute("DELETE FROM banking.cost_records WHERE cost_id = $1", cost_id)
    await db.execute("DELETE FROM banking.sessions WHERE session_id = $1", session_id)
    await db.disconnect()
    print()


async def test_service_repo():
    """Phase 5: does service_repo work?"""
    print("Calling test_service_repo")
    print("=" * 50)
    print("  Testing service_repo")
    print("=" * 50)

    await db.connect()

    customer = await customer_repo.get_by_id("cust_001")
    assert customer is not None
    address_request = await service_repo.change_address("cust_001", customer["address"])
    cheque_request = await service_repo.request_chequebook("cust_001", "acc_1001", 25)
    kyc_request = await service_repo.update_kyc("cust_001", "passport", "TEST-DOCUMENT")
    direct_request = await service_repo.create_request(
        "cust_001", "dispute", {"reason": "repository test"}
    )
    request_ids = [
        address_request["request_id"],
        cheque_request["request_id"],
        kyc_request["request_id"],
        direct_request["request_id"],
    ]
    requests = await service_repo.get_requests("cust_001")
    assert set(request_ids).issubset({request["request_id"] for request in requests})
    print(f"  [OK] all service methods ({len(request_ids)} requests)")

    await db.execute(
        """
        UPDATE banking.customers
        SET address = $2, kyc_status = $3, kyc_last_updated = $4
        WHERE customer_id = $1
        """,
        "cust_001",
        customer["address"],
        customer["kyc_status"],
        customer["kyc_last_updated"],
    )
    for request_id in request_ids:
        await db.execute("DELETE FROM banking.service_requests WHERE request_id = $1", request_id)
    await db.disconnect()
    print()


async def test_transaction_repo():
    """Phase 6: does transaction_repo work?"""
    print("Calling test_transaction_repo")
    print("=" * 50)
    print("  Testing transaction_repo")
    print("=" * 50)

    await db.connect()

    transactions = await transaction_repo.get_transactions("acc_1001")
    assert transactions, "acc_1001 should have transactions"
    assert isinstance(transactions[0]["amount"], float)
    filtered = await transaction_repo.get_transactions("acc_1001", category="utilities")
    assert all(transaction["category"] == "utilities" for transaction in filtered)
    statement = await transaction_repo.get_statement("acc_1001", 8, 2024)
    assert statement["account_id"] == "acc_1001"
    assert statement["transaction_count"] == len(statement["transactions"])
    print(f"  [OK] get_transactions: {len(transactions)} rows")
    print(f"  [OK] get_statement: {statement['transaction_count']} rows")

    await db.disconnect()
    print()
 



def test_basic_chat():
    """Test 1: simple text response."""
    print("Calling test_basic_chat")
    print("=" * 50)
    print(f"  Test 1: Basic chat ({llm_client.model_id})")
    print("=" * 50)
 
    response = llm_client.invoke(
        messages=[{"role": "user", "content": "What is AI"}],
        system_prompt="You are a helpful assistant. Be extremely brief.",
        session_id="test_basic",
    )
 
    print(f"  Reply: {response['reply']}")
    print(f"  Model: {response['model']}")
    print(f"  Tokens: {response['input_tokens']} in, {response['output_tokens']} out")
    print(f"  Cost: ${response['estimated_cost']}")
    print(f"  Latency: {response['latency_ms']:.0f}ms")
 
    assert response["reply"] is not None, "Should have a text reply"
    assert response["tool_uses"] is None, "Should have no tool calls"
    print("  ✓ Passed\n")
 
 
def test_tool_calling():
    """Test 2: LLM wants to call a tool."""
    print("Calling test_tool_calling")
    print("=" * 50)
    print(f"  Test 2: Tool calling ({llm_client.model_id})")
    print("=" * 50)
 
    # Define a tool using the universal format
    tools = [
        BaseLLMClient.build_tool_spec(
            name="get_weather",
            description="Get current weather for a city",
            parameters={
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"],
            },
        )
    ]
 
    response = llm_client.invoke(
        messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
        system_prompt="You have a weather tool. Always use it for weather questions.",
        tools=tools,
        session_id="test_tools",
    )
 
    print(f"  Reply: {response['reply']}")
    print(f"  Tool uses: {response['tool_uses']}")
    print(f"  Stop reason: {response['stop_reason']}")
 
    assert response["stop_reason"] == "tool_calls", "Should want to use a tool"
    assert response["tool_uses"] is not None, "Should have tool calls"
    assert response["tool_uses"][0]["name"] == "get_weather", "Should call get_weather"
 
    tool_call = response["tool_uses"][0]
    print(f"  Tool: {tool_call['name']}")
    print(f"  Args: {tool_call['arguments']}")
    print(f"  ID: {tool_call['id']}")
    print("  ✓ Passed\n")
 
 
def test_tool_spec_format():
    """Test 3: build_tool_spec produces correct format."""
    print("Calling test_tool_spec_format")
    print("=" * 50)
    print("  Test 3: Tool spec format")
    print("=" * 50)
 
    spec = BaseLLMClient.build_tool_spec(
        name="balance_enquiry",
        description="Get account balance",
        parameters={
            "properties": {
                "account_id": {"type": "string", "description": "The account ID"}
            },
            "required": ["account_id"],
        },
    )
 
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "balance_enquiry"
    assert "account_id" in spec["function"]["parameters"]["properties"]
 
    print(f"  Spec: {json.dumps(spec, indent=2)}")
    print("  ✓ Passed\n")


async def test_tool_discovery():
    """Test 1: can agents discover what tools are available?"""
    print("Calling test_tool_discovery")
    print("=" * 50)
    print("  Test 1: Tool discovery")
    print("=" * 50)
 
    # Raw tool list
    tools = accounts_mcp.list_tools()
    print(f"  Tools registered: {[t['name'] for t in tools]}")
    assert len(tools) == 2, f"Expected 2 tools, got {len(tools)}"
 
    # LLM-ready format (OpenAI function-calling)
    specs = accounts_mcp.get_tool_specs()
    for spec in specs:
        func = spec["function"]
        print(f"  Tool: {func['name']}")
        print(f"    Description: {func['description']}")
        print(f"    Parameters: {list(func['parameters']['properties'].keys())}")
    assert specs[0]["type"] == "function"
 
    print("  ✓ Passed\n")
 
async def test_tool_invocation():
    """Test 2: call tools successfully."""
    print("Calling test_tool_invocation")
    print("=" * 50)
    print("  Test 2: Tool invocation")
    print("=" * 50)
 
    await db.connect()
 
    # Balance enquiry
    result = await accounts_mcp.call_tool("balance_enquiry", {"account_id": "acc_1001"})
    print(f"  balance_enquiry:")
    print(f"    Success: {result.success}")
    print(f"    Data: {result.data}")
    print(f"    Time: {result.execution_ms:.0f}ms")
    assert result.success is True
    assert result.data["account_id"] == "acc_1001"
    assert isinstance(result.data["balance"], float)
 
    # List accounts
    result = await accounts_mcp.call_tool("list_accounts", {"customer_id": "cust_001"})
    print(f"  list_accounts:")
    print(f"    Success: {result.success}")
    print(f"    Accounts: {len(result.data['accounts'])}")
    assert result.success is True
    assert len(result.data["accounts"]) == 2
 
    await db.disconnect()
    print("  ✓ Passed\n")
 
 
async def test_error_handling():
    """Test 3: tools handle errors gracefully."""
    print("Calling test_error_handling")
    print("=" * 50)
    print("  Test 3: Error handling")
    print("=" * 50)
 
    await db.connect()
 
    # Non-existent account → ValueError → VALIDATION error
    result = await accounts_mcp.call_tool("balance_enquiry", {"account_id": "acc_9999"})
    print(f"  Non-existent account:")
    print(f"    Success: {result.success}")
    print(f"    Error: {result.error}")
    print(f"    Error type: {result.error_type}")
    assert result.success is False
    assert result.error_type.value == "validation"
 
    # Unknown tool → UNKNOWN_TOOL error
    result = await accounts_mcp.call_tool("nonexistent_tool", {})
    print(f"  Unknown tool:")
    print(f"    Success: {result.success}")
    print(f"    Error type: {result.error_type}")
    assert result.success is False
    assert result.error_type.value == "unknown_tool"
 
    await db.disconnect()
    print("  ✓ Passed\n")
 
 
async def test_full_flow():
    """Test 4: simulate what the agent does — discover tools, pick one, call it."""
    print("Calling test_full_flow")
    print("=" * 50)
    print("  Test 4: Full agent flow simulation")
    print("=" * 50)
 
    await db.connect()
 
    # Step 1: Agent gets tool specs to send to LLM
    specs = accounts_mcp.get_tool_specs()
    print(f"  Step 1 — Discovered {len(specs)} tools")
 
    # Step 2: LLM would return something like this (simulated)
    llm_tool_call = {
        "name": "balance_enquiry",
        "arguments": {"account_id": "acc_1001"},
        "id": "call_abc123",
    }
    print(f"  Step 2 — LLM chose: {llm_tool_call['name']}({llm_tool_call['arguments']})")
 
    # Step 3: Agent executes the tool
    result = await accounts_mcp.call_tool(
        llm_tool_call["name"],
        llm_tool_call["arguments"],
    )
    print(f"  Step 3 — Tool result: success={result.success}")
 
    # Step 4: Agent would feed this back to LLM as tool result
    tool_response = json.dumps(result.data if result.success else {"error": result.error})
    print(f"  Step 4 — Feed back to LLM: {tool_response[:80]}...")
 
    assert result.success is True
 
    await db.disconnect()
    print("  ✓ Passed\n")
 
 
async def main():
    # await test_connection()
    # await test_account_repo()
    #await test_customer_repo()
    # await test_session_repo()
    # await test_observability_repo()
    #await test_service_repo()
    #await test_transaction_repo()
    print("Calling main")
    test_basic_chat()          # first real LLM call
    test_tool_spec_format()     # no API call, test format first
    test_tool_calling() 
    print("=" * 50)
    print("  All tests passed!")
    print("=" * 50)

    await test_tool_discovery()
    await test_tool_invocation()
    await test_error_handling()
    await test_full_flow()
 
    print("=" * 50)
    print("  All MCP tests passed!")
    print("=" * 50)
 

 
 
if __name__ == "__main__":
    asyncio.run(main())