"""
customer_db.py - Customer Database Tools
=========================================
Tools for querying and updating customer data and tickets.
Used by the triage and resolution agents.

All functions work with the SQLAlchemy models and return plain dicts
(not ORM objects) so they can be serialized to JSON and returned to the LLM.

Usage:
    from support_platform.tools.customer_db import (
        get_customer_by_email,
        get_customer_tickets,
        update_ticket_status,
        add_ticket_note,
    )
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError


def _get_session():
    """Get a database session, with graceful fallback."""
    try:
        from support_platform.database.models import get_session
        return get_session()
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Customer queries
# ──────────────────────────────────────────────────────────────

def get_customer_by_id(customer_id: str) -> dict:
    """
    Look up a customer by their UUID.

    Args:
        customer_id: Customer UUID string

    Returns:
        Customer data dict, or {"error": "..."} if not found
    """
    session = _get_session()
    if not session:
        return {"error": "Database not available"}

    try:
        from support_platform.database.models import Customer
        customer = session.query(Customer).filter_by(
            id=uuid.UUID(customer_id)
        ).first()

        if not customer:
            return {"error": f"Customer not found: {customer_id}"}

        return customer.to_dict()

    except ValueError:
        return {"error": f"Invalid customer ID format: {customer_id}"}
    except SQLAlchemyError as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        session.close()


def get_customer_by_email(email: str) -> dict:
    """
    Look up a customer by their email address.

    Args:
        email: Customer's email address

    Returns:
        Customer data dict, or {"error": "..."} if not found
    """
    session = _get_session()
    if not session:
        return _mock_customer_by_email(email)

    try:
        from support_platform.database.models import Customer
        customer = session.query(Customer).filter(
            Customer.email.ilike(email)
        ).first()

        if not customer:
            return {"error": f"No customer found with email: {email}"}

        return customer.to_dict()

    except SQLAlchemyError as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        session.close()


def _mock_customer_by_email(email: str) -> dict:
    """Mock customer lookup for when DB is unavailable."""
    mock_data = {
        "alice@example.com": {
            "id": "a1a1a1a1-0000-0000-0000-000000000001",
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "account_status": "active",
            "subscription_tier": "pro",
            "created_at": "2022-03-15T00:00:00",
        },
        "bob@example.com": {
            "id": "b2b2b2b2-0000-0000-0000-000000000002",
            "name": "Bob Smith",
            "email": "bob@example.com",
            "account_status": "active",
            "subscription_tier": "starter",
            "created_at": "2023-07-22T00:00:00",
        },
    }
    customer = mock_data.get(email.lower())
    if customer:
        return customer
    return {"error": f"No customer found with email: {email}"}


# ──────────────────────────────────────────────────────────────
# Ticket queries
# ──────────────────────────────────────────────────────────────

def get_customer_tickets(
    email: str = None,
    customer_id: str = None,
    status_filter: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Get a customer's ticket history.

    Args:
        email: Customer's email (either email or customer_id required)
        customer_id: Customer's UUID
        status_filter: Filter by status ('open', 'resolved', etc.) or None for all
        limit: Maximum number of tickets to return

    Returns:
        List of ticket dicts, sorted most recent first
    """
    session = _get_session()
    if not session:
        return []

    try:
        from support_platform.database.models import Ticket

        query = session.query(Ticket)

        if email:
            query = query.filter(Ticket.email.ilike(email))
        elif customer_id:
            query = query.filter_by(customer_id=uuid.UUID(customer_id))
        else:
            return []

        if status_filter:
            query = query.filter(Ticket.status == status_filter)

        tickets = (
            query.order_by(Ticket.created_at.desc())
            .limit(limit)
            .all()
        )

        return [t.to_dict() for t in tickets]

    except SQLAlchemyError as e:
        return [{"error": f"Database error: {str(e)}"}]
    finally:
        session.close()


def get_ticket_by_id(ticket_id: str) -> dict:
    """
    Get a specific ticket by its UUID.

    Args:
        ticket_id: Ticket UUID string

    Returns:
        Ticket data dict, or {"error": "..."} if not found
    """
    session = _get_session()
    if not session:
        return {"error": "Database not available"}

    try:
        from support_platform.database.models import Ticket
        ticket = session.query(Ticket).filter_by(
            id=uuid.UUID(ticket_id)
        ).first()

        if not ticket:
            return {"error": f"Ticket not found: {ticket_id}"}

        return ticket.to_dict()

    except ValueError:
        return {"error": f"Invalid ticket ID format: {ticket_id}"}
    except SQLAlchemyError as e:
        return {"error": f"Database error: {str(e)}"}
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────
# Ticket mutations
# ──────────────────────────────────────────────────────────────

def update_ticket_status(
    ticket_id: str,
    new_status: str,
    resolution: Optional[str] = None,
) -> dict:
    """
    Update a ticket's status and optionally set a resolution.

    Args:
        ticket_id: Ticket UUID string
        new_status: New status ('open', 'in_progress', 'waiting_customer',
                    'escalated', 'resolved', 'closed')
        resolution: Resolution text (required if new_status='resolved')

    Returns:
        Updated ticket dict, or {"error": "..."} on failure
    """
    valid_statuses = {
        "open", "in_progress", "waiting_customer",
        "escalated", "resolved", "closed"
    }

    if new_status not in valid_statuses:
        return {"error": f"Invalid status '{new_status}'. Valid: {sorted(valid_statuses)}"}

    if new_status == "resolved" and not resolution:
        return {"error": "resolution text is required when status is 'resolved'"}

    session = _get_session()
    if not session:
        # Mock success for demo purposes
        return {
            "success": True,
            "ticket_id": ticket_id,
            "new_status": new_status,
            "updated_at": datetime.utcnow().isoformat(),
        }

    try:
        from support_platform.database.models import Ticket
        ticket = session.query(Ticket).filter_by(
            id=uuid.UUID(ticket_id)
        ).first()

        if not ticket:
            return {"error": f"Ticket not found: {ticket_id}"}

        old_status = ticket.status
        ticket.status = new_status
        ticket.updated_at = datetime.utcnow()

        if resolution:
            ticket.resolution = resolution

        session.commit()
        session.refresh(ticket)

        return {
            "success": True,
            "ticket_id": str(ticket.id),
            "old_status": old_status,
            "new_status": new_status,
            "updated_at": ticket.updated_at.isoformat(),
        }

    except ValueError:
        return {"error": f"Invalid ticket ID format: {ticket_id}"}
    except SQLAlchemyError as e:
        session.rollback()
        return {"error": f"Database error: {str(e)}"}
    finally:
        session.close()


def add_ticket_note(ticket_id: str, note: str) -> dict:
    """
    Append a note to a ticket's agent_notes field.

    Agent notes are internal — not shown to the customer.
    Each note is timestamped.

    Args:
        ticket_id: Ticket UUID string
        note: Note text to append

    Returns:
        Dict with success status
    """
    session = _get_session()
    if not session:
        return {"success": True, "ticket_id": ticket_id, "note": note}

    try:
        from support_platform.database.models import Ticket
        ticket = session.query(Ticket).filter_by(
            id=uuid.UUID(ticket_id)
        ).first()

        if not ticket:
            return {"error": f"Ticket not found: {ticket_id}"}

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        new_note = f"[{timestamp}] {note}"
        ticket.agent_notes = (
            f"{ticket.agent_notes}\n{new_note}"
            if ticket.agent_notes
            else new_note
        )
        ticket.updated_at = datetime.utcnow()

        session.commit()

        return {
            "success": True,
            "ticket_id": str(ticket.id),
            "note_added": new_note,
        }

    except ValueError:
        return {"error": f"Invalid ticket ID format: {ticket_id}"}
    except SQLAlchemyError as e:
        session.rollback()
        return {"error": f"Database error: {str(e)}"}
    finally:
        session.close()


def log_agent_interaction(
    ticket_id: str,
    agent_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
) -> Optional[str]:
    """
    Log an LLM call to the agent_interactions table for cost tracking.

    Args:
        ticket_id: Ticket being processed
        agent_type: Which agent made this call ('triage', 'resolution', etc.)
        model: Model used (e.g., 'gpt-4o')
        input_tokens: Input token count
        output_tokens: Output token count
        cost_usd: Estimated cost in USD
        latency_ms: Latency in milliseconds

    Returns:
        Interaction ID as string, or None on error
    """
    session = _get_session()
    if not session:
        return None

    try:
        from support_platform.database.models import AgentInteraction
        interaction = AgentInteraction(
            ticket_id=uuid.UUID(ticket_id),
            agent_type=agent_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        session.add(interaction)
        session.commit()
        return str(interaction.id)

    except Exception as e:
        session.rollback()
        return None
    finally:
        session.close()
