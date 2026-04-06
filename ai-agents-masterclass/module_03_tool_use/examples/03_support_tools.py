"""
03_support_tools.py - Customer Support Platform Tools
======================================================
Module 3: Tool Use & Function Calling

These are the actual tools used by the AI support agents throughout the course.
They use mock data here, but the signatures and patterns match the production
versions in support_platform/tools/.

Tools:
- search_knowledge_base: Find relevant KB articles by keyword/semantic similarity
- get_customer_info: Look up customer account details
- get_ticket_history: Get a customer's previous support tickets
- update_ticket_status: Change status, add notes, set resolution
- send_email_notification: Send email to customer

Run with: python module_03_tool_use/examples/03_support_tools.py
No API keys needed — all mock data.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Mock data
# ──────────────────────────────────────────────────────────────

MOCK_CUSTOMERS = {
    "alice@example.com": {
        "id": "cust_001",
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "plan": "Pro",
        "status": "active",
        "created_at": "2022-03-15",
        "total_tickets": 5,
        "notes": "Enterprise prospect, high-value customer",
    },
    "bob@example.com": {
        "id": "cust_002",
        "name": "Bob Smith",
        "email": "bob@example.com",
        "plan": "Starter",
        "status": "active",
        "created_at": "2023-07-22",
        "total_tickets": 2,
        "notes": "",
    },
    "carol@suspended.com": {
        "id": "cust_003",
        "name": "Carol White",
        "email": "carol@suspended.com",
        "plan": "Free",
        "status": "suspended",
        "created_at": "2023-01-10",
        "total_tickets": 8,
        "notes": "Account suspended due to payment failure",
    },
}

MOCK_TICKET_HISTORY = {
    "cust_001": [
        {
            "id": "TKT-0001",
            "subject": "Password reset not working",
            "category": "account_access",
            "priority": "high",
            "status": "resolved",
            "created_at": "2024-01-10",
            "resolved_at": "2024-01-10",
            "resolution": "Sent manual reset link, issue resolved",
        },
        {
            "id": "TKT-0023",
            "subject": "Need invoice for January",
            "category": "billing",
            "priority": "low",
            "status": "resolved",
            "created_at": "2024-02-01",
            "resolved_at": "2024-02-01",
            "resolution": "Sent PDF invoice via email",
        },
    ],
    "cust_002": [
        {
            "id": "TKT-0045",
            "subject": "CSV export is empty",
            "category": "technical_bug",
            "priority": "medium",
            "status": "resolved",
            "created_at": "2024-03-05",
            "resolved_at": "2024-03-06",
            "resolution": "Fixed by clearing browser cache",
        },
    ],
}

MOCK_KB_ARTICLES = [
    {
        "id": "kb_001",
        "title": "How to Reset Your Password",
        "category": "account_access",
        "content": "1. Go to /forgot-password. 2. Enter email. 3. Check inbox (check spam). 4. Click link (24h expiry). 5. Set new password.",
        "tags": ["password", "login", "reset", "forgot"],
        "relevance_score": None,
    },
    {
        "id": "kb_002",
        "title": "Two-Factor Authentication Troubleshooting",
        "category": "account_access",
        "content": "If your 2FA codes don't work after getting a new phone: 1. Use backup codes from setup. 2. If lost, contact support with account verification. We'll disable 2FA within 1 business day.",
        "tags": ["2fa", "authenticator", "security", "phone"],
        "relevance_score": None,
    },
    {
        "id": "kb_003",
        "title": "Understanding Your Invoice",
        "category": "billing",
        "content": "Invoices are sent on your billing date. Download at Settings > Billing > History. For VAT invoices, add your VAT number at Settings > Billing > Tax Info.",
        "tags": ["invoice", "billing", "vat", "receipt"],
        "relevance_score": None,
    },
    {
        "id": "kb_004",
        "title": "Requesting a Refund",
        "category": "billing",
        "content": "Annual plans: refundable within 30 days. Monthly plans: non-refundable. Duplicate charges: refunded immediately. Contact billing@support.io with charge details.",
        "tags": ["refund", "billing", "charge", "duplicate"],
        "relevance_score": None,
    },
    {
        "id": "kb_005",
        "title": "Export Troubleshooting",
        "category": "technical_bug",
        "content": "If export downloads empty file: 1. Check active filters. 2. Clear browser cache. 3. Try different browser. Large exports (>10k rows) are emailed. Free plan limited to 1,000 rows.",
        "tags": ["export", "csv", "download", "empty"],
        "relevance_score": None,
    },
    {
        "id": "kb_006",
        "title": "API Rate Limits and Error Codes",
        "category": "technical_bug",
        "content": "Rate limits: Free 30/min, Pro 500/min, Enterprise custom. 429 error means rate limited — implement exponential backoff. Check X-RateLimit-Remaining header.",
        "tags": ["api", "rate limit", "429", "integration"],
        "relevance_score": None,
    },
    {
        "id": "kb_007",
        "title": "Plan Comparison and Upgrading",
        "category": "general_inquiry",
        "content": "Free: 1 user, basic features. Starter ($29/mo): 5 users + integrations. Pro ($79/mo): 25 users + advanced analytics. Enterprise: unlimited users + SSO + SLA.",
        "tags": ["plan", "upgrade", "pricing", "features"],
        "relevance_score": None,
    },
    {
        "id": "kb_008",
        "title": "Data Export and Account Cancellation",
        "category": "general_inquiry",
        "content": "Before cancelling: export all data at Settings > Export Data (ZIP file with CSVs). After cancellation, data retained for 30 days. Cancellation at Settings > Account > Cancel.",
        "tags": ["cancel", "export", "data", "account"],
        "relevance_score": None,
    },
]

# Simulated ticket database (mutable for update demo)
TICKET_DB: dict[str, dict] = {}


# ──────────────────────────────────────────────────────────────
# Tool 1: search_knowledge_base
# ──────────────────────────────────────────────────────────────

def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    n_results: int = 3,
) -> list[dict]:
    """
    Search the knowledge base for articles relevant to a support query.

    In production (Module 6): embeds the query and searches ChromaDB by
    cosine similarity. Here: simple keyword matching for demonstration.

    Args:
        query: Natural language query describing what the customer needs
        category: Optional filter by article category
        n_results: Maximum number of articles to return

    Returns:
        List of relevant articles with title, content, and relevance score
    """
    query_lower = query.lower()
    scored_articles = []

    for article in MOCK_KB_ARTICLES:
        # Skip if category filter doesn't match
        if category and article["category"] != category:
            continue

        # Score based on keyword matches
        score = 0.0
        for tag in article["tags"]:
            if tag in query_lower:
                score += 0.3
        for word in article["title"].lower().split():
            if word in query_lower and len(word) > 3:
                score += 0.1
        if score > 0:
            article_copy = dict(article)
            article_copy["relevance_score"] = round(min(score, 1.0), 2)
            scored_articles.append(article_copy)

    # Sort by relevance
    scored_articles.sort(key=lambda x: x["relevance_score"], reverse=True)

    return scored_articles[:n_results]


# ──────────────────────────────────────────────────────────────
# Tool 2: get_customer_info
# ──────────────────────────────────────────────────────────────

def get_customer_info(email: str = None, customer_id: str = None) -> dict:
    """
    Look up a customer's account information.

    Args:
        email: Customer's email address (preferred)
        customer_id: Customer's ID (alternative to email)

    Returns:
        Customer account details dict, or error dict if not found
    """
    if email:
        customer = MOCK_CUSTOMERS.get(email.lower())
        if customer:
            return customer
        return {"error": f"No customer found with email '{email}'"}

    elif customer_id:
        for customer in MOCK_CUSTOMERS.values():
            if customer["id"] == customer_id:
                return customer
        return {"error": f"No customer found with ID '{customer_id}'"}

    return {"error": "Must provide either 'email' or 'customer_id'"}


# ──────────────────────────────────────────────────────────────
# Tool 3: get_ticket_history
# ──────────────────────────────────────────────────────────────

def get_ticket_history(
    customer_id: str = None,
    email: str = None,
    limit: int = 5,
    status_filter: Optional[str] = None,
) -> list[dict]:
    """
    Get a customer's previous support ticket history.

    Useful for understanding repeat issues and the customer's experience.
    Always check ticket history before resolving billing or escalation issues.

    Args:
        customer_id: Customer's ID
        email: Customer's email (used if customer_id not provided)
        limit: Maximum number of tickets to return (most recent first)
        status_filter: Optional filter by status ('open', 'resolved', etc.)

    Returns:
        List of previous tickets, most recent first
    """
    # Resolve customer_id from email if needed
    if not customer_id and email:
        customer = MOCK_CUSTOMERS.get(email.lower())
        if customer:
            customer_id = customer["id"]
        else:
            return []

    if not customer_id:
        return []

    tickets = MOCK_TICKET_HISTORY.get(customer_id, [])

    if status_filter:
        tickets = [t for t in tickets if t["status"] == status_filter]

    # Return most recent first
    return sorted(tickets, key=lambda x: x["created_at"], reverse=True)[:limit]


# ──────────────────────────────────────────────────────────────
# Tool 4: update_ticket_status
# ──────────────────────────────────────────────────────────────

def update_ticket_status(
    ticket_id: str,
    status: str,
    notes: Optional[str] = None,
    resolution: Optional[str] = None,
) -> dict:
    """
    Update a ticket's status, add notes, or record a resolution.

    Args:
        ticket_id: The ticket ID to update (e.g., 'TKT-00123')
        status: New status: 'open', 'in_progress', 'waiting_customer', 'resolved', 'escalated'
        notes: Internal notes for the support team
        resolution: Resolution text to show the customer (required if status='resolved')

    Returns:
        Updated ticket dict, or error dict if ticket not found
    """
    valid_statuses = {"open", "in_progress", "waiting_customer", "resolved", "escalated", "closed"}

    if status not in valid_statuses:
        return {"error": f"Invalid status '{status}'. Valid: {valid_statuses}"}

    if status == "resolved" and not resolution:
        return {"error": "Resolution text is required when setting status to 'resolved'"}

    # Get or create ticket in mock DB
    ticket = TICKET_DB.get(ticket_id, {"id": ticket_id, "status": "open"})
    old_status = ticket.get("status", "open")

    ticket["status"] = status
    ticket["updated_at"] = datetime.utcnow().isoformat()

    if notes:
        existing_notes = ticket.get("agent_notes", "")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        ticket["agent_notes"] = f"{existing_notes}\n[{timestamp}] {notes}".strip()

    if resolution:
        ticket["resolution"] = resolution

    TICKET_DB[ticket_id] = ticket

    return {
        "success": True,
        "ticket_id": ticket_id,
        "old_status": old_status,
        "new_status": status,
        "updated_at": ticket["updated_at"],
    }


# ──────────────────────────────────────────────────────────────
# Tool 5: send_email_notification
# ──────────────────────────────────────────────────────────────

def send_email_notification(
    to_email: str,
    subject: str,
    body: str,
    template: Optional[str] = None,
) -> dict:
    """
    Send an email notification to a customer.

    Use this to confirm actions, send resolutions, or request more information.
    Only use for support-related communications — not marketing.

    Args:
        to_email: Recipient's email address
        subject: Email subject line
        body: Email body text (plain text or simple HTML)
        template: Optional template name ('resolution', 'follow_up', 'escalation')

    Returns:
        Dict with success status and message_id
    """
    # Validate email format (basic check)
    if "@" not in to_email or "." not in to_email.split("@")[-1]:
        return {"error": f"Invalid email address: {to_email}"}

    # Subject length check
    if len(subject) > 200:
        return {"error": "Subject line too long (max 200 characters)"}

    # Simulate sending (in production: use SendGrid, SES, etc.)
    message_id = f"msg_{uuid.uuid4().hex[:8]}"

    print(f"\n  [MOCK EMAIL SENT]")
    print(f"  To:      {to_email}")
    print(f"  Subject: {subject}")
    print(f"  Body:    {body[:100]}...")

    return {
        "success": True,
        "message_id": message_id,
        "to_email": to_email,
        "subject": subject,
        "sent_at": datetime.utcnow().isoformat(),
    }


# ──────────────────────────────────────────────────────────────
# Demo: Show all tools in action
# ──────────────────────────────────────────────────────────────

def demo_all_tools():
    """Walk through each tool with realistic examples."""

    print("\n" + "=" * 60)
    print("  Support Platform Tools Demo")
    print("=" * 60)

    # ── Tool 1: Knowledge Base Search ──────────────────────
    print("\n  Tool 1: search_knowledge_base")
    print("  ─────────────────────────────")

    result = search_knowledge_base("I can't log in with my authenticator app after new phone")
    print(f"  Query: 'I can't log in with my authenticator app after new phone'")
    print(f"  Results ({len(result)}):")
    for article in result:
        print(f"    [{article['relevance_score']:.2f}] {article['title']}")
        print(f"           {article['content'][:70]}...")

    # ── Tool 2: Customer Info ───────────────────────────────
    print("\n  Tool 2: get_customer_info")
    print("  ─────────────────────────")

    customer = get_customer_info(email="alice@example.com")
    print(f"  Customer: alice@example.com")
    print(f"  Result: {json.dumps(customer, indent=2)}")

    not_found = get_customer_info(email="nobody@example.com")
    print(f"\n  Not found: {not_found}")

    # ── Tool 3: Ticket History ──────────────────────────────
    print("\n  Tool 3: get_ticket_history")
    print("  ──────────────────────────")

    history = get_ticket_history(email="alice@example.com")
    print(f"  Alice's ticket history ({len(history)} tickets):")
    for ticket in history:
        print(f"    {ticket['id']}: {ticket['subject']} [{ticket['status']}]")

    # ── Tool 4: Update Ticket Status ───────────────────────
    print("\n  Tool 4: update_ticket_status")
    print("  ─────────────────────────────")

    # Initialize a ticket first
    TICKET_DB["TKT-99001"] = {
        "id": "TKT-99001",
        "customer_email": "alice@example.com",
        "status": "open",
        "subject": "Can't log in with 2FA",
    }

    result = update_ticket_status(
        ticket_id="TKT-99001",
        status="resolved",
        notes="Customer confirmed 2FA re-setup worked",
        resolution="Guided customer through 2FA reset using backup codes. Issue resolved.",
    )
    print(f"  Updating TKT-99001:")
    print(f"  Result: {json.dumps(result, indent=2)}")

    # ── Tool 5: Send Email ──────────────────────────────────
    print("\n  Tool 5: send_email_notification")
    print("  ─────────────────────────────────")

    result = send_email_notification(
        to_email="alice@example.com",
        subject="Your support ticket TKT-99001 has been resolved",
        body=(
            "Hi Alice,\n\n"
            "We've resolved your ticket about 2FA login issues.\n\n"
            "Resolution: We guided you through resetting 2FA using backup codes. "
            "Please save your new backup codes in a secure location.\n\n"
            "Let us know if you need any further assistance!\n\n"
            "Best,\nSupport Team"
        ),
    )
    print(f"\n  Email result: {json.dumps(result, indent=2)}")


def demo_simulated_agent_flow():
    """Show how these tools would be used in sequence by an agent."""
    print("\n" + "=" * 60)
    print("  Simulated Agent Workflow")
    print("=" * 60)
    print("\n  Ticket: 'I got a new phone and now my 2FA codes don't work'")
    print("  Customer email: alice@example.com")
    print()

    steps = [
        ("Step 1", "Search KB for 2FA troubleshooting",
         lambda: search_knowledge_base("2fa authenticator phone lost codes")),
        ("Step 2", "Get customer account info",
         lambda: get_customer_info(email="alice@example.com")),
        ("Step 3", "Check previous ticket history",
         lambda: get_ticket_history(email="alice@example.com")),
        ("Step 4", "Update ticket status to in_progress",
         lambda: update_ticket_status(
             "TKT-00200",
             "in_progress",
             notes="Customer confirmed new phone, lost 2FA access. Guiding through recovery."
         )),
        ("Step 5", "Send resolution to customer",
         lambda: send_email_notification(
             "alice@example.com",
             "Resolving your 2FA issue [TKT-00200]",
             "Hi Alice, here are your recovery steps...",
         )),
    ]

    for step_name, description, fn in steps:
        print(f"  {step_name}: {description}")
        result = fn()
        if isinstance(result, list):
            print(f"    → {len(result)} result(s)")
        elif isinstance(result, dict):
            print(f"    → {json.dumps(result, indent=2)[:100]}...")
        print()


if __name__ == "__main__":
    demo_all_tools()
    demo_simulated_agent_flow()
