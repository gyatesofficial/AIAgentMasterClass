"""
03_rag_agent.py - RAG-Powered Support Agent
============================================
Module 6: RAG for Agents

Combines the RAG pipeline from 02_rag_pipeline.py with an LLM agent
to create a support agent that searches the knowledge base before answering.

The agent follows this pattern:
1. Receive support ticket
2. Search KB for relevant articles
3. Inject KB content into LLM context
4. Generate grounded, accurate response

Key difference from simple KB lookup: the RAG agent automatically
decides WHAT to search for and HOW MANY results to retrieve.

Run with: python module_06_rag/examples/03_rag_agent.py
Requires: OPENAI_API_KEY in .env
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# Reuse KB from previous examples
MOCK_KB = {
    "password reset": "Reset password: login page → Forgot Password → enter email → click reset link (24h expiry). Accounts lock after 5 failed attempts.",
    "2fa authenticator": "2FA recovery: use backup codes or contact support@example.com with ID verification. Access restored within 1 business day.",
    "billing charge refund": "Refund policy: annual plans 30 days, monthly non-refundable. Duplicates refunded 48h. Contact billing@example.com.",
    "export csv data": "Data export: Settings > Export Data. CSV/JSON. Free: 1k rows, Pro: 100k rows. Large exports emailed within 1h.",
    "api rate limit": "API limits: Free 30/min, Pro 500/min, Enterprise custom. 429 error = rate limited. Implement exponential backoff.",
    "account suspended locked": "Account suspension: payment failure = 30-day grace period. Locked account: auto-unlock 30 min or contact support.",
    "plan upgrade pricing": "Plans: Free $0, Starter $29/mo (5 users), Pro $79/mo (25 users), Enterprise custom. Upgrade at Settings > Billing.",
}


def kb_search(query: str, n_results: int = 3) -> list[dict]:
    """Simple KB search for the demo."""
    query_lower = query.lower()
    results = []
    for kb_topic, content in MOCK_KB.items():
        score = sum(1 for word in kb_topic.split() if word in query_lower)
        if score > 0:
            results.append({"topic": kb_topic, "content": content, "score": score / len(kb_topic.split())})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:n_results]


@dataclass
class RAGAgentResult:
    """Result from the RAG-powered agent."""
    response: str
    kb_articles_searched: list[dict]
    search_query_used: str
    model_used: str
    grounded: bool  # True if response was based on KB content


class RAGSupportAgent:
    """
    A support agent that grounds responses in KB content.

    The key pattern:
    1. Analyze the ticket to determine the best KB search query
    2. Retrieve relevant articles
    3. Generate a response that cites and uses the KB content

    This prevents hallucination — the agent can only answer
    what's in the knowledge base.
    """

    SYSTEM = """You are a customer support agent with access to a knowledge base.

When answering support tickets:
1. You will be given relevant KB articles in the context
2. Use ONLY the KB content to answer — don't invent information
3. If the KB doesn't cover the topic, say so and offer to escalate
4. Be specific: quote relevant parts of the KB when helpful
5. Keep responses concise (under 200 words) and actionable

Format your response as a helpful email to the customer."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def _determine_search_query(self, subject: str, body: str) -> str:
        """
        Use LLM to determine the best KB search query.

        Could be done with keyword extraction, but LLM does better
        at understanding intent: "I can't get in" → "password reset login"
        """
        if not os.environ.get("OPENAI_API_KEY"):
            # Simple keyword extraction fallback
            text = f"{subject} {body}".lower()
            keywords = []
            important_words = ["password", "login", "billing", "charge", "export", "api", "account", "suspended", "2fa"]
            for word in important_words:
                if word in text:
                    keywords.append(word)
            return " ".join(keywords[:3]) or text[:50]

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": f"Extract 3-5 key search terms from this support ticket.\nSubject: {subject}\nBody: {body[:200]}\nReturn only the search terms, nothing else."
                }],
                temperature=0,
                max_tokens=30,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return f"{subject[:30]}"

    def answer(
        self,
        ticket_subject: str,
        ticket_body: str,
        customer_name: str = "Customer",
    ) -> RAGAgentResult:
        """
        Answer a support ticket using RAG.

        Args:
            ticket_subject: Ticket subject line
            ticket_body: Full ticket content
            customer_name: Customer's name for personalized response

        Returns:
            RAGAgentResult with the response and metadata
        """
        # Step 1: Determine search query
        search_query = self._determine_search_query(ticket_subject, ticket_body)

        # Step 2: Retrieve KB articles
        kb_results = kb_search(search_query, n_results=3)

        # Step 3: Generate grounded response
        if kb_results:
            kb_context = "\n\n".join(
                f"[KB: {r['topic']}]\n{r['content']}"
                for r in kb_results
            )
        else:
            kb_context = "No relevant knowledge base articles found."

        grounded = len(kb_results) > 0

        if not os.environ.get("OPENAI_API_KEY"):
            # Template response without LLM
            if grounded:
                response = (
                    f"Hi {customer_name},\n\n"
                    f"Thank you for reaching out! Based on our knowledge base:\n\n"
                    f"{kb_results[0]['content']}\n\n"
                    f"Let me know if you need any further assistance!"
                )
            else:
                response = (
                    f"Hi {customer_name},\n\n"
                    f"Thank you for contacting support. I'm escalating your ticket to "
                    f"our team who will respond within 24 hours.\n\nBest,\nSupport Team"
                )
            return RAGAgentResult(
                response=response,
                kb_articles_searched=kb_results,
                search_query_used=search_query,
                model_used="template",
                grounded=grounded,
            )

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

            prompt = (
                f"KNOWLEDGE BASE CONTEXT:\n{kb_context}\n\n"
                f"SUPPORT TICKET:\n"
                f"Customer: {customer_name}\n"
                f"Subject: {ticket_subject}\n"
                f"Message: {ticket_body}\n\n"
                f"Write a helpful response."
            )

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )

            return RAGAgentResult(
                response=response.choices[0].message.content,
                kb_articles_searched=kb_results,
                search_query_used=search_query,
                model_used=self.model,
                grounded=grounded,
            )

        except Exception as e:
            return RAGAgentResult(
                response=f"Error generating response: {e}",
                kb_articles_searched=kb_results,
                search_query_used=search_query,
                model_used=self.model,
                grounded=False,
            )


def main():
    print("\n" + "=" * 60)
    print("  RAG-Powered Support Agent Demo")
    print("=" * 60)

    agent = RAGSupportAgent()

    test_tickets = [
        ("Can't log in after forgot password", "I tried to log in but I forgot my password. I clicked forgot password but the email never came.", "Alice"),
        ("Confused about pricing", "What's the difference between Pro and Enterprise? We have 30 users.", "Bob"),
    ]

    for subject, body, name in test_tickets:
        print(f"\n  Ticket: '{subject}'")
        result = agent.answer(subject, body, name)

        print(f"  Search query used: '{result.search_query_used}'")
        print(f"  KB articles found: {len(result.kb_articles_searched)}")
        for article in result.kb_articles_searched:
            print(f"    - {article['topic']} (score: {article['score']:.1f})")
        print(f"  Grounded response: {result.grounded}")
        print(f"\n  Response:\n{result.response[:300]}")
        print()


if __name__ == "__main__":
    main()
