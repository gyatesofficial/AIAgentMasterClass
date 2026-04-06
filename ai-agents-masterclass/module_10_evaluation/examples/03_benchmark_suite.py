"""
03_benchmark_suite.py - Complete Benchmark Suite
================================================
Module 10: Testing & Evaluation

A complete benchmarking system that tracks agent performance over time:
1. Run a comprehensive test suite
2. Compare current results against a baseline
3. Detect regressions (when scores drop)
4. Generate a summary report
5. Save results for trend analysis

This is the evaluation infrastructure you'd run on every PR
to ensure agent quality never regresses.

Run with: python module_10_evaluation/examples/03_benchmark_suite.py
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────
# Benchmark Dimensions
# ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkCase:
    """A single benchmark test case with expected outcomes."""
    case_id: str
    category: str           # Groups cases (e.g., "billing", "technical")
    difficulty: str         # "easy", "medium", "hard"
    subject: str
    body: str
    email: str
    expected_category: str
    expected_keywords: list[str]
    should_escalate: bool


@dataclass
class CaseBenchmarkResult:
    """Result for a single benchmark case."""
    case_id: str
    category: str
    difficulty: str
    category_correct: bool
    keywords_found: float       # 0.0 to 1.0
    escalation_correct: bool
    has_greeting: bool
    response_length: int
    latency_ms: int

    @property
    def score(self) -> float:
        """Weighted score for this case."""
        return (
            self.category_correct * 0.30 +
            self.keywords_found * 0.25 +
            self.escalation_correct * 0.20 +
            self.has_greeting * 0.15 +
            min(1.0, self.response_length / 50) * 0.10
        )


@dataclass
class BenchmarkRun:
    """Complete results for one benchmark run."""
    run_id: str
    timestamp: str
    agent_version: str
    cases: list[CaseBenchmarkResult] = field(default_factory=list)
    total_latency_ms: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def overall_score(self) -> float:
        if not self.cases:
            return 0.0
        return sum(c.score for c in self.cases) / len(self.cases)

    @property
    def category_accuracy(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.category_correct) / len(self.cases)

    @property
    def escalation_accuracy(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.escalation_correct) / len(self.cases)

    @property
    def avg_latency_ms(self) -> float:
        if not self.cases:
            return 0.0
        return sum(c.latency_ms for c in self.cases) / len(self.cases)

    def by_difficulty(self) -> dict[str, float]:
        """Average score grouped by difficulty level."""
        groups: dict[str, list[float]] = {}
        for case in self.cases:
            groups.setdefault(case.difficulty, []).append(case.score)
        return {d: sum(s) / len(s) for d, s in groups.items()}

    def by_category(self) -> dict[str, float]:
        """Average score grouped by ticket category."""
        groups: dict[str, list[float]] = {}
        for case in self.cases:
            groups.setdefault(case.category, []).append(case.score)
        return {c: sum(s) / len(s) for c, s in groups.items()}


# ──────────────────────────────────────────────────────────────
# Benchmark Dataset
# ──────────────────────────────────────────────────────────────

BENCHMARK_CASES: list[BenchmarkCase] = [
    # EASY: Clear, single-topic tickets
    BenchmarkCase("B-001", "account", "easy", "Forgot my password", "Can't log in, forgot password", "a@ex.com", "account_access", ["password", "reset"], False),
    BenchmarkCase("B-002", "billing", "easy", "I was charged twice", "Double charge on my card", "b@ex.com", "billing", ["billing", "charge"], True),
    BenchmarkCase("B-003", "technical", "easy", "App keeps crashing", "Dashboard crashes every time", "c@ex.com", "technical_bug", ["error", "crash"], True),
    BenchmarkCase("B-004", "feature", "easy", "Feature request", "Please add dark mode", "d@ex.com", "feature_request", ["feature", "request"], False),

    # MEDIUM: Ambiguous or multi-topic tickets
    BenchmarkCase("B-005", "account", "medium", "2FA issues", "Phone broke, can't get 2FA codes, have backup codes", "e@ex.com", "account_access", ["2fa", "backup", "access"], False),
    BenchmarkCase("B-006", "billing", "medium", "Subscription problem", "I upgraded but still seeing Free plan features", "f@ex.com", "billing", ["billing", "plan"], True),
    BenchmarkCase("B-007", "technical", "medium", "API returning 429", "Getting rate limit errors on the export API", "g@ex.com", "technical_bug", ["api", "error"], True),
    BenchmarkCase("B-008", "account", "medium", "Account locked out", "Too many failed logins, account locked", "h@ex.com", "account_access", ["account", "locked", "access"], False),

    # HARD: Complex, multi-issue tickets requiring nuance
    BenchmarkCase("B-009", "billing", "hard", "Billing AND technical issue", "I was charged but the feature doesn't work. Both issues need fixing.", "i@ex.com", "billing", ["billing", "charge"], True),
    BenchmarkCase("B-010", "account", "hard", "Angry customer edge case", "This is unacceptable! I've been locked out for 3 days and nobody helped me!", "j@ex.com", "account_access", ["account", "access"], False),
]


# ──────────────────────────────────────────────────────────────
# Agent Under Test
# ──────────────────────────────────────────────────────────────

def classify_ticket(subject: str, body: str) -> tuple[str, bool]:
    """Simple rule-based agent (replace with your actual agent)."""
    text = f"{subject} {body}".lower()

    if any(w in text for w in ["password", "login", "access", "locked", "2fa", "account"]):
        return "account_access", False
    elif any(w in text for w in ["charge", "billing", "invoice", "payment", "subscription"]):
        return "billing", True
    elif any(w in text for w in ["error", "bug", "crash", "api", "export", "rate limit"]):
        return "technical_bug", True
    elif any(w in text for w in ["feature", "dark mode", "request"]):
        return "feature_request", False
    else:
        return "general_inquiry", False


def generate_response(subject: str, body: str, email: str, category: str) -> str:
    """Generate a response for the classified category."""
    name = email.split("@")[0].replace(".", " ").title()
    text = f"{subject} {body}".lower()

    if category == "account_access":
        if "2fa" in text or "authenticator" in text:
            return (
                f"Hi {name},\n\nFor 2FA access issues, use your backup codes to log in. "
                f"If you don't have them, contact support@example.com with ID verification."
            )
        elif "locked" in text:
            return (
                f"Hi {name},\n\nAccounts auto-unlock after 30 minutes. "
                f"If still locked, try the password reset option or contact support."
            )
        else:
            return (
                f"Hi {name},\n\nPlease reset your password via the login page > Forgot Password. "
                f"The reset link is valid for 24 hours."
            )
    elif category == "billing":
        return (
            f"Hi {name},\n\nOur billing team will review your account within 1 business day. "
            f"For duplicate charge billing issues, refunds are processed within 48 hours. "
            f"Contact billing@example.com for urgent billing matters."
        )
    elif category == "technical_bug":
        return (
            f"Hi {name},\n\nPlease share the exact error message and your browser version. "
            f"For API errors, include your request ID. Our technical team will investigate."
        )
    else:
        return (
            f"Hi {name},\n\nThank you for your message. "
            f"Our team will review and respond within 24 hours."
        )


def run_agent_on_case(case: BenchmarkCase) -> CaseBenchmarkResult:
    """Run the agent on one benchmark case and score it."""
    start = time.time()

    category, should_escalate = classify_ticket(case.subject, case.body)
    response = generate_response(case.subject, case.body, case.email, category)

    latency = int((time.time() - start) * 1000)

    # Score the result
    response_lower = response.lower()
    keywords_found = sum(
        1 for k in case.expected_keywords if k.lower() in response_lower
    ) / len(case.expected_keywords) if case.expected_keywords else 1.0

    return CaseBenchmarkResult(
        case_id=case.case_id,
        category=case.category,
        difficulty=case.difficulty,
        category_correct=(category == case.expected_category),
        keywords_found=keywords_found,
        escalation_correct=(should_escalate == case.should_escalate),
        has_greeting=any(response.startswith(g) for g in ["Hi", "Hello", "Dear"]),
        response_length=len(response.split()),
        latency_ms=latency,
    )


# ──────────────────────────────────────────────────────────────
# Benchmark Runner
# ──────────────────────────────────────────────────────────────

def run_benchmark(agent_version: str = "1.0.0") -> BenchmarkRun:
    """Run the full benchmark suite."""
    run = BenchmarkRun(
        run_id=f"bench_{int(time.time())}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent_version=agent_version,
        metadata={"case_count": len(BENCHMARK_CASES)},
    )

    start = time.time()
    for case in BENCHMARK_CASES:
        result = run_agent_on_case(case)
        run.cases.append(result)

    run.total_latency_ms = int((time.time() - start) * 1000)
    return run


def save_run(run: BenchmarkRun, output_dir: str = "data/benchmarks"):
    """Save benchmark results to disk."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filepath = os.path.join(output_dir, f"{run.run_id}.json")

    data = {
        "run_id": run.run_id,
        "timestamp": run.timestamp,
        "agent_version": run.agent_version,
        "overall_score": run.overall_score,
        "category_accuracy": run.category_accuracy,
        "escalation_accuracy": run.escalation_accuracy,
        "avg_latency_ms": run.avg_latency_ms,
        "cases": [asdict(c) for c in run.cases],
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


def detect_regression(current: BenchmarkRun, baseline: BenchmarkRun, threshold: float = 0.05) -> list[str]:
    """
    Compare current run to baseline and report regressions.

    A regression is when a metric drops by more than 'threshold'.
    Returns a list of regression descriptions (empty = no regressions).
    """
    regressions = []

    metrics = [
        ("overall_score", current.overall_score, baseline.overall_score),
        ("category_accuracy", current.category_accuracy, baseline.category_accuracy),
        ("escalation_accuracy", current.escalation_accuracy, baseline.escalation_accuracy),
    ]

    for name, curr_val, base_val in metrics:
        drop = base_val - curr_val
        if drop > threshold:
            pct = drop * 100
            regressions.append(
                f"{name}: {base_val:.0%} → {curr_val:.0%} (dropped {pct:.1f}pp)"
            )

    return regressions


# ──────────────────────────────────────────────────────────────
# Report Generation
# ──────────────────────────────────────────────────────────────

def print_benchmark_report(run: BenchmarkRun, baseline: Optional[BenchmarkRun] = None):
    """Print a comprehensive benchmark report."""
    print(f"\n  Benchmark Run: {run.run_id}")
    print(f"  Agent version: {run.agent_version}")
    print(f"  Cases: {len(run.cases)}")
    print()

    def delta(current: float, base: Optional[float]) -> str:
        if base is None:
            return ""
        d = current - base
        if abs(d) < 0.005:
            return " (→)"
        sign = "+" if d > 0 else ""
        return f" ({sign}{d*100:.1f}pp)"

    base_overall = baseline.overall_score if baseline else None
    base_cat = baseline.category_accuracy if baseline else None
    base_esc = baseline.escalation_accuracy if baseline else None

    print(f"  Overall Score:       {run.overall_score:.0%}{delta(run.overall_score, base_overall)}")
    print(f"  Category Accuracy:   {run.category_accuracy:.0%}{delta(run.category_accuracy, base_cat)}")
    print(f"  Escalation Accuracy: {run.escalation_accuracy:.0%}{delta(run.escalation_accuracy, base_esc)}")
    print(f"  Avg Latency:         {run.avg_latency_ms:.0f}ms")

    print("\n  Scores by Difficulty:")
    for diff, score in sorted(run.by_difficulty().items()):
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"    {diff:<8} {bar} {score:.0%}")

    print("\n  Scores by Category:")
    for cat, score in sorted(run.by_category().items()):
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"    {cat:<15} {bar} {score:.0%}")

    print("\n  Case Details:")
    print(f"  {'ID':<8} {'Diff':<8} {'Cat':<12} {'Score':<8} {'Latency'}")
    print("  " + "─" * 55)
    for case in run.cases:
        status = "PASS" if case.score >= 0.7 else "FAIL"
        print(f"  {case.case_id:<8} {case.difficulty:<8} {case.category:<12} {case.score:.0%}  [{status}]  {case.latency_ms}ms")

    if baseline:
        regressions = detect_regression(run, baseline)
        print()
        if regressions:
            print("  REGRESSIONS DETECTED:")
            for r in regressions:
                print(f"    - {r}")
        else:
            print("  No regressions detected vs baseline.")


def main():
    print("\n" + "=" * 60)
    print("  Agent Benchmark Suite")
    print("=" * 60)

    # Run current benchmark
    print(f"\n  Running benchmark on {len(BENCHMARK_CASES)} cases...")
    current = run_benchmark(agent_version="1.0.0")

    # Simulate a baseline (slightly better scores, for regression demo)
    baseline = run_benchmark(agent_version="0.9.0")
    # Artificially degrade baseline to show comparison
    for case in baseline.cases:
        case.category_correct = True  # Baseline had perfect category accuracy

    print_benchmark_report(current, baseline=baseline)

    # Save results
    try:
        filepath = save_run(current)
        print(f"\n  Results saved to: {filepath}")
    except Exception as e:
        print(f"\n  (Could not save results: {e})")

    print("\n  Integration with CI/CD:")
    print("    Add to your GitHub Actions workflow:")
    print("      - run: python -m pytest module_10_evaluation/ --benchmark")
    print("    Fail the build if overall_score drops below threshold")
    print("    Compare every PR to main branch baseline")


if __name__ == "__main__":
    main()
