# Module 13: Case Studies — Real-World Agent Systems

## What This Module Covers

The best way to understand production agent systems is to study ones that already work at scale. This module dissects five real-world AI agent deployments and extracts the patterns you can apply to your own systems.

## Case Studies

### 1. GitHub Copilot — Code Completion at Scale

**Scale:** 1M+ developers, sub-100ms latency requirement
**Agent Level:** Level 2 (Tool Use) — no autonomous loop, but complex context management

**Architecture:**
```
Developer types code
       │
  [Context Builder]          Expensive: collects 10+ files of context
       │
  [Relevance Scorer]         Ranks code snippets by similarity
       │
  [LLM: Code Model]          Fine-tuned on code, temperature=0
       │
  [Completion Filter]        Removes harmful patterns, validates syntax
       │
  [Cache Layer]              Semantic cache for repeated patterns
```

**Key Design Decisions:**
- **Fine-tuning over prompting**: A smaller fine-tuned model beats a larger general model for code completion
- **Temperature=0**: Deterministic outputs — you don't want random variation in code suggestions
- **Semantic caching**: 30-40% cache hit rate eliminates repeated LLM calls
- **Context compression**: Not all of 10 open files is relevant — smart retrieval, not dump-everything

**What You'd Do Differently with Hindsight:**
> The initial version sent the entire file as context. Cache hit rate was near zero. Moving to compressed, relevant-snippet context cut cost by 60% with zero quality loss.

---

### 2. Intercom Fin — Customer Support Agent

**Scale:** Handles millions of support conversations/month
**Agent Level:** Level 3 (Multi-Step Autonomous Reasoning)

**Architecture:**
```
Customer message
       │
  [Intent Classifier]        Is this a new issue or follow-up?
       │
  [Context Retriever]        Customer history + relevant KB articles
       │
  [Resolution Agent]         Main reasoning agent (Claude 3 Sonnet)
       │  ← Tool: search_kb()
       │  ← Tool: get_account_info()
       │  ← Tool: check_subscription()
       │
  [Response Validator]       Is the answer grounded in KB? Is it safe?
       │
  [Confidence Check]         < 0.8 → escalate to human
```

**Key Design Decisions:**
- **Model selection**: Sonnet over Opus — 3x cheaper, 95% of the quality for support tasks
- **Strict grounding**: Agent can ONLY cite KB articles, not hallucinate solutions
- **Hard confidence threshold**: 80% confidence or escalate. No gray zone.
- **Human-in-loop**: Every agent decision is logged; humans review edge cases and retrain

**Metrics They Track:**
- Deflection rate: % tickets resolved without human
- CSAT: Customer satisfaction after agent interaction
- Hallucination rate: Agent cited non-existent KB article
- False escalation rate: Agent escalated when it could have resolved

---

### 3. Cursor — AI-Powered Code Editor

**Scale:** 100K+ active developers, complex multi-file reasoning
**Agent Level:** Level 3-4 (Multi-Step + some Multi-Agent)

**Architecture:**
```
User request: "Refactor auth to use JWT"
       │
  [Codebase Indexer]         AST parsing, symbol graph, embeddings
       │
  [Planning Agent]           Break task into steps
       │
  [Code Reading Agent]       Read relevant files
       │
  [Code Writing Agent]       Generate changes file by file
       │
  [Diff Validator]           Does the code compile? Any broken imports?
       │
  [Human Review]             Show diff to user before applying
```

**Key Design Decisions:**
- **Human always in the loop**: Every change shown as diff, user approves
- **Incremental changes**: One file at a time, not whole-codebase rewrites
- **Compiler validation**: After each change, run the compiler — fast feedback loop
- **Context is king**: AST-aware context retrieval beats naive file dumping

**The Biggest Challenge:**
> Hallucinated function calls. The agent would generate code that called functions that don't exist. Solution: After generation, run a symbol checker against the codebase's actual symbol table.

---

### 4. Harvey — AI Legal Assistant

**Scale:** Top law firms, $50M+ Series B
**Agent Level:** Level 3 (with extreme safety constraints)

**Architecture:**
```
Attorney query: "Draft NDA for SaaS acquisition"
       │
  [Jurisdictional Router]    Which legal system? Which practice area?
       │
  [Precedent Retriever]      Search 50M+ case documents
       │
  [Draft Generator]          GPT-4o with legal fine-tuning
       │
  [Citation Verifier]        Every claim linked to a real document
       │
  [Risk Flagging]            "This clause may not be enforceable in CA"
       │
  [Attorney Review]          ALWAYS required — no autonomous filing
```

**Key Design Decisions:**
- **Never autonomous**: Every output reviewed by a licensed attorney. Legal liability is too high.
- **Citation-first**: Hallucination in legal context is career-ending. Every statement must cite sources.
- **Domain fine-tuning**: Generic models hallucinate legal citations. Fine-tuned models are grounded.
- **Jurisdiction awareness**: A contract clause valid in Delaware may be void in California.

**Why This Matters:**
This is the canonical example of where NOT to fully automate. The agent handles research and drafting. Humans handle judgment and accountability.

---

### 5. Perplexity — AI Search Engine

**Scale:** 10M+ queries/day, sub-3 second total latency
**Agent Level:** Level 3 (Multi-Step Research)

**Architecture:**
```
User query
       │
  [Query Rewriter]           LLM rewrites for better search
       │
  [Parallel Web Search]      3-5 searches simultaneously (asyncio)
       │
  [Content Fetcher]          Parallel page fetches
       │
  [Relevance Ranker]         Score content by query relevance
       │
  [Context Compressor]       Fit 10 pages into 8K context window
       │
  [Answer Synthesizer]       Generate answer with inline citations
       │
  [Follow-up Generator]      Suggest related questions
```

**Key Design Decisions:**
- **Parallelism everywhere**: 5 searches in parallel, 10 page fetches in parallel
- **Context compression**: Extract key sentences, not entire pages
- **Speed vs quality tradeoff**: 3-second budget — no time for iterative refinement
- **Citations as guardrails**: Model must cite sources; hallucinations get caught during citation check

**Latency Budget (3 seconds total):**
```
Query rewrite:         ~200ms
Parallel search:       ~800ms  (3 searches, fastest wins)
Content fetching:      ~600ms  (parallel, top 5 results)
Relevance ranking:     ~200ms
Context compression:   ~300ms
Answer generation:     ~700ms  (streaming starts immediately)
                     ─────────
Total:                ~2.8s
```

---

## Patterns That Appear Everywhere

After studying 50+ production agent systems, these patterns show up constantly:

### 1. Always Have a Cheap Fast Path
Start with a cheap classifier (GPT-4o-mini, even regex). Only escalate to expensive models when needed.

### 2. Ground Every Output
If an agent says X, it should cite where X came from. Hallucinations hurt trust more than slowness.

### 3. Human Review Threshold
Pick a confidence score. Below it: human reviews. Above it: ship. Start conservative (90%), loosen as you gain confidence.

### 4. Parallel Tool Calls
Most agents can call 2-5 tools in parallel. asyncio makes this easy. 3x throughput at 0 extra cost.

### 5. Semantic Caching
If users ask similar questions, cache the answer. 20-40% of queries are "warm" in most support systems.

### 6. Separate Fast and Slow Paths
Real-time user interaction → fast path (cheap model, cached, streaming)
Background processing → slow path (thorough model, no streaming, batch)

---

## Exercises

1. **Map a product you use**: Pick any AI feature in a product you use. Draw the agent architecture. What pattern does it use?

2. **Identify the failure modes**: For each case study, what are the top 3 ways the system could fail? How would you detect it?

3. **Cost modeling**: If you were running Intercom Fin's architecture at 1M tickets/month, estimate the monthly LLM cost.

4. **Build a mini-version**: Take the Perplexity search architecture and build a simplified version that searches Wikipedia.

---

## What's Next

Module 14 is the capstone — you integrate everything you've learned into the complete, production-ready AI Customer Support Agent Platform.
