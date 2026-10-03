"""
Human-in-the-Loop Configuration.

Defines which tool calls require approval before execution,
and who can approve them.

Add to your config.py or keep as a separate file.
"""

# Tools that require approval before execution.
# Key = tool name (from MCP server)
# Value = who approves ("customer" or "employee")
TOOLS_REQUIRING_APPROVAL = {
    "change_address": "customer",        # customer confirms in chat
    "request_chequebook": "customer",    # customer confirms in chat
    "update_kyc": "employee",            # bank employee approves via dashboard
}


def needs_approval(tool_name: str) -> bool:
    """Check if a tool call needs human approval."""
    return tool_name in TOOLS_REQUIRING_APPROVAL


def get_approver_type(tool_name: str) -> str | None:
    """Get who can approve this tool: 'customer' or 'employee'."""
    return TOOLS_REQUIRING_APPROVAL.get(tool_name)