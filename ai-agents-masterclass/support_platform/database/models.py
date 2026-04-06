"""
models.py - SQLAlchemy Database Models
=======================================
Defines the ORM models that map to the database tables created in init_db.sql.

Models:
- Customer: Platform users
- Ticket: Support tickets
- KnowledgeBaseArticle: KB articles (also indexed in ChromaDB)
- AgentInteraction: Audit log of LLM calls

Usage:
    from support_platform.database.models import Ticket, Customer, get_session

    with get_session() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).first()
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.sql import func

from support_platform.config import settings


# ──────────────────────────────────────────────────────────────
# Database setup
# ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def create_db_engine(database_url: str = None):
    """
    Create the SQLAlchemy engine.

    Configured for connection pooling appropriate for a FastAPI application:
    - pool_pre_ping: Test connections before using them
    - pool_recycle: Recycle connections every 30 minutes
    """
    url = database_url or settings.database_url
    engine = create_engine(
        url,
        pool_pre_ping=True,      # Check connection health before use
        pool_recycle=1800,        # Recycle connections after 30 minutes
        pool_size=10,             # Maintain up to 10 connections
        max_overflow=20,          # Allow up to 20 additional connections
        echo=settings.is_development,  # Log SQL in development
    )
    return engine


# Lazy-initialized engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


def get_session() -> Session:
    """
    Get a database session.

    Usage with context manager (preferred):
        with get_session() as session:
            ticket = session.query(Ticket).first()

    Usage for FastAPI dependency injection:
        def get_db():
            db = get_session_factory()()
            try:
                yield db
            finally:
                db.close()
    """
    SessionLocal = get_session_factory()
    return SessionLocal()


# ──────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────

class Customer(Base):
    """
    A customer who uses the support platform.

    Matches the `customers` table in init_db.sql.
    """

    __tablename__ = "customers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    account_status = Column(
        String(50),
        nullable=False,
        default="active",
    )
    subscription_tier = Column(
        String(50),
        nullable=False,
        default="free",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    tickets = relationship("Ticket", back_populates="customer", lazy="dynamic")

    # ── Constraints ──────────────────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "account_status IN ('active', 'suspended', 'cancelled', 'trial')",
            name="ck_customers_account_status",
        ),
        CheckConstraint(
            "subscription_tier IN ('free', 'starter', 'pro', 'enterprise')",
            name="ck_customers_subscription_tier",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "account_status": self.account_status,
            "subscription_tier": self.subscription_tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Customer {self.email} ({self.subscription_tier})>"


class Ticket(Base):
    """
    A customer support ticket.

    Matches the `tickets` table in init_db.sql.
    Created when a customer submits a support request.
    Updated as the agent processes and resolves the ticket.
    """

    __tablename__ = "tickets"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Customer info (FK + denormalized for performance)
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name = Column(String(255))
    email = Column(String(255), nullable=False, index=True)

    # Ticket content
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)

    # Classification (set by triage agent)
    priority = Column(
        String(20),
        nullable=False,
        default="medium",
        index=True,
    )
    category = Column(String(50), index=True)

    # Lifecycle
    status = Column(
        String(30),
        nullable=False,
        default="open",
        index=True,
    )

    # Resolution
    resolution = Column(Text)
    agent_notes = Column(Text)

    # Relationships
    customer = relationship("Customer", back_populates="tickets")
    interactions = relationship(
        "AgentInteraction",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )

    # ── Constraints ──────────────────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_tickets_priority",
        ),
        CheckConstraint(
            "category IS NULL OR category IN ('account_access', 'billing', 'technical_bug', 'feature_request', 'general_inquiry')",
            name="ck_tickets_category",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'waiting_customer', 'escalated', 'resolved', 'closed')",
            name="ck_tickets_status",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "customer_name": self.customer_name,
            "email": self.email,
            "subject": self.subject,
            "body": self.body,
            "priority": self.priority,
            "category": self.category,
            "status": self.status,
            "resolution": self.resolution,
            "agent_notes": self.agent_notes,
        }

    def __repr__(self) -> str:
        return f"<Ticket {self.id} [{self.status}] {self.subject[:40]}>"


class KnowledgeBaseArticle(Base):
    """
    A knowledge base article.

    These articles are also embedded into ChromaDB for semantic search.
    The embedding_id field links to the ChromaDB document ID.

    Matches the `knowledge_base` table in init_db.sql.
    """

    __tablename__ = "knowledge_base"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(100), index=True)
    tags = Column(ARRAY(String))      # PostgreSQL array of tag strings
    embedding_id = Column(String(255))  # ChromaDB document ID
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "tags": self.tags or [],
            "embedding_id": self.embedding_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<KBArticle '{self.title[:40]}'>"


class AgentInteraction(Base):
    """
    Audit log of every LLM call made by the agent pipeline.

    Used for:
    - Cost tracking (sum cost_usd per day/month)
    - Performance monitoring (latency_ms distribution)
    - Debugging (what did the agent do for ticket X?)
    - Billing attribution (which tickets are expensive?)

    Matches the `agent_interactions` table in init_db.sql.
    """

    __tablename__ = "agent_interactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticket_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        index=True,
    )
    agent_type = Column(String(100), nullable=False, index=True)
    model = Column(String(100))
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    latency_ms = Column(Integer)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    ticket = relationship("Ticket", back_populates="interactions")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "ticket_id": str(self.ticket_id) if self.ticket_id else None,
            "agent_type": self.agent_type,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": float(self.cost_usd) if self.cost_usd else 0.0,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<AgentInteraction {self.agent_type} "
            f"${float(self.cost_usd):.6f} {self.latency_ms}ms>"
        )


# ──────────────────────────────────────────────────────────────
# Database utilities
# ──────────────────────────────────────────────────────────────

def create_all_tables() -> None:
    """Create all tables in the database (safe to call multiple times)."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def check_db_connection() -> bool:
    """Check if the database is reachable."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("Database Models:")
    for table_name, table in Base.metadata.tables.items():
        cols = [f"{c.name} ({c.type})" for c in table.columns]
        print(f"\n  {table_name}:")
        for col in cols:
            print(f"    - {col}")
