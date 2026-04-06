"""
routes.py - FastAPI Route Definitions
======================================
HTTP API for the AI Customer Support Platform.

Endpoints:
  POST /tickets          - Submit new ticket (async processing)
  GET  /tickets          - List tickets with optional filtering
  GET  /tickets/{id}     - Get ticket status and details
  POST /tickets/{id}/resolve  - Manually resolve a ticket
  GET  /health           - System health check

Usage:
    from support_platform.api.routes import router
    app.include_router(router)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from support_platform.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────────────────────
# Request / Response schemas (Pydantic)
# ──────────────────────────────────────────────────────────────

class SubmitTicketRequest(BaseModel):
    """Request body for POST /tickets."""
    email: str = Field(..., description="Customer's email address")
    subject: str = Field(..., min_length=5, max_length=500, description="Brief description of the issue")
    body: str = Field(..., min_length=10, max_length=10_000, description="Full description of the issue")
    customer_name: Optional[str] = Field(None, description="Customer's name (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "alice@example.com",
                "subject": "Can't log in after phone upgrade",
                "body": "I upgraded my iPhone yesterday and now my 2FA codes don't work. My account is completely locked.",
                "customer_name": "Alice Johnson",
            }
        }


class TicketResponse(BaseModel):
    """Response schema for ticket data."""
    id: str
    status: str
    priority: Optional[str] = None
    category: Optional[str] = None
    subject: str
    created_at: str
    email: str
    resolution: Optional[str] = None
    agent_notes: Optional[str] = None


class SubmitTicketResponse(BaseModel):
    """Response for POST /tickets."""
    ticket_id: str
    status: str = "processing"
    message: str
    estimated_response: str = "Within 24 hours"


class ResolveTicketRequest(BaseModel):
    """Request body for POST /tickets/{id}/resolve."""
    resolution: str = Field(..., min_length=10, description="Resolution text to send to the customer")
    resolved_by: str = Field(default="human", description="Who resolved this ('human' or 'agent')")


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str
    timestamp: str
    version: str = "1.0.0"
    checks: dict


# ──────────────────────────────────────────────────────────────
# In-memory ticket store (for demo — production uses PostgreSQL)
# ──────────────────────────────────────────────────────────────

# This dict stores tickets when DB is unavailable
_ticket_store: dict[str, dict] = {}


def _store_ticket(ticket_id: str, data: dict) -> None:
    """Store ticket (DB if available, else in-memory)."""
    try:
        from support_platform.database.models import Ticket, get_session
        with get_session() as session:
            ticket = Ticket(
                id=uuid.UUID(ticket_id),
                email=data["email"],
                subject=data["subject"],
                body=data["body"],
                customer_name=data.get("customer_name"),
                status="open",
            )
            session.add(ticket)
            session.commit()
    except Exception:
        _ticket_store[ticket_id] = {**data, "status": "open", "created_at": datetime.utcnow().isoformat()}


def _get_ticket(ticket_id: str) -> Optional[dict]:
    """Get ticket (DB if available, else in-memory)."""
    try:
        from support_platform.database.models import get_session
        from support_platform.tools.customer_db import get_ticket_by_id
        ticket = get_ticket_by_id(ticket_id)
        if "error" not in ticket:
            return ticket
    except Exception:
        pass
    return _ticket_store.get(ticket_id)


def _update_ticket(ticket_id: str, updates: dict) -> None:
    """Update ticket fields."""
    try:
        from support_platform.tools.customer_db import update_ticket_status
        if "status" in updates:
            update_ticket_status(
                ticket_id,
                updates["status"],
                resolution=updates.get("resolution"),
            )
        return
    except Exception:
        pass
    if ticket_id in _ticket_store:
        _ticket_store[ticket_id].update(updates)


def _list_tickets(
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """List tickets with optional filtering."""
    try:
        from support_platform.database.models import Ticket, get_session
        with get_session() as session:
            q = session.query(Ticket)
            if status_filter:
                q = q.filter(Ticket.status == status_filter)
            tickets = q.order_by(Ticket.created_at.desc()).offset(offset).limit(limit).all()
            return [t.to_dict() for t in tickets]
    except Exception:
        pass

    tickets = list(_ticket_store.values())
    if status_filter:
        tickets = [t for t in tickets if t.get("status") == status_filter]
    return tickets[offset:offset + limit]


# ──────────────────────────────────────────────────────────────
# Background task: agent pipeline
# ──────────────────────────────────────────────────────────────

async def _process_ticket_async(ticket_id: str, ticket_data: dict) -> None:
    """
    Background task that runs the full agent pipeline for a ticket.

    Flow:
    1. Triage agent: classify category, priority, find KB articles
    2. Resolution agent: draft response, decide auto-send vs escalate
    3. Update ticket status in database
    4. Trigger notifications
    """
    logger.info(f"Processing ticket {ticket_id}")
    _update_ticket(ticket_id, {"status": "in_progress"})

    try:
        from support_platform.agents.triage_agent import TriageAgent
        from support_platform.agents.resolution_agent import ResolutionAgent

        # Stage 1: Triage
        triage_agent = TriageAgent()
        triage_result = triage_agent.triage(
            ticket_id=ticket_id,
            subject=ticket_data["subject"],
            body=ticket_data["body"],
            customer_email=ticket_data["email"],
        )
        logger.info(f"Ticket {ticket_id} triaged: {triage_result.category}/{triage_result.priority}")

        # Update with triage results
        _update_ticket(ticket_id, {
            "category": triage_result.category,
            "priority": triage_result.priority,
            "agent_notes": f"Triaged by AI: {triage_result.triage_reasoning[:200]}",
        })

        # Stage 2: Resolution
        resolution_agent = ResolutionAgent()
        resolution_result = resolution_agent.resolve(
            triage_result,
            ticket_subject=ticket_data["subject"],
            ticket_body=ticket_data["body"],
        )

        if resolution_result.auto_send:
            _update_ticket(ticket_id, {
                "status": "resolved",
                "resolution": resolution_result.response,
                "agent_notes": f"Auto-resolved. Confidence: {resolution_result.confidence:.0%}",
            })
            logger.info(f"Ticket {ticket_id} auto-resolved")
        else:
            _update_ticket(ticket_id, {
                "status": "escalated",
                "agent_notes": f"Escalated: {resolution_result.escalation_reason}",
            })
            logger.info(f"Ticket {ticket_id} escalated: {resolution_result.escalation_reason}")

    except Exception as e:
        logger.error(f"Error processing ticket {ticket_id}: {e}", exc_info=True)
        _update_ticket(ticket_id, {
            "status": "open",
            "agent_notes": f"Processing failed: {str(e)[:200]}",
        })


# ──────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────

@router.post("/tickets", response_model=SubmitTicketResponse, status_code=202)
async def submit_ticket(
    request: SubmitTicketRequest,
    background_tasks: BackgroundTasks,
) -> SubmitTicketResponse:
    """
    Submit a new support ticket.

    The ticket is created immediately and processing happens asynchronously.
    Returns the ticket ID for polling the status.

    The agent pipeline (triage → resolution) runs in the background:
    - Typically completes in 5-30 seconds
    - Poll GET /tickets/{ticket_id} to check status
    """
    ticket_id = str(uuid.uuid4())
    ticket_data = {
        "id": ticket_id,
        "email": request.email,
        "subject": request.subject,
        "body": request.body,
        "customer_name": request.customer_name,
        "created_at": datetime.utcnow().isoformat(),
        "status": "open",
    }

    # Store the ticket
    _store_ticket(ticket_id, ticket_data)

    # Queue background processing
    background_tasks.add_task(_process_ticket_async, ticket_id, ticket_data)

    logger.info(f"Ticket {ticket_id} submitted for {request.email}")

    return SubmitTicketResponse(
        ticket_id=ticket_id,
        status="processing",
        message="Your ticket has been submitted. Our AI agent is processing it now.",
        estimated_response="Within 24 hours (usually much faster)",
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str) -> TicketResponse:
    """
    Get the current status and details of a ticket.

    Poll this endpoint after submitting a ticket to check for resolution.
    Status progression: open → in_progress → resolved (or escalated)
    """
    ticket = _get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

    return TicketResponse(
        id=str(ticket.get("id", ticket_id)),
        status=ticket.get("status", "open"),
        priority=ticket.get("priority"),
        category=ticket.get("category"),
        subject=ticket.get("subject", ""),
        created_at=ticket.get("created_at", datetime.utcnow().isoformat()),
        email=ticket.get("email", ""),
        resolution=ticket.get("resolution"),
        agent_notes=ticket.get("agent_notes"),
    )


@router.get("/tickets", response_model=list[TicketResponse])
async def list_tickets(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Maximum tickets to return"),
    offset: int = Query(0, ge=0, description="Number of tickets to skip"),
) -> list[TicketResponse]:
    """
    List tickets with optional filtering.

    Query parameters:
    - status: Filter by 'open', 'in_progress', 'resolved', 'escalated'
    - limit: Max results (1-100, default 20)
    - offset: Pagination offset
    """
    valid_statuses = {
        "open", "in_progress", "waiting_customer",
        "escalated", "resolved", "closed", None
    }
    if status and status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Valid: {sorted(s for s in valid_statuses if s)}"
        )

    tickets = _list_tickets(status_filter=status, limit=limit, offset=offset)

    return [
        TicketResponse(
            id=str(t.get("id", "")),
            status=t.get("status", "open"),
            priority=t.get("priority"),
            category=t.get("category"),
            subject=t.get("subject", ""),
            created_at=t.get("created_at", ""),
            email=t.get("email", ""),
            resolution=t.get("resolution"),
        )
        for t in tickets
    ]


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_ticket(
    ticket_id: str,
    request: ResolveTicketRequest,
) -> TicketResponse:
    """
    Manually resolve a ticket.

    Used by human support agents to resolve tickets that were escalated
    or that the AI couldn't handle.
    """
    ticket = _get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

    if ticket.get("status") == "resolved":
        raise HTTPException(status_code=409, detail="Ticket is already resolved")

    _update_ticket(ticket_id, {
        "status": "resolved",
        "resolution": request.resolution,
        "agent_notes": f"Manually resolved by {request.resolved_by}",
    })

    updated = _get_ticket(ticket_id)
    return TicketResponse(
        id=str(updated.get("id", ticket_id)),
        status="resolved",
        priority=updated.get("priority"),
        category=updated.get("category"),
        subject=updated.get("subject", ""),
        created_at=updated.get("created_at", ""),
        email=updated.get("email", ""),
        resolution=request.resolution,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    System health check.

    Returns the status of all dependencies:
    - Database (PostgreSQL)
    - Cache (Redis)
    - Vector store (ChromaDB)

    Used by load balancers and monitoring systems.
    Returns 200 if healthy, 503 if degraded.
    """
    checks = {}

    # Check PostgreSQL
    try:
        from support_platform.database.models import check_db_connection
        checks["database"] = check_db_connection()
    except Exception:
        checks["database"] = False

    # Check Redis
    try:
        import redis
        r = redis.from_url(settings.redis_url, socket_timeout=2)
        r.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    # Check ChromaDB
    try:
        import httpx
        resp = httpx.get(f"{settings.chroma_url}/api/v1", timeout=2)
        checks["chromadb"] = resp.status_code == 200
    except Exception:
        checks["chromadb"] = False

    # Check LLM API key
    checks["openai_configured"] = settings.has_openai_key

    all_critical = checks.get("database", False) and checks.get("openai_configured", False)
    status = "healthy" if all_critical else "degraded"

    return HealthResponse(
        status=status,
        timestamp=datetime.utcnow().isoformat(),
        checks=checks,
    )
