# Module 10: Evaluation & Testing

## What This Module Covers

"My agent seems to work" is not good enough for production. This module teaches you how to systematically evaluate agent quality using deterministic evals, LLM-as-judge, and benchmark suites.

## What You'll Build

| File | What It Teaches |
|------|-----------------|
| `01_basic_evals.py` | Test cases, scoring, deterministic evaluation |
| `02_llm_judge.py` | Use GPT-4o to evaluate response quality |
| `03_benchmark_suite.py` | Full benchmark: 20 test tickets, automated scoring |

## Key Concepts

### The Evaluation Pyramid

```
           ┌────────────────────────┐
           │    E2E System Tests    │  (expensive, slow, realistic)
           ├────────────────────────┤
           │   LLM-as-Judge Evals   │  (flexible, subjective)
           ├────────────────────────┤
           │   Deterministic Evals  │  (fast, objective, brittle)
           └────────────────────────┘
```

Use all three layers:
1. **Deterministic** for objective metrics (triage accuracy, response format)
2. **LLM-judge** for subjective quality (tone, helpfulness, safety)
3. **E2E tests** for catching regressions before deployment

### Deterministic Evaluation

Define test cases as (input, expected_output) pairs:

```python
test_cases = [
    EvalCase(
        ticket="I can't log into my account",
        expected_category="account_access",
        expected_priority="high",
    ),
    EvalCase(
        ticket="How do I upgrade my plan?",
        expected_category="billing",
        expected_priority="low",
    ),
]

# Run and score
for case in test_cases:
    result = triage_agent.run(case.ticket)
    scores["category"] += (result.category == case.expected_category)
    scores["priority"] += (result.priority == case.expected_priority)

accuracy = scores["category"] / len(test_cases)
```

Simple, fast, and reproducible. Run this in CI/CD.

### LLM-as-Judge

Use a separate, stronger LLM to evaluate agent responses:

```python
JUDGE_PROMPT = """
You are evaluating a customer support agent response.

Ticket: {ticket}
Agent Response: {response}

Rate on these criteria (0-10 each):
1. Accuracy: Is the information factually correct?
2. Helpfulness: Does it actually solve the customer's problem?
3. Tone: Is it professional, empathetic, and appropriate?
4. Completeness: Does it address all aspects of the ticket?
5. Safety: Does it avoid any harmful content or PII exposure?

Respond with JSON: {"accuracy": X, "helpfulness": X, "tone": X, "completeness": X, "safety": X, "reasoning": "..."}
"""
```

**Use a different model than the one being evaluated** — using GPT-4o to judge GPT-4o responses creates a bias. Use Claude to judge GPT-4o, or vice versa.

### Benchmark Suite

The support platform benchmark:
- 20 carefully crafted test tickets across all categories
- Each with ground-truth labels (category, priority, resolution approach)
- Automated scoring pipeline
- HTML report generation

```
Benchmark Results (2024-01-15 14:30:00)
========================================
Model: gpt-4o
Total tickets: 20

Triage Accuracy
  Category:     18/20 (90.0%)
  Priority:     16/20 (80.0%)
  Auto-resolve: 14/20 (70.0%)

Quality Scores (LLM judge, scale 0-10)
  Accuracy:     8.4
  Helpfulness:  8.1
  Tone:         9.2
  Completeness: 7.8
  Safety:       9.8

Performance
  Avg latency:  3.2s
  Total cost:   $0.87

Overall Score: 85/100
```

### Regression Testing

Run benchmarks on every model/prompt change and track over time:

```python
# Store benchmark results in a database
# Alert if any metric drops more than 5% from baseline
if results.category_accuracy < baseline.category_accuracy - 0.05:
    alert("Category accuracy regression detected!")
```

### Eval-Driven Development

The recommended workflow for improving agents:
1. Run benchmark → find failure cases
2. Analyze failure patterns
3. Improve prompt or tools
4. Run benchmark again
5. Confirm improvement, no regressions
6. Commit changes

## How to Run the Examples

```bash
# Requires OPENAI_API_KEY and ANTHROPIC_API_KEY (for judge)
python module_10_evaluation/examples/01_basic_evals.py
python module_10_evaluation/examples/02_llm_judge.py
python module_10_evaluation/examples/03_benchmark_suite.py
```

## What's Next

Module 11 covers safety and guardrails — input validation, PII detection, injection prevention, and output filtering. Critical before going to production.
