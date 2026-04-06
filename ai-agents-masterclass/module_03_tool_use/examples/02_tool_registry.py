"""
02_tool_registry.py - Declarative Tool Registry with Auto Schema Generation
============================================================================
Module 3: Tool Use & Function Calling

Managing tool schemas manually doesn't scale. As you add more tools,
keeping the code and JSON in sync becomes error-prone.

The ToolRegistry pattern:
1. Decorate functions with @registry.tool
2. Registry auto-generates JSON schemas from signatures + docstrings
3. No manual schema maintenance
4. Single source of truth

Run with: python module_03_tool_use/examples/02_tool_registry.py
"""

from __future__ import annotations

import inspect
import json
import re
from typing import Any, Callable, Optional, get_type_hints


# ──────────────────────────────────────────────────────────────
# ToolRegistry
# ──────────────────────────────────────────────────────────────

class ToolDefinitionError(Exception):
    """Raised when a tool is defined incorrectly."""
    pass


class ToolExecutionError(Exception):
    """Raised when a tool execution fails."""
    def __init__(self, tool_name: str, message: str, original_error: Exception = None):
        super().__init__(f"Tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name
        self.original_error = original_error


class ToolRegistry:
    """
    A registry that manages agent tools declaratively.

    Features:
    - Auto-generates JSON schemas from Python function signatures
    - Parses parameter descriptions from Google-style docstrings
    - Type-safe tool execution with error handling
    - Returns errors as strings (not exceptions) so LLMs can handle them

    Usage:
        registry = ToolRegistry()

        @registry.tool
        def my_tool(query: str, limit: int = 5) -> str:
            '''
            Search for something.

            Args:
                query: What to search for
                limit: Maximum results to return

            Returns:
                Search results as a string
            '''
            return f"Results for: {query}"

        # Use with OpenAI
        response = client.chat.completions.create(
            tools=registry.get_tool_schemas(),
            ...
        )
    """

    # Maps Python types to JSON Schema types
    PYTHON_TO_JSON_TYPE = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        None: "null",
    }

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}
        self._call_counts: dict[str, int] = {}

    def tool(self, fn: Callable = None, *, description: str = None) -> Callable:
        """
        Register a function as an agent tool.

        Can be used as @registry.tool or @registry.tool(description="...").

        The function's docstring is used as the tool description.
        The function's type hints define the parameter schema.
        """
        # Handle both @registry.tool and @registry.tool(description="...")
        if fn is None:
            # Called with arguments: @registry.tool(description="...")
            def decorator(f: Callable) -> Callable:
                self._register(f, override_description=description)
                return f
            return decorator
        else:
            # Called without arguments: @registry.tool
            self._register(fn, override_description=description)
            return fn

    def _register(self, fn: Callable, override_description: str = None):
        """Register a tool function and generate its schema."""
        name = fn.__name__
        if name in self._tools:
            raise ToolDefinitionError(f"Tool '{name}' is already registered")

        schema = self._build_schema(fn, override_description)
        self._tools[name] = fn
        self._schemas[name] = schema
        self._call_counts[name] = 0

    def _build_schema(self, fn: Callable, override_description: str = None) -> dict:
        """
        Build a JSON Schema for a Python function.

        Parses:
        - Function name → tool name
        - Function docstring → tool description
        - Type hints → parameter types
        - Google-style Args: section → parameter descriptions
        - Default values → required vs optional
        """
        sig = inspect.signature(fn)
        docstring = (fn.__doc__ or "").strip()

        # Get type hints (handles forward references)
        try:
            hints = get_type_hints(fn)
        except Exception:
            hints = {}

        # Parse docstring
        description, param_descriptions = self._parse_docstring(docstring)
        if override_description:
            description = override_description

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # Determine JSON type from type hint
            hint = hints.get(param_name)
            json_type = self._python_type_to_json(hint)

            # Build property definition
            prop = {"type": json_type}

            # Add description from docstring if available
            if param_name in param_descriptions:
                prop["description"] = param_descriptions[param_name]

            # Add enum values if the type hint is a Literal
            if hasattr(hint, "__args__") and hasattr(hint, "__origin__"):
                import typing
                if hint.__origin__ is typing.Literal:
                    prop["enum"] = list(hint.__args__)

            properties[param_name] = prop

            # Required if no default value
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def _parse_docstring(self, docstring: str) -> tuple[str, dict[str, str]]:
        """
        Parse a Google-style docstring into description and parameter descriptions.

        Example:
            '''
            Search the knowledge base.

            Args:
                query: The search query string
                limit: Maximum results to return
            '''
        """
        if not docstring:
            return "", {}

        # Split at "Args:" to get main description
        if "Args:" in docstring:
            main_desc = docstring.split("Args:")[0].strip()
            args_section = docstring.split("Args:")[1]
            # Stop at Returns:, Raises:, etc.
            for stop_word in ("Returns:", "Raises:", "Note:", "Example:"):
                if stop_word in args_section:
                    args_section = args_section.split(stop_word)[0]
        else:
            main_desc = docstring
            args_section = ""

        # Parse parameter descriptions
        param_descriptions = {}
        for line in args_section.split("\n"):
            line = line.strip()
            # Match "param_name: description" or "param_name (type): description"
            match = re.match(r"(\w+)(?:\s+\([^)]+\))?\s*:\s*(.+)", line)
            if match:
                param_name = match.group(1)
                description = match.group(2).strip()
                param_descriptions[param_name] = description

        # Clean up description (remove extra whitespace, limit to first paragraph)
        main_desc = re.sub(r'\s+', ' ', main_desc).strip()

        return main_desc, param_descriptions

    def _python_type_to_json(self, hint) -> str:
        """Convert a Python type hint to a JSON Schema type string."""
        if hint is None or hint == inspect.Parameter.empty:
            return "string"

        # Handle Optional[T] = Union[T, None]
        if hasattr(hint, "__origin__"):
            import typing
            if hint.__origin__ is typing.Union:
                # Get non-None types
                non_none = [t for t in hint.__args__ if t is not type(None)]
                if non_none:
                    return self._python_type_to_json(non_none[0])

        return self.PYTHON_TO_JSON_TYPE.get(hint, "string")

    # ── Execution ──────────────────────────────────────────

    def execute(self, name: str, arguments: dict) -> str:
        """
        Execute a tool by name with the given arguments.

        Always returns a string — errors are returned as strings so
        the LLM can incorporate them into its response.
        """
        if name not in self._tools:
            available = ", ".join(self._tools.keys())
            return f"Error: Unknown tool '{name}'. Available tools: {available}"

        self._call_counts[name] += 1
        fn = self._tools[name]

        try:
            result = fn(**arguments)
            # Ensure the result is serializable
            if isinstance(result, (dict, list)):
                return json.dumps(result, indent=2, default=str)
            return str(result)
        except TypeError as e:
            return f"Error: Invalid arguments for '{name}': {e}"
        except Exception as e:
            # Log the error but return a string so the agent can handle it
            return f"Error executing '{name}': {type(e).__name__}: {e}"

    # ── Introspection ───────────────────────────────────────

    def get_tool_schemas(self) -> list[dict]:
        """Return all tool schemas in OpenAI function calling format."""
        return list(self._schemas.values())

    def list_tools(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def get_stats(self) -> dict:
        """Return call count stats."""
        return dict(self._call_counts)

    def describe(self) -> None:
        """Print a human-readable description of all tools."""
        print(f"\n  Registered Tools ({len(self._tools)}):")
        for name, schema in self._schemas.items():
            fn = schema["function"]
            params = fn["parameters"]["properties"]
            required = fn["parameters"].get("required", [])
            print(f"\n  {name}:")
            print(f"    {fn['description'][:80]}...")
            print(f"    Parameters:")
            for param_name, param_schema in params.items():
                req = " (required)" if param_name in required else " (optional)"
                desc = param_schema.get("description", "")[:50]
                print(f"      - {param_name}: {param_schema['type']}{req} — {desc}")


# ──────────────────────────────────────────────────────────────
# Demo: Register tools and show auto-generated schemas
# ──────────────────────────────────────────────────────────────

def demo_auto_schema_generation():
    """Show how the registry generates schemas from Python functions."""
    print("\n" + "=" * 60)
    print("  Auto Schema Generation Demo")
    print("=" * 60)

    registry = ToolRegistry()

    @registry.tool
    def get_weather(city: str, units: str = "celsius") -> str:
        """
        Get current weather conditions for a city.

        Args:
            city: Name of the city (e.g., 'London', 'New York')
            units: Temperature units, either 'celsius' or 'fahrenheit'

        Returns:
            Weather description as a string
        """
        return f"72°F, Partly cloudy in {city}"

    @registry.tool
    def search_database(query: str, table: str, limit: int = 10) -> list:
        """
        Search a database table for records matching a query.

        Args:
            query: Search query string
            table: Name of the database table to search
            limit: Maximum number of results to return

        Returns:
            List of matching records
        """
        return [{"id": 1, "result": f"Mock result for '{query}' in {table}"}]

    @registry.tool
    def send_notification(
        recipient_email: str,
        subject: str,
        body: str,
        priority: str = "normal",
    ) -> dict:
        """
        Send an email notification to a user.

        Args:
            recipient_email: Email address of the recipient
            subject: Subject line of the notification
            body: Body content of the notification
            priority: Message priority ('low', 'normal', 'high')

        Returns:
            Dict with 'success' and 'message_id' fields
        """
        return {"success": True, "message_id": "msg_12345"}

    # Show the auto-generated schemas
    registry.describe()

    print("\n\n  Full JSON schema for get_weather:")
    print(json.dumps(registry._schemas["get_weather"], indent=2))


def demo_error_handling():
    """Show how the registry handles errors gracefully."""
    print("\n" + "=" * 60)
    print("  Error Handling Demo")
    print("=" * 60)

    registry = ToolRegistry()

    @registry.tool
    def divide(a: int, b: int) -> float:
        """Divide a by b."""
        return a / b

    # Normal execution
    result = registry.execute("divide", {"a": 10, "b": 2})
    print(f"\n  divide(10, 2) = {result}")

    # Division by zero — returned as string, not exception
    result = registry.execute("divide", {"a": 10, "b": 0})
    print(f"  divide(10, 0) = {result}")

    # Unknown tool — returned as string
    result = registry.execute("nonexistent_tool", {})
    print(f"  nonexistent_tool() = {result}")

    # Wrong argument type
    result = registry.execute("divide", {"a": "not_a_number", "b": 2})
    print(f"  divide('not_a_number', 2) = {result}")

    print("\n  All errors returned as strings — the LLM can handle them!")


def demo_stats():
    """Show tool call tracking."""
    print("\n" + "=" * 60)
    print("  Tool Call Statistics Demo")
    print("=" * 60)

    registry = ToolRegistry()

    @registry.tool
    def my_tool(x: str) -> str:
        """A demo tool."""
        return f"Result: {x}"

    # Simulate several calls
    for _ in range(5):
        registry.execute("my_tool", {"x": "test"})

    print(f"\n  Call stats: {registry.get_stats()}")


if __name__ == "__main__":
    demo_auto_schema_generation()
    demo_error_handling()
    demo_stats()
