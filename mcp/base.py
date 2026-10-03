"""
Base MCP Server — async tool registry with structured error handling.

The MCP (Model Context Protocol) pattern:
  1. Tools are registered with name, description, parameters, and an async handler
  2. Agents discover available tools via list_tools()
  3. Agents invoke tools via call_tool()
  4. Results are returned in a standard format the LLM can parse

Production concerns handled here:
  - Structured error types (not just string messages)
  - Timeout protection on tool execution
  - Correlation ID logging for tracing a request across layers
  - Type-safe tool results
"""
import asyncio
import time
import logging
from typing import Callable
from dataclasses import dataclass
from enum import Enum
from llm.base_client import BaseLLMClient

logger = logging.getLogger("mcp")


class ToolErrorType(str, Enum):
    """Structured error types so agents can react differently to different failures."""
    NOT_FOUND = "not_found"           # resource doesn't exist
    PERMISSION_DENIED = "permission"  # not allowed
    VALIDATION = "validation"         # bad input
    TIMEOUT = "timeout"               # took too long
    INTERNAL = "internal"             # unexpected failure
    UNKNOWN_TOOL = "unknown_tool"     # tool doesn't exist


@dataclass
class ToolResult:
    """Standard result from every tool call."""
    tool_name: str
    success: bool
    data: dict | list | str
    error: str | None = None
    error_type: ToolErrorType | None = None
    execution_ms: float = 0


class BaseMCPServer:
    """
    Each domain (accounts, transactions, services) gets its own MCP server.
    Tools are async functions backed by PostgreSQL repositories.
    """

    TOOL_TIMEOUT_SECONDS = 10  # kill tool calls that take too long

    def __init__(self, server_name: str):
        logger.debug("Calling BaseMCPServer.__init__")
        self.server_name = server_name
        self._tools: dict[str, dict] = {}
        self._handlers: dict[str, Callable] = {}
        logger.info(f"[MCP:{self.server_name}] Server initialized")

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
    ):
        """
        Register an async tool handler.

        Parameters
        ----------
        name : str
            Tool name (must match what the LLM will call)
        description : str
            What the tool does (the LLM reads this to decide when to use it)
        parameters : dict
            JSON Schema for the tool's input:
            {"properties": {...}, "required": [...]}
        handler : Callable
            Async function that executes the tool
        """
        logger.debug("Calling BaseMCPServer.register_tool")
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
        self._handlers[name] = handler
        logger.info(f"[MCP:{self.server_name}] Registered tool: {name}")

    def list_tools(self) -> list[dict]:
        """Return raw tool definitions."""
        logger.debug("Calling BaseMCPServer.list_tools")
        return list(self._tools.values())

    def get_tool_specs(self) -> list[dict]:
        """
        Return tools in OpenAI function-calling format.
        The LLM client's Bedrock implementation converts this
        to Bedrock format internally — we don't need to care.
        """
        logger.debug("Calling BaseMCPServer.get_tool_specs")
        return [
            BaseLLMClient.build_tool_spec(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in self._tools.values()
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        """
        Execute a registered tool by name with timeout protection.

        This is the method agents call after the LLM decides to use a tool.
        """
        logger.debug("Calling BaseMCPServer.call_tool")
        handler = self._handlers.get(tool_name)
        if not handler:
            logger.warning(f"[MCP:{self.server_name}] Unknown tool: {tool_name}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data="",
                error=f"Unknown tool: {tool_name}",
                error_type=ToolErrorType.UNKNOWN_TOOL,
            )

        start = time.time()

        try:
            # Timeout protection — don't let a bad query hang forever
            result = await asyncio.wait_for(
                handler(**arguments),
                timeout=self.TOOL_TIMEOUT_SECONDS,
            )
            execution_ms = (time.time() - start) * 1000

            logger.info(
                f"[MCP:{self.server_name}] {tool_name} succeeded "
                f"({execution_ms:.0f}ms)"
            )
            return ToolResult(
                tool_name=tool_name,
                success=True,
                data=result,
                execution_ms=execution_ms,
            )

        except asyncio.TimeoutError:
            execution_ms = (time.time() - start) * 1000
            logger.error(
                f"[MCP:{self.server_name}] {tool_name} timed out "
                f"after {self.TOOL_TIMEOUT_SECONDS}s"
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data="",
                error=f"Tool timed out after {self.TOOL_TIMEOUT_SECONDS}s",
                error_type=ToolErrorType.TIMEOUT,
                execution_ms=execution_ms,
            )

        except ValueError as e:
            # Expected errors (not found, bad input) — the agent can handle these
            execution_ms = (time.time() - start) * 1000
            logger.warning(
                f"[MCP:{self.server_name}] {tool_name} validation error: {e}"
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data="",
                error=str(e),
                error_type=ToolErrorType.VALIDATION,
                execution_ms=execution_ms,
            )

        except Exception as e:
            # Unexpected errors — log full details, return generic message
            execution_ms = (time.time() - start) * 1000
            logger.exception(
                f"[MCP:{self.server_name}] {tool_name} internal error"
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data="",
                error=f"Internal error: {type(e).__name__}",
                error_type=ToolErrorType.INTERNAL,
                execution_ms=execution_ms,
            )