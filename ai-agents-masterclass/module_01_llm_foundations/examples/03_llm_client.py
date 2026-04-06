"""
03_llm_client.py - Production LLM Client
=========================================
Module 1: LLM Foundations

This is the LLMClient class used throughout the course. It wraps
both OpenAI and Anthropic APIs with:
- Unified interface (same code works for both providers)
- Retry logic with exponential backoff
- Token usage and cost tracking on every call
- Streaming support
- Structured error handling

Run with: python module_01_llm_foundations/examples/03_llm_client.py
Requires: OPENAI_API_KEY and/or ANTHROPIC_API_KEY in .env
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Generator, Iterator, Optional
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Pricing (must stay in sync with 02_cost_estimator.py)
# ──────────────────────────────────────────────────────────────

MODEL_PRICING = {
    # OpenAI (input/output per million tokens)
    "gpt-4o":             (2.50,  10.00),
    "gpt-4o-mini":        (0.15,   0.60),
    "o3-mini":            (1.10,   4.40),
    # Anthropic
    "claude-opus-4-20250514":    (15.00,  75.00),
    "claude-sonnet-4-20250514":   (3.00,  15.00),
    "claude-3-5-sonnet-20241022": (3.00,  15.00),
    "claude-3-5-haiku-20241022":  (0.80,   4.00),
}

def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate USD cost for a given model and token counts."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * pricing[0]
    output_cost = (output_tokens / 1_000_000) * pricing[1]
    return input_cost + output_cost


# ──────────────────────────────────────────────────────────────
# Response dataclass — unified across providers
# ──────────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """
    Normalized response from any LLM provider.

    The goal is that code using LLMClient doesn't need to know
    whether it's talking to OpenAI or Anthropic.
    """
    content: str                           # The text content of the response
    model: str                             # Model that was used
    input_tokens: int = 0                  # Tokens in the input/prompt
    output_tokens: int = 0                 # Tokens in the response
    cost_usd: float = 0.0                  # Estimated USD cost
    latency_ms: int = 0                    # Wall-clock time for the API call
    finish_reason: str = "stop"            # Why the model stopped
    tool_calls: list[dict] = field(default_factory=list)  # Tool calls if any

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __str__(self) -> str:
        return (
            f"LLMResponse(model={self.model}, tokens={self.total_tokens}, "
            f"cost=${self.cost_usd:.6f}, latency={self.latency_ms}ms)"
        )


# ──────────────────────────────────────────────────────────────
# Custom exceptions
# ──────────────────────────────────────────────────────────────

class LLMError(Exception):
    """Base class for LLM client errors."""
    pass

class LLMRateLimitError(LLMError):
    """API rate limit exceeded."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after

class LLMContextLengthError(LLMError):
    """Input exceeds the model's context window."""
    pass

class LLMAuthError(LLMError):
    """Invalid or missing API key."""
    pass


# ──────────────────────────────────────────────────────────────
# LLMClient
# ──────────────────────────────────────────────────────────────

class LLMClient:
    """
    Production LLM client that works with OpenAI and Anthropic.

    Features:
    - Unified interface: same method signatures for both providers
    - Automatic retries with exponential backoff
    - Token usage and cost tracking
    - Streaming support
    - Detailed logging

    Usage:
        client = LLMClient()

        # Chat completion
        response = client.chat(
            messages=[{"role": "user", "content": "Hello!"}],
            model="gpt-4o",
        )
        print(response.content)
        print(f"Cost: ${response.cost_usd:.6f}")

        # With system prompt
        response = client.chat(
            messages=[{"role": "user", "content": "Classify this ticket..."}],
            model="gpt-4o",
            system="You are a support triage agent...",
        )
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        max_retries: int = 3,
        initial_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
    ):
        """
        Initialize the client.

        Args:
            openai_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            anthropic_api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            max_retries: Number of retry attempts for transient errors
            initial_retry_delay: Starting delay for exponential backoff (seconds)
            max_retry_delay: Maximum delay between retries (seconds)
        """
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.max_retry_delay = max_retry_delay

        # Lazy-initialize clients
        self._openai_client = None
        self._anthropic_client = None

        # Usage tracking across all calls in this session
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_cost_usd = 0.0
        self.session_calls = 0

    # ── Client initialization ───────────────────────────────

    def _get_openai_client(self):
        """Lazy-initialize the OpenAI client."""
        if self._openai_client is None:
            try:
                from openai import OpenAI
                if not self.openai_api_key:
                    raise LLMAuthError(
                        "OPENAI_API_KEY not set. Add it to your .env file."
                    )
                self._openai_client = OpenAI(api_key=self.openai_api_key)
            except ImportError:
                raise ImportError("openai not installed. Run: pip install openai")
        return self._openai_client

    def _get_anthropic_client(self):
        """Lazy-initialize the Anthropic client."""
        if self._anthropic_client is None:
            try:
                import anthropic
                if not self.anthropic_api_key:
                    raise LLMAuthError(
                        "ANTHROPIC_API_KEY not set. Add it to your .env file."
                    )
                self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            except ImportError:
                raise ImportError("anthropic not installed. Run: pip install anthropic")
        return self._anthropic_client

    # ── Provider detection ──────────────────────────────────

    def _is_anthropic_model(self, model: str) -> bool:
        """Determine if a model ID belongs to Anthropic."""
        return model.startswith("claude")

    # ── Main interface ──────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        model: str = "gpt-4o",
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of {"role": "user"/"assistant"/"tool", "content": "..."}
            model: Model ID (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            system: Optional system prompt (prepended to messages)
            temperature: Sampling temperature 0.0-2.0 (lower = more deterministic)
            max_tokens: Maximum tokens in the response
            tools: Optional list of tool definitions in OpenAI format
            tool_choice: How to handle tools ("auto", "required", "none")

        Returns:
            LLMResponse with content, token counts, cost, and latency
        """
        if self._is_anthropic_model(model):
            return self._chat_anthropic(
                messages, model, system, temperature, max_tokens, tools, tool_choice
            )
        else:
            return self._chat_openai(
                messages, model, system, temperature, max_tokens, tools, tool_choice
            )

    def stream(
        self,
        messages: list[dict],
        model: str = "gpt-4o",
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """
        Stream a chat completion.

        Yields string chunks as they arrive from the API.

        Usage:
            for chunk in client.stream(messages):
                print(chunk, end="", flush=True)
        """
        if self._is_anthropic_model(model):
            yield from self._stream_anthropic(messages, model, system, temperature, max_tokens)
        else:
            yield from self._stream_openai(messages, model, system, temperature, max_tokens)

    # ── OpenAI implementation ───────────────────────────────

    def _chat_openai(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]],
        tool_choice: str,
    ) -> LLMResponse:
        """Execute a chat completion using the OpenAI API."""
        from openai import RateLimitError, APIStatusError

        client = self._get_openai_client()

        # Prepend system message if provided
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs = {
            "model": model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        return self._retry_call(
            lambda: self._execute_openai_call(client, kwargs, model),
            model=model,
        )

    def _execute_openai_call(self, client, kwargs: dict, model: str) -> LLMResponse:
        """Make the actual OpenAI API call and normalize the response."""
        start_ms = time.time() * 1000
        response = client.chat.completions.create(**kwargs)
        latency_ms = int(time.time() * 1000 - start_ms)

        message = response.choices[0].message
        content = message.content or ""
        finish_reason = response.choices[0].finish_reason

        # Extract tool calls if present
        tool_calls = []
        if message.tool_calls:
            import json
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = _calculate_cost(model, input_tokens, output_tokens)

        self._update_session_stats(input_tokens, output_tokens, cost)

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    def _stream_openai(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Generator[str, None, None]:
        """Stream response from OpenAI."""
        client = self._get_openai_client()

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        stream = client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    # ── Anthropic implementation ────────────────────────────

    def _chat_anthropic(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]],
        tool_choice: str,
    ) -> LLMResponse:
        """Execute a chat completion using the Anthropic API."""
        client = self._get_anthropic_client()

        # Anthropic uses a separate 'system' parameter, not a message
        # Filter out any system messages from the messages list
        anthropic_messages = [m for m in messages if m.get("role") != "system"]

        # Convert OpenAI-format tool results to Anthropic format if needed
        anthropic_messages = self._convert_tool_messages_for_anthropic(anthropic_messages)

        # Convert OpenAI-format tools to Anthropic format
        anthropic_tools = None
        if tools:
            anthropic_tools = self._convert_tools_for_anthropic(tools)

        kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        return self._retry_call(
            lambda: self._execute_anthropic_call(client, kwargs, model),
            model=model,
        )

    def _execute_anthropic_call(self, client, kwargs: dict, model: str) -> LLMResponse:
        """Make the actual Anthropic API call and normalize the response."""
        start_ms = time.time() * 1000
        response = client.messages.create(**kwargs)
        latency_ms = int(time.time() * 1000 - start_ms)

        # Extract text content (Anthropic returns a list of content blocks)
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = _calculate_cost(model, input_tokens, output_tokens)

        self._update_session_stats(input_tokens, output_tokens, cost)

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason or "stop",
            tool_calls=tool_calls,
        )

    def _stream_anthropic(
        self,
        messages: list[dict],
        model: str,
        system: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Generator[str, None, None]:
        """Stream response from Anthropic."""
        client = self._get_anthropic_client()

        anthropic_messages = [m for m in messages if m.get("role") != "system"]
        kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system

        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    # ── Format conversion helpers ───────────────────────────

    def _convert_tools_for_anthropic(self, openai_tools: list[dict]) -> list[dict]:
        """Convert OpenAI tool format to Anthropic format."""
        anthropic_tools = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                anthropic_tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                })
        return anthropic_tools

    def _convert_tool_messages_for_anthropic(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI tool result messages to Anthropic format."""
        converted = []
        for msg in messages:
            if msg.get("role") == "tool":
                # OpenAI: {"role": "tool", "tool_call_id": "...", "content": "..."}
                # Anthropic: {"role": "user", "content": [{"type": "tool_result", ...}]}
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }]
                })
            else:
                converted.append(msg)
        return converted

    # ── Retry logic ─────────────────────────────────────────

    def _retry_call(self, fn: callable, model: str) -> LLMResponse:
        """
        Execute an API call with exponential backoff retry.

        Retries on:
        - Rate limit errors (429)
        - Transient server errors (500, 503)

        Does NOT retry on:
        - Authentication errors (401)
        - Invalid request errors (400)
        - Context length errors
        """
        delay = self.initial_retry_delay

        for attempt in range(self.max_retries + 1):
            try:
                return fn()

            except Exception as e:
                error_str = str(e).lower()
                is_retryable = (
                    "rate limit" in error_str
                    or "429" in error_str
                    or "503" in error_str
                    or "500" in error_str
                    or "overloaded" in error_str
                )

                if not is_retryable or attempt == self.max_retries:
                    # Translate to our exception types
                    if "401" in error_str or "invalid api key" in error_str:
                        raise LLMAuthError(f"Authentication failed: {e}")
                    elif "context_length" in error_str or "too long" in error_str:
                        raise LLMContextLengthError(f"Context too long: {e}")
                    elif "rate limit" in error_str or "429" in error_str:
                        raise LLMRateLimitError(f"Rate limit: {e}")
                    else:
                        raise LLMError(f"LLM API error: {e}")

                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{self.max_retries}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)
                delay = min(delay * 2, self.max_retry_delay)

    # ── Session stats ────────────────────────────────────────

    def _update_session_stats(self, input_tokens: int, output_tokens: int, cost: float):
        """Update running totals for this client session."""
        self.session_input_tokens += input_tokens
        self.session_output_tokens += output_tokens
        self.session_cost_usd += cost
        self.session_calls += 1

    def print_session_stats(self) -> None:
        """Print accumulated usage stats for this session."""
        print(f"\n{'─' * 45}")
        print(f"  LLM Session Stats")
        print(f"{'─' * 45}")
        print(f"  API calls:       {self.session_calls:,}")
        print(f"  Input tokens:    {self.session_input_tokens:,}")
        print(f"  Output tokens:   {self.session_output_tokens:,}")
        print(f"  Total tokens:    {self.session_input_tokens + self.session_output_tokens:,}")
        print(f"  Total cost:      ${self.session_cost_usd:.6f}")
        if self.session_calls > 0:
            avg_cost = self.session_cost_usd / self.session_calls
            print(f"  Avg cost/call:   ${avg_cost:.6f}")
        print(f"{'─' * 45}")


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def demo_basic_chat():
    """Demonstrate a basic chat completion."""
    print("\n" + "=" * 55)
    print("  Demo: Basic Chat Completion")
    print("=" * 55)

    client = LLMClient()

    messages = [
        {"role": "user", "content": "In one sentence, what is an AI agent?"}
    ]

    print("\n  Calling GPT-4o...")
    try:
        response = client.chat(messages, model="gpt-4o", max_tokens=100)
        print(f"\n  Response: {response.content}")
        print(f"\n  {response}")
    except LLMAuthError as e:
        print(f"\n  Skipped (no API key): {e}")
    except Exception as e:
        print(f"\n  Error: {e}")


def demo_streaming():
    """Demonstrate streaming responses."""
    print("\n" + "=" * 55)
    print("  Demo: Streaming Response")
    print("=" * 55)

    client = LLMClient()
    messages = [{"role": "user", "content": "List 3 benefits of AI agents in 1 sentence each."}]

    print("\n  Streaming from GPT-4o (tokens arrive in real-time):\n")
    try:
        for chunk in client.stream(messages, model="gpt-4o", max_tokens=200):
            print(chunk, end="", flush=True)
        print("\n")
    except LLMAuthError as e:
        print(f"\n  Skipped (no API key): {e}")
    except Exception as e:
        print(f"\n  Error: {e}")


def demo_provider_comparison():
    """Show the same call going to both OpenAI and Anthropic."""
    print("\n" + "=" * 55)
    print("  Demo: Cross-Provider Comparison")
    print("=" * 55)

    client = LLMClient()

    question = "Classify this support ticket in one word: 'I can't log in'"
    messages = [{"role": "user", "content": question}]

    for model in ["gpt-4o-mini", "claude-3-5-haiku-20241022"]:
        print(f"\n  Model: {model}")
        try:
            response = client.chat(messages, model=model, temperature=0, max_tokens=20)
            print(f"  Response: {response.content.strip()}")
            print(f"  Cost: ${response.cost_usd:.6f}, Latency: {response.latency_ms}ms")
        except LLMAuthError as e:
            print(f"  Skipped: {e}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    demo_basic_chat()
    demo_streaming()
    demo_provider_comparison()

    # Show how the client accumulates stats
    client = LLMClient()
    print("\n  (Making a few calls to demonstrate session stats...)")
    for _ in range(2):
        try:
            client.chat(
                [{"role": "user", "content": "Hi"}],
                model="gpt-4o-mini",
                max_tokens=10,
            )
        except Exception:
            pass
    client.print_session_stats()
