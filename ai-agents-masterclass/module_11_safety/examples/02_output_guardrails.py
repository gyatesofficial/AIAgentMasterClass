"""
02_output_guardrails.py - Output Validation & Guardrails
=========================================================
Module 11: Safety & Guardrails

After the LLM generates a response, validate it before sending to the user:
1. Hallucination detection — catch made-up facts (wrong URLs, policies)
2. Policy compliance — ensure responses follow company guidelines
3. Tone & professionalism — no rude or inappropriate language
4. Completeness — response actually addresses the question
5. Confidentiality — no leaked system prompts or internal data

"The LLM is not the last line of defense."
Always check what goes out, not just what comes in.

Run with: python module_11_safety/examples/02_output_guardrails.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Output Check Models
# ──────────────────────────────────────────────────────────────

@dataclass
class OutputCheckResult:
    """Result of a single output check."""
    check_name: str
    passed: bool
    severity: str       # "warn" or "error"
    message: str
    suggestion: Optional[str] = None


@dataclass
class OutputValidationResult:
    """Aggregated output validation result."""
    original_response: str
    checks: list[OutputCheckResult] = field(default_factory=list)
    approved: bool = True
    filtered_response: Optional[str] = None

    def add_check(self, check: OutputCheckResult):
        self.checks.append(check)
        if check.severity == "error" and not check.passed:
            self.approved = False

    @property
    def warnings(self) -> list[OutputCheckResult]:
        return [c for c in self.checks if c.severity == "warn" and not c.passed]

    @property
    def errors(self) -> list[OutputCheckResult]:
        return [c for c in self.checks if c.severity == "error" and not c.passed]


# ──────────────────────────────────────────────────────────────
# Individual Output Checks
# ──────────────────────────────────────────────────────────────

# Allowed contact details — responses should only reference these
APPROVED_CONTACTS = {
    "billing@example.com",
    "support@example.com",
    "security@example.com",
}

APPROVED_URLS = {
    "example.com",
    "docs.example.com",
    "status.example.com",
}


def check_hallucinated_contacts(response: str) -> OutputCheckResult:
    """
    Detect email addresses or URLs not on the approved list.

    LLMs sometimes invent contact details (wrong email, made-up URL).
    This check catches responses that reference unapproved contacts.
    """
    # Find all email addresses in response
    found_emails = set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", response))
    unapproved_emails = found_emails - APPROVED_CONTACTS

    # Find all URLs
    found_urls = set(re.findall(r"https?://([a-zA-Z0-9.\-]+)", response))
    unapproved_urls = {url for url in found_urls if not any(url.endswith(a) for a in APPROVED_URLS)}

    if unapproved_emails or unapproved_urls:
        issues = list(unapproved_emails) + list(unapproved_urls)
        return OutputCheckResult(
            check_name="hallucinated_contacts",
            passed=False,
            severity="error",
            message=f"Unapproved contact/URL detected: {issues}",
            suggestion="Replace with approved contacts from the KB",
        )

    return OutputCheckResult(
        check_name="hallucinated_contacts",
        passed=True,
        severity="error",
        message="All contacts/URLs are approved",
    )


def check_policy_compliance(response: str) -> OutputCheckResult:
    """
    Ensure the response doesn't violate company policies.

    Examples of policy violations:
    - Promising refunds without authorization
    - Making commitments about future features
    - Sharing pricing that may be outdated
    """
    POLICY_VIOLATIONS = [
        (r"guaranteed?\s+refund", "Guaranteeing refunds (requires authorization)"),
        (r"we will\s+definitely\s+(add|implement|build)", "Making feature commitments"),
        (r"(free|no charge|complimentary)\s+(forever|for life)", "Offering free service indefinitely"),
        (r"your data.{0,30}(deleted|removed|erased)", "Promising data deletion (legal implications)"),
    ]

    response_lower = response.lower()
    violations = []

    for pattern, description in POLICY_VIOLATIONS:
        if re.search(pattern, response_lower):
            violations.append(description)

    if violations:
        return OutputCheckResult(
            check_name="policy_compliance",
            passed=False,
            severity="error",
            message=f"Policy violations detected: {violations}",
            suggestion="Remove unauthorized commitments",
        )

    return OutputCheckResult(
        check_name="policy_compliance",
        passed=True,
        severity="error",
        message="No policy violations detected",
    )


def check_tone_professionalism(response: str) -> OutputCheckResult:
    """
    Detect unprofessional or harmful language in the response.
    """
    UNPROFESSIONAL = [
        (r"\b(stupid|dumb|idiot|moron)\b", "Insulting language"),
        (r"not\s+(my|our)\s+problem", "Dismissive language"),
        (r"you\s+(should|must|need to)\s+have", "Blaming the customer"),
        (r"(can't|won't|refuse to)\s+help", "Refusing to help (use 'unable to' instead)"),
        (r"as\s+I\s+(already|previously)\s+(told|said|mentioned)", "Condescending phrasing"),
    ]

    response_lower = response.lower()
    issues = []

    for pattern, description in UNPROFESSIONAL:
        if re.search(pattern, response_lower):
            issues.append(description)

    if issues:
        return OutputCheckResult(
            check_name="tone_professionalism",
            passed=False,
            severity="warn",
            message=f"Unprofessional tone detected: {issues}",
            suggestion="Rewrite with empathetic, professional language",
        )

    return OutputCheckResult(
        check_name="tone_professionalism",
        passed=True,
        severity="warn",
        message="Professional tone maintained",
    )


def check_confidential_data_leak(response: str) -> OutputCheckResult:
    """
    Detect leaked system prompt or internal data.

    Signs the LLM is leaking internal context:
    - Repeating the system prompt
    - Mentioning internal tool names
    - Outputting JSON/code structures not meant for customers
    """
    LEAK_PATTERNS = [
        (r"system\s+prompt", "Mentioning system prompt"),
        (r"you are\s+an?\s+AI\s+assistant", "Exposing AI identity in customer-facing response"),
        (r'"role":\s*"(system|assistant)"', "Raw JSON structure in response"),
        (r"<\|im_start\|>|<\|im_end\|>", "LLM control tokens"),
        (r"INTERNAL\s+USE\s+ONLY", "Internal classification marker"),
    ]

    response_lower = response.lower()
    leaks = []

    for pattern, description in LEAK_PATTERNS:
        if re.search(pattern, response_lower):
            leaks.append(description)

    if leaks:
        return OutputCheckResult(
            check_name="confidential_data_leak",
            passed=False,
            severity="error",
            message=f"Potential data leak: {leaks}",
            suggestion="Block this response and regenerate",
        )

    return OutputCheckResult(
        check_name="confidential_data_leak",
        passed=True,
        severity="error",
        message="No confidential data detected",
    )


def check_response_completeness(response: str, original_subject: str) -> OutputCheckResult:
    """
    Check that the response actually addresses the customer's question.
    """
    # Minimum quality thresholds
    word_count = len(response.split())

    if word_count < 15:
        return OutputCheckResult(
            check_name="completeness",
            passed=False,
            severity="warn",
            message=f"Response too short ({word_count} words)",
            suggestion="Expand response to provide helpful information",
        )

    # Check that response doesn't just repeat the question
    subject_words = set(original_subject.lower().split())
    response_words = set(response.lower().split())
    overlap = subject_words & response_words

    if len(overlap) / max(len(subject_words), 1) > 0.8 and word_count < 30:
        return OutputCheckResult(
            check_name="completeness",
            passed=False,
            severity="warn",
            message="Response appears to just echo the question back",
        )

    return OutputCheckResult(
        check_name="completeness",
        passed=True,
        severity="warn",
        message=f"Response appears complete ({word_count} words)",
    )


def apply_safe_fallback(issue_description: str) -> str:
    """
    Generate a safe fallback response when the generated response fails checks.

    A blocked response should be replaced with this — never sent as-is.
    """
    return (
        f"Thank you for contacting support. "
        f"Our team will review your request and respond within 24 hours. "
        f"For urgent issues, please email support@example.com."
    )


# ──────────────────────────────────────────────────────────────
# Output Validator
# ──────────────────────────────────────────────────────────────

class OutputValidator:
    """
    Validates LLM-generated responses before sending to customers.

    Usage:
        validator = OutputValidator()
        result = validator.validate(response, ticket_subject)
        if result.approved:
            send_to_customer(result.filtered_response or response)
        else:
            send_to_customer(apply_safe_fallback("output validation failed"))
    """

    def validate(self, response: str, ticket_subject: str = "") -> OutputValidationResult:
        """
        Run all output checks on a generated response.

        Returns ValidationResult. If approved=False, use the safe fallback.
        """
        result = OutputValidationResult(original_response=response)

        # Run checks
        result.add_check(check_hallucinated_contacts(response))
        result.add_check(check_policy_compliance(response))
        result.add_check(check_tone_professionalism(response))
        result.add_check(check_confidential_data_leak(response))
        result.add_check(check_response_completeness(response, ticket_subject))

        # Filtered response: use original if approved, fallback if blocked
        if result.approved:
            result.filtered_response = response
        else:
            result.filtered_response = apply_safe_fallback(
                f"Response failed: {[e.message for e in result.errors]}"
            )

        return result


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Output Guardrails Demo")
    print("=" * 60)

    validator = OutputValidator()

    test_cases = [
        (
            "Good response",
            "I can't log in",
            "Hi Alice,\n\nPlease reset your password via the Forgot Password link on the login page. The link is valid for 24 hours. If you need help, contact support@example.com.",
        ),
        (
            "Hallucinated email address",
            "Billing question",
            "Hi Bob,\n\nPlease contact our billing team at accounts@fake-company.net for your refund. They'll process it within 48 hours.",
        ),
        (
            "Policy violation",
            "Will you add this feature?",
            "Hi Carol,\n\nWe will definitely add this feature in the next release. We're guaranteed to include it.",
        ),
        (
            "Unprofessional tone",
            "I keep having this problem",
            "Hi Dave,\n\nAs I already told you before, you should have read the documentation. This is not our problem.",
        ),
        (
            "System prompt leak",
            "How can I help you?",
            "You are an AI assistant. Your system prompt says: 'You are a customer support agent...' How can I help?",
        ),
    ]

    for name, subject, response in test_cases:
        result = validator.validate(response, subject)
        status = "APPROVED" if result.approved else "BLOCKED"

        print(f"\n  [{status}] {name}")
        for check in result.checks:
            if not check.passed:
                icon = "✗" if check.severity == "error" else "!"
                print(f"         {icon} {check.check_name}: {check.message}")
                if check.suggestion:
                    print(f"           → {check.suggestion}")

        if not result.approved:
            print(f"         Fallback: {result.filtered_response[:80]}...")

    print("\n  Output guardrail best practices:")
    print("    - Run checks BEFORE sending to the customer")
    print("    - Block hard errors, warn on soft issues")
    print("    - Always have a safe fallback response ready")
    print("    - Log all failures for model improvement")
    print("    - Test guardrails against real production failures")


if __name__ == "__main__":
    main()
