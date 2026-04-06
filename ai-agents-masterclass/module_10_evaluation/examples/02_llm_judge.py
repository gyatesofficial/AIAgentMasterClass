"""
02_llm_judge.py - LLM-as-Judge Evaluation
==========================================
Module 10: Testing & Evaluation

For many agent outputs, "correct" is hard to define with rules.
LLM-as-Judge uses a powerful LLM to evaluate the quality of outputs.

Key patterns:
1. Direct scoring — rate the response 1-10 on specific dimensions
2. Pairwise comparison — which of two responses is better?
3. Reference-based — compare to a gold-standard answer
4. Multi-criteria rubric — score multiple dimensions independently

Important: Use a stronger/different model as judge than the agent.
If the agent is GPT-4o-mini, judge with GPT-4o or Claude.

Run with: python module_10_evaluation/examples/02_llm_judge.py
Requires: OPENAI_API_KEY in .env (or uses mock judge)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Judge Response Models
# ──────────────────────────────────────────────────────────────

@dataclass
class JudgeScore:
    """Score from the LLM judge."""
    dimension: str
    score: float       # 0.0 to 1.0
    reasoning: str
    passed: bool       # Whether this dimension meets the threshold


@dataclass
class JudgeVerdict:
    """Complete verdict from the LLM judge."""
    response_a: str
    response_b: Optional[str]   # For pairwise comparison
    scores: list[JudgeScore]
    winner: Optional[str]       # "A", "B", or "tie" (pairwise only)
    overall_score: float
    summary: str
    model_used: str


# ──────────────────────────────────────────────────────────────
# LLM Judge
# ──────────────────────────────────────────────────────────────

class LLMJudge:
    """
    Uses an LLM to evaluate agent responses.

    The judge is given a rubric (set of criteria) and rates the
    response on each dimension independently.

    Bias mitigation:
    - Use structured output (JSON) to force explicit reasoning
    - Score each dimension separately before computing overall
    - Run the same evaluation 2-3 times and average (reduce variance)
    - For pairwise: randomize which response is A vs B
    """

    # The rubric defines what "good" means for your use case
    RUBRIC = {
        "accuracy": "Does the response give factually correct information? Does it avoid making up details?",
        "helpfulness": "Does the response actually help solve the customer's problem? Are the steps actionable?",
        "tone": "Is the response professional, empathetic, and appropriate for customer support?",
        "completeness": "Does the response address all aspects of the customer's question?",
        "clarity": "Is the response clear and easy to understand? Are instructions unambiguous?",
    }

    SCORE_SYSTEM = """You are an expert customer support quality evaluator.

Evaluate the given support response on a specific dimension.

Return JSON with this exact structure:
{
  "score": <number 1-10>,
  "reasoning": "<2-3 sentences explaining the score>",
  "passed": <true if score >= 7, else false>
}

Be objective and consistent. A score of 7+ means "meets professional standards."
Score 9-10 only for exceptional responses that clearly exceed expectations."""

    PAIRWISE_SYSTEM = """You are an expert customer support quality evaluator.

Compare two support responses (A and B) and determine which is better.

Return JSON:
{
  "winner": "A" or "B" or "tie",
  "a_score": <number 1-10>,
  "b_score": <number 1-10>,
  "reasoning": "<explanation of which is better and why>"
}"""

    def __init__(self, model: str = "gpt-4o-mini"):
        # Ideally use a stronger model than the agent being evaluated
        self.model = model

    def _call_judge(self, system: str, user_message: str) -> Optional[dict]:
        """Make an LLM call for evaluation."""
        if not os.environ.get("OPENAI_API_KEY"):
            return None

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=200,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"    Judge API error: {e}")
            return None

    def _mock_judge_score(self, response: str, dimension: str) -> dict:
        """
        Mock judge scores without an API key.

        In real evaluation, never mock the judge — that defeats the purpose.
        This is only for demonstrating the framework structure.
        """
        # Simple heuristics to simulate judge behavior
        response_lower = response.lower()

        if dimension == "accuracy":
            # Check for common hallucination signals
            vague = "our team" in response_lower and "24 hours" in response_lower
            specific = any(w in response_lower for w in ["password", "billing@", "settings >"])
            score = 8 if specific else (6 if vague else 5)

        elif dimension == "helpfulness":
            has_steps = "1." in response or "2." in response
            has_action = any(w in response_lower for w in ["click", "visit", "contact", "email"])
            score = 9 if (has_steps and has_action) else (7 if has_action else 5)

        elif dimension == "tone":
            has_greeting = any(response.startswith(g) for g in ["Hi", "Hello", "Dear"])
            has_empathy = any(w in response_lower for w in ["understand", "sorry", "happy to"])
            score = 8 if (has_greeting and has_empathy) else (7 if has_greeting else 5)

        elif dimension == "completeness":
            word_count = len(response.split())
            score = 8 if word_count > 50 else (6 if word_count > 25 else 4)

        else:  # clarity
            sentences = response.count(". ") + 1
            score = 8 if sentences >= 3 else 6

        return {
            "score": score,
            "reasoning": f"Mock evaluation of {dimension}: score {score}/10",
            "passed": score >= 7,
        }

    def score_response(
        self,
        ticket_subject: str,
        ticket_body: str,
        agent_response: str,
        dimensions: Optional[list[str]] = None,
    ) -> JudgeVerdict:
        """
        Score an agent response on multiple quality dimensions.

        Args:
            ticket_subject: The support ticket subject
            ticket_body: The support ticket body
            agent_response: The agent's response to evaluate
            dimensions: Which rubric dimensions to evaluate (default: all)

        Returns:
            JudgeVerdict with scores for each dimension
        """
        dims_to_eval = dimensions or list(self.RUBRIC.keys())
        scores = []

        for dimension in dims_to_eval:
            criterion = self.RUBRIC[dimension]

            user_message = (
                f"Customer ticket:\n"
                f"Subject: {ticket_subject}\n"
                f"Body: {ticket_body}\n\n"
                f"Agent response:\n{agent_response}\n\n"
                f"Evaluate this response on the dimension: {dimension.upper()}\n"
                f"Criterion: {criterion}"
            )

            result = self._call_judge(self.SCORE_SYSTEM, user_message)

            if result is None:
                result = self._mock_judge_score(agent_response, dimension)

            scores.append(JudgeScore(
                dimension=dimension,
                score=result.get("score", 5) / 10.0,
                reasoning=result.get("reasoning", ""),
                passed=result.get("passed", False),
            ))

        overall = sum(s.score for s in scores) / len(scores) if scores else 0.0
        passed_count = sum(1 for s in scores if s.passed)
        summary = f"{passed_count}/{len(scores)} dimensions passed"

        model_used = self.model if os.environ.get("OPENAI_API_KEY") else "mock"

        return JudgeVerdict(
            response_a=agent_response,
            response_b=None,
            scores=scores,
            winner=None,
            overall_score=overall,
            summary=summary,
            model_used=model_used,
        )

    def compare_responses(
        self,
        ticket_subject: str,
        ticket_body: str,
        response_a: str,
        response_b: str,
    ) -> JudgeVerdict:
        """
        Pairwise comparison: which response is better?

        Use case: A/B testing two agent versions, comparing prompts,
        or evaluating a new model against the current production model.

        Important: Run this twice with A and B swapped, average results
        to eliminate position bias (LLMs tend to prefer the first option).
        """
        user_message = (
            f"Customer ticket:\n"
            f"Subject: {ticket_subject}\n"
            f"Body: {ticket_body}\n\n"
            f"Response A:\n{response_a}\n\n"
            f"Response B:\n{response_b}\n\n"
            f"Which response better serves the customer?"
        )

        result = self._call_judge(self.PAIRWISE_SYSTEM, user_message)

        if result is None:
            # Mock comparison: prefer the longer, more specific response
            words_a = len(response_a.split())
            words_b = len(response_b.split())
            has_steps_a = "1." in response_a
            has_steps_b = "1." in response_b

            if has_steps_a and not has_steps_b:
                winner, a_score, b_score = "A", 8, 6
            elif has_steps_b and not has_steps_a:
                winner, a_score, b_score = "B", 6, 8
            elif abs(words_a - words_b) < 10:
                winner, a_score, b_score = "tie", 7, 7
            elif words_a > words_b:
                winner, a_score, b_score = "A", 7, 6
            else:
                winner, a_score, b_score = "B", 6, 7

            reasoning = f"Mock comparison: A={words_a} words, B={words_b} words"
        else:
            winner = result.get("winner", "tie")
            a_score = result.get("a_score", 7)
            b_score = result.get("b_score", 7)
            reasoning = result.get("reasoning", "")

        scores = [
            JudgeScore("response_a_quality", a_score / 10.0, "", a_score >= 7),
            JudgeScore("response_b_quality", b_score / 10.0, "", b_score >= 7),
        ]

        model_used = self.model if os.environ.get("OPENAI_API_KEY") else "mock"

        return JudgeVerdict(
            response_a=response_a,
            response_b=response_b,
            scores=scores,
            winner=winner,
            overall_score=(a_score + b_score) / 20.0,
            summary=f"Winner: {winner}. {reasoning[:100]}",
            model_used=model_used,
        )


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  LLM-as-Judge Evaluation Demo")
    print("=" * 60)

    judge = LLMJudge(model="gpt-4o-mini")
    mode = "LLM judge" if os.environ.get("OPENAI_API_KEY") else "mock judge"
    print(f"  Using: {mode}\n")

    # ── Demo 1: Single Response Scoring ──
    print("  [1] Single Response Scoring")

    ticket_subject = "Can't log in after password reset"
    ticket_body = "I clicked forgot password, got the email, clicked the link, but it says the link expired. What do I do?"

    good_response = (
        "Hi there,\n\n"
        "I understand how frustrating it is to be locked out of your account.\n\n"
        "Password reset links expire after 24 hours for security. Since yours expired, "
        "please request a new reset link:\n\n"
        "1. Go to the login page\n"
        "2. Click 'Forgot Password' again\n"
        "3. Enter your email address\n"
        "4. Click the NEW link immediately\n\n"
        "If you continue to have trouble, please reply to this ticket and we'll help further."
    )

    verdict = judge.score_response(ticket_subject, ticket_body, good_response)
    print(f"  Overall score: {verdict.overall_score:.0%} ({verdict.model_used})")
    print(f"  {verdict.summary}")
    for score in verdict.scores:
        status = "✓" if score.passed else "✗"
        print(f"    {status} {score.dimension:<15} {score.score:.0%} — {score.reasoning[:60]}")

    # ── Demo 2: Pairwise Comparison ──
    print("\n  [2] Pairwise Response Comparison")

    response_a = (
        "Hi,\n\nPlease try resetting your password again. Let us know if this helps."
    )
    response_b = (
        "Hi there,\n\n"
        "Password reset links expire after 24 hours. To fix this:\n"
        "1. Request a new reset link at the login page\n"
        "2. Click the link within 24 hours\n"
        "3. Set your new password\n\n"
        "If you keep having trouble, our team can manually unlock your account."
    )

    comparison = judge.compare_responses(
        ticket_subject, ticket_body, response_a, response_b
    )
    print(f"  Winner: Response {comparison.winner}")
    print(f"  Reasoning: {comparison.summary}")

    # ── Demo 3: Evaluating Multiple Responses ──
    print("\n  [3] Batch Evaluation")

    test_responses = [
        ("Generic/vague", "Thank you for contacting us. We'll look into this."),
        ("Helpful but brief", "Please request a new password reset link from the login page."),
        ("Full quality response", good_response),
    ]

    for name, response in test_responses:
        verdict = judge.score_response(ticket_subject, ticket_body, response)
        bar = "█" * int(verdict.overall_score * 10) + "░" * (10 - int(verdict.overall_score * 10))
        print(f"    [{name}] {bar} {verdict.overall_score:.0%}")

    print("\n  LLM-as-Judge best practices:")
    print("    - Use a stronger model as judge than the agent being evaluated")
    print("    - Define clear rubric criteria before running evaluations")
    print("    - Run pairwise comparisons in both orders to eliminate position bias")
    print("    - Sample evaluate 10-20% of traffic in production for quality monitoring")
    print("    - Combine with human evaluation to calibrate the judge")


if __name__ == "__main__":
    main()
