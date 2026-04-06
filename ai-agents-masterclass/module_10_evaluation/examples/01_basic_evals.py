"""
01_basic_evals.py - Basic Agent Evaluation Framework
=====================================================
Module 10: Testing & Evaluation

Evaluating AI agents requires different strategies than traditional software:
- Outputs are probabilistic, not deterministic
- "Correct" is often fuzzy or context-dependent
- You need both automated and human evaluation

This file demonstrates:
1. Test dataset creation with expected outputs
2. Exact match and fuzzy match evaluators
3. Keyword/topic presence checks
4. Running an evaluation suite and reporting results
5. Regression testing to catch quality degradation

Run with: python module_10_evaluation/examples/01_basic_evals.py
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Test Dataset
# ──────────────────────────────────────────────────────────────

@dataclass
class EvalCase:
    """A single evaluation test case."""
    case_id: str
    description: str

    # Input
    subject: str
    body: str
    customer_email: str

    # Expected outputs (what a good agent should produce)
    expected_category: str
    expected_keywords: list[str]          # Response must contain these
    expected_not_keywords: list[str]      # Response must NOT contain these
    should_escalate: bool
    min_response_length: int = 50


# The evaluation dataset — these are our "golden" examples
EVAL_DATASET: list[EvalCase] = [
    EvalCase(
        case_id="EVAL-001",
        description="Password reset request",
        subject="Can't log in",
        body="I forgot my password and the reset email isn't coming through.",
        customer_email="alice@example.com",
        expected_category="account_access",
        expected_keywords=["password", "reset", "email"],
        expected_not_keywords=["billing", "refund"],
        should_escalate=False,
    ),
    EvalCase(
        case_id="EVAL-002",
        description="Duplicate billing charge",
        subject="Charged twice this month",
        body="I see two charges of $79 on January 15th and 16th. Please help.",
        customer_email="bob@example.com",
        expected_category="billing",
        expected_keywords=["billing", "charge"],
        expected_not_keywords=["password"],
        should_escalate=True,
    ),
    EvalCase(
        case_id="EVAL-003",
        description="Technical bug report",
        subject="Export keeps failing",
        body="When I try to export my data as CSV, I get a 500 error. This has happened 3 times.",
        customer_email="charlie@example.com",
        expected_category="technical_bug",
        expected_keywords=["error", "export"],
        expected_not_keywords=["password", "billing"],
        should_escalate=True,
    ),
    EvalCase(
        case_id="EVAL-004",
        description="Feature request",
        subject="Can you add dark mode?",
        body="I would love to have a dark mode option for the dashboard. Many users would benefit.",
        customer_email="diana@example.com",
        expected_category="feature_request",
        expected_keywords=["feature", "request"],
        expected_not_keywords=["password", "billing"],
        should_escalate=False,
    ),
    EvalCase(
        case_id="EVAL-005",
        description="2FA lockout",
        subject="Locked out of account",
        body="My phone broke and I can't get the 2FA codes anymore. I have my backup codes somewhere.",
        customer_email="eve@example.com",
        expected_category="account_access",
        expected_keywords=["2fa", "backup", "access"],
        expected_not_keywords=["billing"],
        should_escalate=False,
    ),
]


# ──────────────────────────────────────────────────────────────
# Evaluators
# ──────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    """Result of a single evaluator check."""
    evaluator: str
    passed: bool
    score: float  # 0.0 to 1.0
    details: str


@dataclass
class CaseResult:
    """Aggregated result for one test case."""
    case_id: str
    description: str
    agent_output: dict
    eval_results: list[EvalResult] = field(default_factory=list)
    latency_ms: int = 0

    @property
    def overall_score(self) -> float:
        if not self.eval_results:
            return 0.0
        return sum(r.score for r in self.eval_results) / len(self.eval_results)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.eval_results)


def eval_category(expected: str, actual: str) -> EvalResult:
    """Check if the agent classified the ticket correctly."""
    passed = expected == actual
    return EvalResult(
        evaluator="category_match",
        passed=passed,
        score=1.0 if passed else 0.0,
        details=f"Expected '{expected}', got '{actual}'",
    )


def eval_keywords_present(response: str, keywords: list[str]) -> EvalResult:
    """Check that required keywords appear in the response."""
    response_lower = response.lower()
    missing = [k for k in keywords if k.lower() not in response_lower]
    found = len(keywords) - len(missing)

    score = found / len(keywords) if keywords else 1.0
    passed = len(missing) == 0

    details = (
        f"All {len(keywords)} keywords found"
        if passed
        else f"Missing: {missing}"
    )
    return EvalResult(
        evaluator="keywords_present",
        passed=passed,
        score=score,
        details=details,
    )


def eval_keywords_absent(response: str, forbidden: list[str]) -> EvalResult:
    """Check that forbidden keywords do NOT appear in the response."""
    response_lower = response.lower()
    found = [k for k in forbidden if k.lower() in response_lower]

    passed = len(found) == 0
    score = 1.0 if passed else 0.0

    details = (
        "No forbidden keywords found"
        if passed
        else f"Forbidden keywords present: {found}"
    )
    return EvalResult(
        evaluator="keywords_absent",
        passed=passed,
        score=score,
        details=details,
    )


def eval_escalation(expected: bool, actual: bool) -> EvalResult:
    """Check if escalation decision matches expected."""
    passed = expected == actual
    return EvalResult(
        evaluator="escalation_correct",
        passed=passed,
        score=1.0 if passed else 0.0,
        details=f"Expected escalate={expected}, got escalate={actual}",
    )


def eval_response_length(response: str, min_length: int) -> EvalResult:
    """Check that the response meets minimum length requirements."""
    word_count = len(response.split())
    passed = word_count >= min_length

    return EvalResult(
        evaluator="response_length",
        passed=passed,
        score=min(1.0, word_count / min_length),
        details=f"{word_count} words (minimum: {min_length})",
    )


def eval_has_greeting(response: str) -> EvalResult:
    """Check that the response starts with a professional greeting."""
    has_greeting = any(response.startswith(g) for g in ["Hi", "Hello", "Dear", "Thank"])
    return EvalResult(
        evaluator="has_greeting",
        passed=has_greeting,
        score=1.0 if has_greeting else 0.0,
        details="Has greeting" if has_greeting else "Missing professional greeting",
    )


# ──────────────────────────────────────────────────────────────
# Agent Under Test (the system being evaluated)
# ──────────────────────────────────────────────────────────────

def run_agent(case: EvalCase) -> dict:
    """
    Run the agent on a test case.

    In real evaluation, this calls your actual agent.
    Here we use a mock that demonstrates the evaluation patterns.
    """
    text = f"{case.subject} {case.body}".lower()

    # Category detection
    if any(w in text for w in ["password", "login", "access", "2fa", "locked"]):
        category = "account_access"
        should_escalate = False
        response = (
            f"Hi there,\n\n"
            f"I can help with your account access issue. Please try the password reset "
            f"option at the login page. If you need to recover 2FA access, use your "
            f"backup codes or contact support@example.com."
        )
    elif any(w in text for w in ["charge", "billing", "invoice", "payment", "refund"]):
        category = "billing"
        should_escalate = True
        response = (
            f"Hi there,\n\n"
            f"I understand you have a billing concern about a charge on your account. "
            f"Our billing team will review this and respond within 1 business day."
        )
    elif any(w in text for w in ["error", "bug", "crash", "export", "failing", "broken"]):
        category = "technical_bug"
        should_escalate = True
        response = (
            f"Hi there,\n\n"
            f"I'm sorry you're experiencing this technical error. Please share the "
            f"exact error message and your browser version so our team can investigate."
        )
    elif "feature" in text or "request" in text or "dark mode" in text:
        category = "feature_request"
        should_escalate = False
        response = (
            f"Hi there,\n\n"
            f"Thank you for submitting your feature request. We've logged it in our "
            f"product roadmap and our team will consider it for future releases."
        )
    else:
        category = "general_inquiry"
        should_escalate = False
        response = (
            f"Hi there,\n\n"
            f"Thank you for reaching out. Our support team will review your request "
            f"and respond within 24 hours."
        )

    return {
        "category": category,
        "should_escalate": should_escalate,
        "response": response,
    }


# ──────────────────────────────────────────────────────────────
# Evaluation Runner
# ──────────────────────────────────────────────────────────────

def evaluate_case(case: EvalCase) -> CaseResult:
    """Run all evaluators on a single test case."""
    start = time.time()
    output = run_agent(case)
    latency = int((time.time() - start) * 1000)

    result = CaseResult(
        case_id=case.case_id,
        description=case.description,
        agent_output=output,
        latency_ms=latency,
    )

    # Run all evaluators
    result.eval_results.extend([
        eval_category(case.expected_category, output.get("category", "")),
        eval_keywords_present(output.get("response", ""), case.expected_keywords),
        eval_keywords_absent(output.get("response", ""), case.expected_not_keywords),
        eval_escalation(case.should_escalate, output.get("should_escalate", False)),
        eval_response_length(output.get("response", ""), case.min_response_length),
        eval_has_greeting(output.get("response", "")),
    ])

    return result


def run_evaluation_suite(dataset: list[EvalCase]) -> list[CaseResult]:
    """Run the full evaluation suite."""
    return [evaluate_case(case) for case in dataset]


def print_report(results: list[CaseResult]):
    """Print a structured evaluation report."""
    print("\n  Evaluation Report")
    print("  " + "─" * 58)

    total_cases = len(results)
    passed_cases = sum(1 for r in results if r.passed)
    avg_score = sum(r.overall_score for r in results) / total_cases if total_cases > 0 else 0

    for result in results:
        icon = "PASS" if result.passed else "FAIL"
        print(f"\n  [{icon}] {result.case_id}: {result.description}")
        print(f"         Score: {result.overall_score:.0%} | Latency: {result.latency_ms}ms")

        for eval_result in result.eval_results:
            status = "✓" if eval_result.passed else "✗"
            print(f"         {status} {eval_result.evaluator}: {eval_result.details}")

    print("\n  " + "─" * 58)
    print(f"  Summary: {passed_cases}/{total_cases} cases passed")
    print(f"  Average score: {avg_score:.0%}")
    print(f"  Pass rate: {passed_cases/total_cases:.0%}")

    # Identify weak spots
    evaluator_scores: dict[str, list[float]] = {}
    for result in results:
        for er in result.eval_results:
            evaluator_scores.setdefault(er.evaluator, []).append(er.score)

    print("\n  Scores by evaluator:")
    for ev_name, scores in sorted(evaluator_scores.items()):
        avg = sum(scores) / len(scores)
        bar = "█" * int(avg * 10) + "░" * (10 - int(avg * 10))
        print(f"    {ev_name:<25} {bar} {avg:.0%}")


def main():
    print("\n" + "=" * 60)
    print("  Basic Agent Evaluation Suite")
    print("=" * 60)
    print(f"  Running {len(EVAL_DATASET)} test cases...\n")

    results = run_evaluation_suite(EVAL_DATASET)
    print_report(results)

    print("\n  Evaluation best practices:")
    print("    - Keep eval dataset separate from training data")
    print("    - Add new cases whenever a bug is discovered (regression)")
    print("    - Track scores over time to catch quality drift")
    print("    - Use LLM-as-judge for semantic quality (see 02_llm_judge.py)")
    print("    - Aim for automated evals that run on every commit")


if __name__ == "__main__":
    main()
