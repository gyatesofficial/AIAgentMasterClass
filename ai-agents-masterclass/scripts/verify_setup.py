#!/usr/bin/env python3
"""
verify_setup.py - Setup Verification Script for AI Agents Course
================================================================
Run this script to verify your environment is correctly configured
before starting the course modules.

Usage:
    python scripts/verify_setup.py

What it checks:
    1. Python version (must be 3.11+)
    2. Required packages are importable
    3. API keys are set in environment
    4. Docker services are reachable (postgres, redis, chromadb)
"""

import sys
import os
import importlib
import socket
from typing import Callable

# ANSI color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Load .env file if it exists (allows running before pip install of python-dotenv)
def load_env_file():
    """Manually parse .env file without requiring python-dotenv."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    # Only set if not already in environment
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{BLUE}{'─' * 50}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'─' * 50}{RESET}")


def check_python_version() -> bool:
    """Check that Python is 3.11 or higher."""
    section("Python Version")
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major == 3 and version.minor >= 11:
        ok(f"Python {version_str} (3.11+ required)")
        return True
    else:
        fail(f"Python {version_str} found — need Python 3.11+")
        print(f"    {YELLOW}Hint: Use pyenv or conda to install Python 3.11{RESET}")
        return False


def check_packages() -> bool:
    """Check that all required packages can be imported."""
    section("Required Packages")

    packages = [
        # (import_name, display_name, critical)
        ("anthropic", "anthropic", True),
        ("openai", "openai", True),
        ("langgraph", "langgraph", True),
        ("langchain", "langchain", True),
        ("langchain_core", "langchain-core", True),
        ("langchain_openai", "langchain-openai", True),
        ("langchain_anthropic", "langchain-anthropic", True),
        ("fastapi", "fastapi", True),
        ("chromadb", "chromadb", True),
        ("redis", "redis", True),
        ("sqlalchemy", "sqlalchemy", True),
        ("pydantic", "pydantic", True),
        ("pydantic_settings", "pydantic-settings", True),
        ("dotenv", "python-dotenv", True),
        ("tenacity", "tenacity", True),
        ("tiktoken", "tiktoken", True),
        ("uvicorn", "uvicorn", False),
        ("httpx", "httpx", False),
        ("pytest", "pytest", False),
    ]

    all_critical_ok = True
    for import_name, display_name, critical in packages:
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "unknown")
            ok(f"{display_name} ({version})")
        except ImportError:
            if critical:
                fail(f"{display_name} — NOT INSTALLED (required)")
                all_critical_ok = False
            else:
                warn(f"{display_name} — not installed (optional)")

    if not all_critical_ok:
        print(f"\n  {YELLOW}Fix: pip install -r requirements.txt{RESET}")

    return all_critical_ok


def check_api_keys() -> bool:
    """Check that API keys are configured. Warns but doesn't fail."""
    section("API Keys")

    keys = [
        ("OPENAI_API_KEY", "OpenAI API Key", True),
        ("ANTHROPIC_API_KEY", "Anthropic API Key", True),
        ("LANGCHAIN_API_KEY", "LangSmith API Key (optional)", False),
    ]

    has_warnings = False
    for env_var, display_name, required in keys:
        value = os.environ.get(env_var, "")
        if value and not value.startswith("...") and "your-key" not in value:
            # Mask the key for display
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "****"
            ok(f"{display_name}: {masked}")
        elif required:
            warn(f"{display_name}: NOT SET — set {env_var} in .env file")
            has_warnings = True
        else:
            warn(f"{display_name}: not set (optional for LangSmith tracing)")

    if has_warnings:
        print(f"\n  {YELLOW}Note: Copy .env.example to .env and add your API keys{RESET}")
        print(f"  {YELLOW}The course will work without them for module 0,{RESET}")
        print(f"  {YELLOW}but modules 1+ require valid keys.{RESET}")

    # API key check never fails the suite — just warns
    return True


def check_tcp_connection(host: str, port: int, timeout: float = 2.0) -> bool:
    """Try to open a TCP connection to host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def check_chromadb_http(host: str, port: int) -> bool:
    """Try to hit ChromaDB's health endpoint."""
    try:
        import urllib.request
        url = f"http://{host}:{port}/api/v1"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_docker_services() -> bool:
    """Check that Docker services are reachable."""
    section("Docker Services")

    postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
    postgres_port = int(os.environ.get("POSTGRES_PORT", "5432"))
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    chroma_host = os.environ.get("CHROMA_HOST", "localhost")
    chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))

    # Parse redis host/port from URL
    redis_host = "localhost"
    redis_port = 6379
    if "://" in redis_url:
        parts = redis_url.split("://")[1].split(":")
        redis_host = parts[0]
        redis_port = int(parts[1]) if len(parts) > 1 else 6379

    all_ok = True

    # PostgreSQL
    if check_tcp_connection(postgres_host, postgres_port):
        # Try actual connection if psycopg2 is available
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=postgres_host,
                port=postgres_port,
                user=os.environ.get("POSTGRES_USER", "agents_user"),
                password=os.environ.get("POSTGRES_PASSWORD", "agents_password"),
                dbname=os.environ.get("POSTGRES_DB", "agents_db"),
                connect_timeout=3,
            )
            conn.close()
            ok(f"PostgreSQL at {postgres_host}:{postgres_port} (connected successfully)")
        except Exception as e:
            warn(f"PostgreSQL port open but auth failed: {e}")
    else:
        fail(f"PostgreSQL at {postgres_host}:{postgres_port} — not reachable")
        print(f"    {YELLOW}Fix: docker compose up -d postgres{RESET}")
        all_ok = False

    # Redis
    if check_tcp_connection(redis_host, redis_port):
        try:
            import redis as redis_lib
            r = redis_lib.Redis(host=redis_host, port=redis_port, socket_timeout=2)
            r.ping()
            ok(f"Redis at {redis_host}:{redis_port} (PING → PONG)")
        except Exception as e:
            warn(f"Redis port open but ping failed: {e}")
    else:
        fail(f"Redis at {redis_host}:{redis_port} — not reachable")
        print(f"    {YELLOW}Fix: docker compose up -d redis{RESET}")
        all_ok = False

    # ChromaDB
    if check_tcp_connection(chroma_host, chroma_port):
        if check_chromadb_http(chroma_host, chroma_port):
            ok(f"ChromaDB at {chroma_host}:{chroma_port} (HTTP API healthy)")
        else:
            warn(f"ChromaDB port open but API not responding at /api/v1")
    else:
        fail(f"ChromaDB at {chroma_host}:{chroma_port} — not reachable")
        print(f"    {YELLOW}Fix: docker compose up -d chromadb{RESET}")
        all_ok = False

    if not all_ok:
        print(f"\n  {YELLOW}To start all services: docker compose up -d{RESET}")

    return all_ok


def print_summary(results: dict[str, bool]) -> None:
    """Print a final pass/fail summary."""
    section("Summary")

    all_passed = all(results.values())

    for check_name, passed in results.items():
        if passed:
            ok(check_name)
        else:
            fail(check_name)

    print()
    if all_passed:
        print(f"{BOLD}{GREEN}  ✓ All checks passed! You're ready to start the course.{RESET}")
        print(f"\n  Next step: Open module_00_foundations/README.md")
    else:
        failed = [name for name, passed in results.items() if not passed]
        print(f"{BOLD}{RED}  ✗ {len(failed)} check(s) failed. See details above.{RESET}")
        print(f"\n  Check the README.md for setup instructions.")

    print()


def main():
    print(f"\n{BOLD}AI Agents Course — Environment Verification{RESET}")
    print(f"{'=' * 50}")
    print(f"Repository: https://github.com/gyatesofficial/AIAgentMasterClass")

    # Load .env before running checks
    load_env_file()

    results = {
        "Python 3.11+": check_python_version(),
        "Required packages": check_packages(),
        "API keys configured": check_api_keys(),
        "Docker services": check_docker_services(),
    }

    print_summary(results)

    # Exit with non-zero code if critical checks failed
    critical = ["Python 3.11+", "Required packages"]
    if any(not results[c] for c in critical):
        sys.exit(1)


if __name__ == "__main__":
    main()
