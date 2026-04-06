"""
02_react_agent.py - The ReAct Pattern (Reasoning + Acting)
===========================================================
Module 2: Agent Architecture Patterns

ReAct is the dominant agent pattern in production systems. It forces the
model to explicitly reason before each action, creating an auditable
decision trail that dramatically reduces hallucination.

Pattern:
    Thought: [reasoning about what to do]
    Action: tool_name(arguments)
    Observation: [result of the tool]
    ... repeat until ...
    Thought: I have enough information to answer.
    Final Answer: [response to user]

Why ReAct works:
- Forces step-by-step reasoning (like Chain of Thought)
- Each action is informed by explicit reasoning
- Creates a log of decisions you can debug and audit
- Models are trained on this pattern so it's reliable

Run with: python module_02_agent_architecture/examples/02_react_agent.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import inspect
import json
import os
import re
from typing import Any, Callable, Optional

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Tool Registry
# ──────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Registry that maps tool names to functions.

    Use the @registry.tool decorator to register tools.
    The registry auto-generates JSON schemas from function signatures.

    Usage:
        registry = ToolRegistry()

        @registry.tool
        def my_tool(param: str) -> str:
            "Description of the tool"
            return f"Result: {param}"

        schemas = registry.get_tool_schemas()  # For OpenAI
    """

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}

    def tool(self, fn: Callable) -> Callable:
        """Decorator to register a function as an agent tool."""
        name = fn.__name__
        self._tools[name] = fn
        self._schemas[name] = self._build_schema(fn)
        return fn

    def _build_schema(self, fn: Callable) -> dict:
        """Build a JSON schema for a function based on its signature and docstring."""
        sig = inspect.signature(fn)
        docstring = (fn.__doc__ or "").strip()

        # Parse the docstring to extract parameter descriptions
        param_descriptions = {}
        if "Args:" in docstring:
            args_section = docstring.split("Args:")[1].split("Returns:")[0]
            for line in args_section.strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    param_name, _, desc = line.partition(":")
                    param_descriptions[param_name.strip()] = desc.strip()

        # Function description is everything before "Args:"
        description = docstring.split("Args:")[0].strip() if "Args:" in docstring else docstring

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Infer JSON type from Python annotation
            annotation = param.annotation
            if annotation in (str, inspect.Parameter.empty):
                json_type = "string"
            elif annotation == int:
                json_type = "integer"
            elif annotation == float:
                json_type = "number"
            elif annotation == bool:
                json_type = "boolean"
            elif annotation == list:
                json_type = "array"
            else:
                json_type = "string"

            properties[param_name] = {
                "type": json_type,
                "description": param_descriptions.get(param_name, f"The {param_name} parameter"),
            }

            # Mark as required if no default value
            if param.default == inspect.Parameter.empty:
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

    def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool by name with the given arguments."""
        if name not in self._tools:
            return f"Error: Tool '{name}' not found. Available: {list(self._tools.keys())}"
        try:
            result = self._tools[name](**arguments)
            # Always return a string (LLMs work with text)
            return str(result) if not isinstance(result, str) else result
        except TypeError as e:
            return f"Error: Invalid arguments for {name}: {e}"
        except Exception as e:
            # Return error as string — don't raise, so the LLM can handle it
            return f"Tool error: {str(e)}"

    def get_tool_schemas(self) -> list[dict]:
        """Return all tool schemas in OpenAI function calling format."""
        return list(self._schemas.values())

    def list_tools(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())


# ──────────────────────────────────────────────────────────────
# Example tools for the support platform
# ──────────────────────────────────────────────────────────────

registry = ToolRegistry()


@registry.tool
def search_knowledge_base(query: str) -> str:
    """
    Search the product knowledge base for articles relevant to a support query.

    Args:
        query: Natural language description of what the customer needs help with

    Returns:
        Relevant knowledge base content, or 'No results found' if nothing matches
    """
    KB = {
        "password": "Password Reset Guide: Visit /forgot-password, enter your email, check inbox for link (valid 24h). Accounts lock after 5 failed attempts and auto-unlock after 30 minutes.",
        "2fa": "2FA Troubleshooting: If you lost access to your authenticator, use backup codes saved during setup. Contact support@example.com with your ID for emergency access.",
        "billing": "Billing Questions: View invoices at Settings > Billing. Disputes handled by billing@example.com within 2 business days. Refunds processed within 5-10 days.",
        "export": "Data Export: Go to Dashboard > Settings > Export Data. Choose CSV or JSON. Large exports (>10k rows) are emailed within 1 hour. Free plan limited to 1,000 rows.",
        "api": "API Documentation: Full docs at api.example.com/docs. Rate limits: 100/min (Pro), 500/min (Enterprise). Get your API key at Settings > API Keys.",
    }
    results = [content for keyword, content in KB.items() if keyword in query.lower()]
    return "\n\n".join(results) if results else "No relevant knowledge base articles found."


@registry.tool
def get_weather_mock(city: str) -> str:
    """
    Get the current weather for a city (mock implementation for demo).

    Args:
        city: Name of the city to get weather for

    Returns:
        Current weather conditions as a string
    """
    # Mock data — in production, this would call a real weather API
    weather_data = {
        "new york": "72°F, Partly cloudy",
        "london": "61°F, Overcast",
        "san francisco": "65°F, Foggy morning",
        "tokyo": "78°F, Sunny",
    }
    city_lower = city.lower()
    for key, weather in weather_data.items():
        if key in city_lower or city_lower in key:
            return f"Weather in {city}: {weather}"
    return f"Weather data not available for {city}"


@registry.tool
def calculate(expression: str) -> str:
    """
    Evaluate a mathematical expression safely.

    Args:
        expression: A mathematical expression to evaluate (e.g., '2 + 2', '15% of 299')

    Returns:
        The calculated result as a string
    """
    # Only allow safe characters: digits, operators, spaces, decimal points, parentheses
    safe = re.match(r'^[0-9\s\+\-\*\/\.\(\)%]+$', expression)
    if not safe:
        return f"Error: Invalid expression '{expression}'. Only basic math operations allowed."

    try:
        # Handle percentage calculations
        if "% of" in expression:
            parts = expression.lower().split("% of")
            pct = float(parts[0].strip())
            value = float(parts[1].strip())
            result = (pct / 100) * value
            return f"{pct}% of {value} = {result:.2f}"

        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return f"{expression} = {result}"
    except Exception as e:
        return f"Calculation error: {e}"


# ──────────────────────────────────────────────────────────────
# ReAct Agent
# ──────────────────────────────────────────────────────────────

REACT_SYSTEM_PROMPT = """You are a helpful customer support agent. Use the ReAct pattern:

Thought: [reason about what you need to do or know]
Action: tool_name({"param": "value"})
Observation: [you will receive the tool result here]
... (repeat Thought/Action/Observation as needed)
Thought: I now have enough information to answer.
Final Answer: [your response to the customer]

Available tools: {tools}

Rules:
- Always think before acting
- Use tools to gather information before answering
- Write 'Final Answer:' when you're ready to respond
- Keep your Final Answer concise and helpful"""


class ReActAgent:
    """
    An agent that uses the ReAct (Reason + Act) pattern.

    Instead of calling the LLM with a tool schema and parsing tool_calls,
    this agent prompts the LLM to reason in a structured text format and
    then parses that text to extract and execute actions.

    This is closer to the original ReAct paper and is more transparent
    about the reasoning process.
    """

    def __init__(self, tool_registry: ToolRegistry, model: str = "gpt-4o-mini"):
        self.registry = tool_registry
        self.model = model

    def _format_system_prompt(self) -> str:
        tool_list = "\n".join(
            f"- {schema['function']['name']}: {schema['function']['description']}"
            for schema in self.registry.get_tool_schemas()
        )
        return REACT_SYSTEM_PROMPT.format(tools=tool_list)

    def _parse_action(self, text: str) -> Optional[tuple[str, dict]]:
        """
        Parse an Action line like: Action: search_knowledge_base({"query": "password"})
        Returns (tool_name, arguments) or None if no action found.
        """
        match = re.search(r"Action:\s*(\w+)\s*\(({.*?})\)", text, re.DOTALL)
        if match:
            tool_name = match.group(1)
            try:
                args = json.loads(match.group(2))
                return tool_name, args
            except json.JSONDecodeError:
                return None
        return None

    def _parse_final_answer(self, text: str) -> Optional[str]:
        """Parse the Final Answer from the response."""
        match = re.search(r"Final Answer:\s*(.+)", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def run(self, user_message: str, max_steps: int = 8) -> str:
        """
        Run the ReAct loop until a Final Answer is produced.

        Args:
            user_message: The user's question or request
            max_steps: Maximum number of Thought/Action/Observation cycles

        Returns:
            The agent's final answer
        """
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        except ImportError:
            return "Error: openai package not installed"

        messages = [
            {"role": "system", "content": self._format_system_prompt()},
            {"role": "user", "content": user_message},
        ]

        print(f"\n{'═' * 55}")
        print(f"Question: {user_message}")
        print(f"{'═' * 55}")

        for step in range(max_steps):
            # Call LLM (no tools — it reasons in text format)
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                max_tokens=500,
                stop=["Observation:"],  # Stop when it's waiting for tool result
            )

            assistant_text = response.choices[0].message.content.strip()
            print(f"\nStep {step + 1}:")
            print(assistant_text)

            # Check if we have a final answer
            final_answer = self._parse_final_answer(assistant_text)
            if final_answer:
                print(f"\n{'═' * 55}")
                print(f"Final Answer: {final_answer}")
                return final_answer

            # Parse and execute an action
            action = self._parse_action(assistant_text)
            if action:
                tool_name, tool_args = action
                tool_result = self.registry.execute(tool_name, tool_args)
                observation = f"Observation: {tool_result}"
                print(f"\n{observation}")

                # Add this exchange to conversation history
                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({"role": "user", "content": observation})
            else:
                # LLM didn't produce an action or final answer — might be reasoning only
                messages.append({"role": "assistant", "content": assistant_text})

        return "Reached maximum steps without a final answer."


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print("  ReAct Agent Demo")
    print("=" * 55)
    print(f"\n  Tools registered: {registry.list_tools()}")
    print(f"\n  Auto-generated JSON schemas:")
    for schema in registry.get_tool_schemas():
        fn = schema["function"]
        print(f"    - {fn['name']}: {fn['description'][:50]}...")

    agent = ReActAgent(registry, model="gpt-4o-mini")

    questions = [
        "I forgot my password and can't get into my account. How do I reset it?",
        "What is 15% of $299 and what is the billing email?",
    ]

    for question in questions:
        try:
            agent.run(question)
            print()
        except Exception as e:
            if "api" in str(e).lower() or "key" in str(e).lower():
                print(f"\n  Skipped: Add OPENAI_API_KEY to .env  ({e})")
                break
            raise


if __name__ == "__main__":
    main()
