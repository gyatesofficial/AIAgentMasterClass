"""
02_redis_memory.py - Persistent Conversation Memory with Redis
=============================================================
Module 4: Memory Systems

In-memory conversation history disappears when the process restarts.
Redis provides persistence across restarts, horizontal scaling, and
automatic TTL-based expiration.

This module shows:
1. Storing conversation history in Redis
2. Session management with TTL
3. Cross-process conversation continuity
4. Graceful fallback when Redis is unavailable

Run with: python module_04_memory_systems/examples/02_redis_memory.py
Requires: Redis running (docker compose up -d redis)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


# ──────────────────────────────────────────────────────────────
# RedisConversationMemory
# ──────────────────────────────────────────────────────────────

class RedisConversationMemory:
    """
    Persistent conversation memory backed by Redis.

    Each conversation session is stored under a key:
        session:{session_id}

    The value is a JSON-encoded list of messages.
    TTL ensures old sessions are automatically cleaned up.

    Usage:
        memory = RedisConversationMemory()

        # Store messages
        memory.add_message("session-001", "user", "I need help")
        memory.add_message("session-001", "assistant", "How can I help?")

        # Retrieve
        history = memory.get_history("session-001")

        # Session expires after TTL
        memory.set_ttl("session-001", hours=24)
    """

    SESSION_PREFIX = "session:"
    DEFAULT_TTL_HOURS = 24

    def __init__(
        self,
        redis_url: str = None,
        default_ttl_hours: int = 24,
        max_messages: int = 50,
    ):
        self.redis_url = redis_url or REDIS_URL
        self.default_ttl_hours = default_ttl_hours
        self.max_messages = max_messages
        self._client = None
        self._available = False
        self._connect()

    def _connect(self) -> None:
        """Connect to Redis, fail gracefully if unavailable."""
        try:
            import redis
            self._client = redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
            self._available = True
            print(f"  Connected to Redis at {self.redis_url}")
        except Exception as e:
            print(f"  Redis not available ({e}). Using in-memory fallback.")
            self._fallback: dict[str, list] = {}
            self._available = False

    def _key(self, session_id: str) -> str:
        return f"{self.SESSION_PREFIX}{session_id}"

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to the session's conversation history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self._available:
            key = self._key(session_id)
            # Get existing messages
            existing = self._client.get(key)
            messages = json.loads(existing) if existing else []
            messages.append(message)

            # Trim to max_messages
            if len(messages) > self.max_messages:
                messages = messages[-self.max_messages:]

            # Store back with TTL refresh
            ttl_seconds = self.default_ttl_hours * 3600
            self._client.setex(key, ttl_seconds, json.dumps(messages))
        else:
            # In-memory fallback
            if session_id not in self._fallback:
                self._fallback[session_id] = []
            self._fallback[session_id].append(message)
            if len(self._fallback[session_id]) > self.max_messages:
                self._fallback[session_id] = self._fallback[session_id][-self.max_messages:]

    def get_history(
        self,
        session_id: str,
        last_n: Optional[int] = None,
    ) -> list[dict]:
        """
        Get conversation history for a session.

        Args:
            session_id: The session identifier
            last_n: Only return the last N messages (None = all)

        Returns:
            List of message dicts with role, content, timestamp
        """
        if self._available:
            key = self._key(session_id)
            raw = self._client.get(key)
            messages = json.loads(raw) if raw else []
        else:
            messages = self._fallback.get(session_id, [])

        if last_n is not None:
            messages = messages[-last_n:]

        return messages

    def get_messages_for_llm(
        self,
        session_id: str,
        system_prompt: Optional[str] = None,
        last_n: Optional[int] = None,
    ) -> list[dict]:
        """
        Get messages formatted for an LLM API call.

        Strips timestamps (LLMs don't need them) and optionally
        prepends a system prompt.
        """
        history = self.get_history(session_id, last_n=last_n)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        return messages

    def session_exists(self, session_id: str) -> bool:
        """Check if a session has any history."""
        if self._available:
            return self._client.exists(self._key(session_id)) > 0
        return session_id in self._fallback

    def delete_session(self, session_id: str) -> bool:
        """Delete a session's history."""
        if self._available:
            return self._client.delete(self._key(session_id)) > 0
        return self._fallback.pop(session_id, None) is not None

    def get_ttl(self, session_id: str) -> Optional[int]:
        """Get remaining TTL in seconds (-1 if no TTL, None if key doesn't exist)."""
        if self._available:
            ttl = self._client.ttl(self._key(session_id))
            return ttl if ttl >= 0 else None
        return None  # No TTL in fallback mode

    def extend_session(self, session_id: str, hours: int = None) -> None:
        """Reset the TTL for a session (keep it alive)."""
        if self._available:
            ttl_seconds = (hours or self.default_ttl_hours) * 3600
            self._client.expire(self._key(session_id), ttl_seconds)

    def list_active_sessions(self) -> list[str]:
        """List all active session IDs."""
        if self._available:
            keys = self._client.keys(f"{self.SESSION_PREFIX}*")
            return [k.removeprefix(self.SESSION_PREFIX) for k in keys]
        return list(self._fallback.keys())

    def get_session_stats(self, session_id: str) -> dict:
        """Get stats about a session."""
        history = self.get_history(session_id)
        if not history:
            return {"exists": False}

        turns = len([m for m in history if m["role"] == "user"])
        ttl = self.get_ttl(session_id)

        return {
            "exists": True,
            "total_messages": len(history),
            "user_turns": turns,
            "started_at": history[0]["timestamp"] if history else None,
            "last_message_at": history[-1]["timestamp"] if history else None,
            "ttl_seconds": ttl,
        }


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def demo_basic_session():
    """Show basic session creation and retrieval."""
    print("\n" + "=" * 60)
    print("  Demo 1: Basic Session Management")
    print("=" * 60)

    memory = RedisConversationMemory(default_ttl_hours=1)
    session_id = f"demo-{int(time.time())}"

    print(f"\n  Session ID: {session_id}")
    print(f"  Session exists: {memory.session_exists(session_id)}")

    # Simulate a conversation
    conversation = [
        ("user", "I can't log into my account"),
        ("assistant", "I'll help you get back in. What error are you seeing?"),
        ("user", "It says 'invalid credentials' but I'm sure the password is right"),
        ("assistant", "Let's try a password reset. What's your email address?"),
        ("user", "alice@example.com"),
        ("assistant", "I've sent a password reset link to alice@example.com. Check your inbox!"),
    ]

    for role, content in conversation:
        memory.add_message(session_id, role, content)

    print(f"  Session exists after adding messages: {memory.session_exists(session_id)}")

    # Retrieve history
    history = memory.get_history(session_id)
    print(f"\n  Full history ({len(history)} messages):")
    for msg in history:
        print(f"    [{msg['role']}]: {msg['content'][:55]}...")

    # Get last 2 messages
    recent = memory.get_history(session_id, last_n=2)
    print(f"\n  Last 2 messages:")
    for msg in recent:
        print(f"    [{msg['role']}]: {msg['content'][:55]}...")

    # Session stats
    stats = memory.get_session_stats(session_id)
    print(f"\n  Session stats: {stats}")

    # Cleanup
    memory.delete_session(session_id)
    print(f"\n  Session deleted. Exists: {memory.session_exists(session_id)}")


def demo_cross_process_continuity():
    """Show how Redis allows conversations to survive process restarts."""
    print("\n" + "=" * 60)
    print("  Demo 2: Cross-Process Session Continuity")
    print("=" * 60)

    session_id = "ticket-support-12345"
    memory = RedisConversationMemory()

    # Simulate "first process" (e.g., web worker #1)
    print("\n  [Process 1] Customer starts a conversation...")
    memory.add_message(session_id, "user", "My export is showing an empty file")
    memory.add_message(session_id, "assistant", "Sorry about that! What browser are you using?")
    memory.add_message(session_id, "user", "Chrome on Windows")
    print("  [Process 1] Done — process ends or request completes")

    # Simulate "second process" (e.g., web worker #2, next HTTP request)
    print("\n  [Process 2] Customer sends another message (different server worker)...")
    memory2 = RedisConversationMemory()  # New connection, same data

    memory2.add_message(session_id, "user", "I also tried Firefox and same issue")

    history = memory2.get_history(session_id)
    print(f"\n  [Process 2] Retrieved {len(history)} messages from Redis:")
    for msg in history:
        print(f"    [{msg['role']}]: {msg['content'][:60]}")

    print("\n  Conversation state survived the process boundary!")

    # Cleanup
    memory.delete_session(session_id)


def demo_ttl_management():
    """Show TTL-based session expiration."""
    print("\n" + "=" * 60)
    print("  Demo 3: Session TTL Management")
    print("=" * 60)

    memory = RedisConversationMemory(default_ttl_hours=1)
    session_id = f"ttl-demo-{int(time.time())}"

    memory.add_message(session_id, "user", "Hello")

    if memory._available:
        ttl = memory.get_ttl(session_id)
        print(f"\n  Session TTL after creation: {ttl} seconds (~{ttl // 60} minutes)")

        # Extend the session
        memory.extend_session(session_id, hours=24)
        ttl_extended = memory.get_ttl(session_id)
        print(f"  After extension: {ttl_extended} seconds (~{ttl_extended // 3600:.1f} hours)")

        print("\n  TTL Strategy for Support Platform:")
        print("  - Active tickets: 24h TTL, refreshed on each message")
        print("  - Resolved tickets: 1h TTL (brief window for follow-ups)")
        print("  - Idle sessions (no activity): auto-expire via TTL")
        print("  - No manual cleanup needed!")

        memory.delete_session(session_id)
    else:
        print("  (TTL demo requires Redis connection)")


def demo_list_sessions():
    """Show session enumeration."""
    print("\n" + "=" * 60)
    print("  Demo 4: Active Session Management")
    print("=" * 60)

    memory = RedisConversationMemory()

    # Create a few sessions
    session_ids = [f"customer-{i}" for i in range(1, 4)]
    for sid in session_ids:
        memory.add_message(sid, "user", f"Support request from {sid}")

    active = memory.list_active_sessions()
    print(f"\n  Active sessions: {[s for s in active if s.startswith('customer-')]}")

    # Cleanup
    for sid in session_ids:
        memory.delete_session(sid)


if __name__ == "__main__":
    demo_basic_session()
    demo_cross_process_continuity()
    demo_ttl_management()
    demo_list_sessions()
