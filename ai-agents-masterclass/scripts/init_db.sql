-- init_db.sql
-- Database initialization for AI Customer Support Agent Platform
-- This file is mounted into PostgreSQL and runs automatically on first start.
-- Run manually: psql -U agents_user -d agents_db -f scripts/init_db.sql

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector for embedding storage (install separately if needed)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- customers
-- Master table of customers using the support platform.
-- ============================================================
CREATE TABLE IF NOT EXISTS customers (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    account_status VARCHAR(50) NOT NULL DEFAULT 'active'
                  CHECK (account_status IN ('active', 'suspended', 'cancelled', 'trial')),
    subscription_tier VARCHAR(50) NOT NULL DEFAULT 'free'
                  CHECK (subscription_tier IN ('free', 'starter', 'pro', 'enterprise')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(account_status);

-- ============================================================
-- tickets
-- Core support ticket table.
-- ============================================================
CREATE TABLE IF NOT EXISTS tickets (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Customer info (denormalized for quick access)
    customer_id   UUID REFERENCES customers(id) ON DELETE SET NULL,
    customer_name VARCHAR(255),
    email         VARCHAR(255) NOT NULL,

    -- Ticket content
    subject       VARCHAR(500) NOT NULL,
    body          TEXT NOT NULL,

    -- Classification (set by triage agent)
    priority      VARCHAR(20) NOT NULL DEFAULT 'medium'
                  CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    category      VARCHAR(50)
                  CHECK (category IN (
                      'account_access', 'billing', 'technical_bug',
                      'feature_request', 'general_inquiry'
                  )),

    -- Lifecycle
    status        VARCHAR(30) NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open', 'in_progress', 'waiting_customer',
                                    'escalated', 'resolved', 'closed')),

    -- Resolution
    resolution    TEXT,
    agent_notes   TEXT
);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets;
CREATE TRIGGER trg_tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_tickets_email     ON tickets(email);
CREATE INDEX IF NOT EXISTS idx_tickets_status    ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_priority  ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_tickets_category  ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_customer  ON tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created   ON tickets(created_at DESC);

-- ============================================================
-- knowledge_base
-- Articles used by the RAG system to answer tickets.
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_base (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title         VARCHAR(500) NOT NULL,
    content       TEXT NOT NULL,
    category      VARCHAR(100),
    tags          TEXT[],            -- e.g. ARRAY['password', 'login', 'auth']
    embedding_id  VARCHAR(255),      -- ChromaDB document ID for the vector
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_base(category);
CREATE INDEX IF NOT EXISTS idx_kb_tags     ON knowledge_base USING GIN(tags);

-- ============================================================
-- agent_interactions
-- Audit log of every LLM call made by the agent pipeline.
-- Used for cost tracking and debugging.
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_interactions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_id     UUID REFERENCES tickets(id) ON DELETE CASCADE,
    agent_type    VARCHAR(100) NOT NULL,   -- e.g. 'triage', 'resolution', 'quality'
    model         VARCHAR(100),            -- e.g. 'gpt-4o', 'claude-3-5-sonnet-20241022'
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(10, 6) NOT NULL DEFAULT 0,
    latency_ms    INTEGER,                 -- Wall-clock time for the LLM call
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interactions_ticket ON agent_interactions(ticket_id);
CREATE INDEX IF NOT EXISTS idx_interactions_agent  ON agent_interactions(agent_type);
CREATE INDEX IF NOT EXISTS idx_interactions_date   ON agent_interactions(created_at DESC);

-- ============================================================
-- Seed a few demo customers (useful for development)
-- ============================================================
INSERT INTO customers (name, email, account_status, subscription_tier) VALUES
    ('Alice Johnson',    'alice@example.com',   'active',    'pro'),
    ('Bob Smith',        'bob@example.com',     'active',    'starter'),
    ('Carol White',      'carol@example.com',   'suspended', 'free'),
    ('David Brown',      'david@enterprise.io', 'active',    'enterprise'),
    ('Eve Martinez',     'eve@example.com',     'trial',     'free')
ON CONFLICT (email) DO NOTHING;
