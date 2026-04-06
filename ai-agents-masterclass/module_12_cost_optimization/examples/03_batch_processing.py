"""
03_batch_processing.py - Batch Processing for Cost Reduction
=============================================================
Module 12: Cost Optimization

For workloads that don't require immediate responses (nightly reports,
bulk ticket processing, proactive outreach), batch processing reduces
costs significantly:

1. OpenAI Batch API: 50% discount for async batch jobs
2. Grouping similar requests: shared context reduces per-request tokens
3. Parallel processing: maximize throughput, reduce wall clock time
4. Deduplication: skip processing if result already cached

Use cases for batching:
- Overnight ticket triaging
- Bulk KB article summarization
- Weekly customer satisfaction analysis
- Proactive support outreach

Run with: python module_12_cost_optimization/examples/03_batch_processing.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# Batch Job Models
# ──────────────────────────────────────────────────────────────

@dataclass
class BatchItem:
    """A single item to be processed in a batch."""
    item_id: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    """Result for one item in a batch."""
    item_id: str
    output: str
    tokens_used: int
    cost_usd: float
    from_cache: bool = False
    error: Optional[str] = None


@dataclass
class BatchJobResult:
    """Summary of a completed batch job."""
    job_id: str
    total_items: int
    successful: int
    failed: int
    cache_hits: int
    total_tokens: int
    total_cost_usd: float
    wall_time_seconds: float
    results: list[BatchResult] = field(default_factory=list)

    @property
    def tokens_per_second(self) -> float:
        return self.total_tokens / max(self.wall_time_seconds, 0.001)

    @property
    def cost_per_item(self) -> float:
        return self.total_cost_usd / max(self.successful, 1)


# ──────────────────────────────────────────────────────────────
# Deduplication Cache
# ──────────────────────────────────────────────────────────────

class DeduplicationCache:
    """
    Skip processing for items we've already seen.

    Content-addressed: hash the input content to detect
    identical items across batch runs.
    """

    def __init__(self, cache_dir: str = "data/batch_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, str] = {}  # In-memory layer

    def _key(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, content: str) -> Optional[str]:
        key = self._key(content)
        # Check memory first
        if key in self._memory:
            return self._memory[key]
        # Check disk
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            result = json.loads(cache_file.read_text())
            self._memory[key] = result  # Warm memory cache
            return result
        return None

    def set(self, content: str, result: str):
        key = self._key(content)
        self._memory[key] = result
        try:
            cache_file = self.cache_dir / f"{key}.json"
            cache_file.write_text(json.dumps(result))
        except Exception:
            pass  # Memory cache still works


# ──────────────────────────────────────────────────────────────
# Batch Processor
# ──────────────────────────────────────────────────────────────

class BatchProcessor:
    """
    Process large volumes of items efficiently.

    Features:
    - Deduplication (skip items we've already processed)
    - Parallel execution with concurrency limit
    - Progress tracking
    - Cost accumulation
    - Graceful error handling (failed items don't stop the batch)
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        model: str = "gpt-4o-mini",
        dedup_cache: Optional[DeduplicationCache] = None,
    ):
        self.max_concurrent = max_concurrent
        self.model = model
        self.dedup = dedup_cache or DeduplicationCache()
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def _process_one(
        self,
        item: BatchItem,
        processor_fn: Callable[[str], str],
    ) -> BatchResult:
        """Process a single item with deduplication and error handling."""
        async with self._semaphore:
            # Check deduplication cache
            cached = self.dedup.get(item.content)
            if cached:
                return BatchResult(
                    item_id=item.item_id,
                    output=cached,
                    tokens_used=0,
                    cost_usd=0.0,
                    from_cache=True,
                )

            try:
                # Call the processing function
                output = processor_fn(item.content)

                # Estimate tokens (real: use tiktoken)
                input_tokens = len(item.content.split()) * 1.3
                output_tokens = len(output.split()) * 1.3

                cost = (
                    (input_tokens / 1_000_000) * 0.15 +   # gpt-4o-mini input
                    (output_tokens / 1_000_000) * 0.60     # gpt-4o-mini output
                )

                # Cache result for future deduplication
                self.dedup.set(item.content, output)

                return BatchResult(
                    item_id=item.item_id,
                    output=output,
                    tokens_used=int(input_tokens + output_tokens),
                    cost_usd=round(cost, 6),
                )

            except Exception as e:
                return BatchResult(
                    item_id=item.item_id,
                    output="",
                    tokens_used=0,
                    cost_usd=0.0,
                    error=str(e),
                )

    async def run_batch(
        self,
        items: list[BatchItem],
        processor_fn: Callable[[str], str],
        job_id: str = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> BatchJobResult:
        """
        Process all items in the batch concurrently.

        Args:
            items: List of items to process
            processor_fn: Function that processes one item's content
            job_id: Optional identifier for this batch run
            progress_callback: Called with (completed, total) after each item

        Returns:
            BatchJobResult with all results and summary stats
        """
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        job_id = job_id or f"batch_{int(time.time())}"
        start = time.time()

        # Create all tasks
        tasks = [
            asyncio.create_task(self._process_one(item, processor_fn))
            for item in items
        ]

        # Process with progress tracking
        results = []
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            if progress_callback:
                progress_callback(completed, len(items))

        # Sort results to match input order
        result_map = {r.item_id: r for r in results}
        ordered_results = [result_map.get(item.item_id, results[0]) for item in items]

        elapsed = time.time() - start

        return BatchJobResult(
            job_id=job_id,
            total_items=len(items),
            successful=sum(1 for r in results if not r.error),
            failed=sum(1 for r in results if r.error),
            cache_hits=sum(1 for r in results if r.from_cache),
            total_tokens=sum(r.tokens_used for r in results),
            total_cost_usd=sum(r.cost_usd for r in results),
            wall_time_seconds=elapsed,
            results=ordered_results,
        )


# ──────────────────────────────────────────────────────────────
# OpenAI Batch API (Production Pattern)
# ──────────────────────────────────────────────────────────────

def prepare_openai_batch_file(
    items: list[BatchItem],
    system_prompt: str,
    output_path: str,
) -> int:
    """
    Prepare a JSONL file for the OpenAI Batch API.

    The Batch API processes requests asynchronously with a 50% discount.
    You submit a JSONL file and retrieve results within 24 hours.

    File format: one JSON object per line (JSONL)
    Each object: {"custom_id": "...", "method": "POST", "url": "/v1/chat/completions", "body": {...}}
    """
    lines = []
    for item in items:
        request = {
            "custom_id": item.item_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": item.content},
                ],
                "max_tokens": 500,
                "temperature": 0,
            },
        }
        lines.append(json.dumps(request))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    return len(lines)


def submit_openai_batch(batch_file_path: str) -> Optional[str]:
    """
    Submit a batch job to the OpenAI Batch API.

    Returns the batch_id for polling, or None if submission fails.

    In production:
    - Store the batch_id in your database
    - Poll GET /v1/batches/{batch_id} every few minutes
    - Retrieve results from the output file when status = "completed"
    """
    if not os.environ.get("OPENAI_API_KEY"):
        print("    (Skipping — OPENAI_API_KEY not set)")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        with open(batch_file_path, "rb") as f:
            batch_file = client.files.create(file=f, purpose="batch")

        batch = client.batches.create(
            input_file_id=batch_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        )
        return batch.id

    except Exception as e:
        print(f"    Batch submission error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Demo
# ──────────────────────────────────────────────────────────────

def mock_triage_processor(content: str) -> str:
    """Mock ticket classification (simulates LLM call with 10ms latency)."""
    time.sleep(0.01)  # 10ms simulated API latency
    content_lower = content.lower()
    if any(w in content_lower for w in ["password", "login", "access"]):
        return json.dumps({"category": "account_access", "priority": "medium", "confidence": 0.9})
    elif any(w in content_lower for w in ["charge", "billing", "payment"]):
        return json.dumps({"category": "billing", "priority": "high", "confidence": 0.88})
    elif any(w in content_lower for w in ["error", "bug", "crash"]):
        return json.dumps({"category": "technical", "priority": "high", "confidence": 0.85})
    else:
        return json.dumps({"category": "general", "priority": "low", "confidence": 0.7})


async def demo_batch_processing():
    """Show batch processing with deduplication."""
    print("\n  [1] Parallel Batch Processing with Deduplication")

    # Create a batch of 20 tickets (some duplicates to show deduplication)
    ticket_templates = [
        "I forgot my password and can't log in",
        "I was charged twice this month for $79",
        "The export feature gives a 500 error",
        "Can't get 2FA codes after phone upgrade",
        "Need to cancel my subscription",
    ]

    items = []
    for i in range(20):
        content = ticket_templates[i % len(ticket_templates)]
        items.append(BatchItem(
            item_id=f"TKT-{i+1:03d}",
            content=content,
            metadata={"source": "nightly_batch"},
        ))

    processor = BatchProcessor(max_concurrent=5)

    completed_count = [0]
    def progress(done: int, total: int):
        completed_count[0] = done

    start = time.time()
    result = await processor.run_batch(
        items,
        mock_triage_processor,
        job_id="nightly_triage_001",
        progress_callback=progress,
    )
    elapsed = time.time() - start

    print(f"    Processed {result.total_items} tickets in {result.wall_time_seconds:.2f}s")
    print(f"    Cache hits (deduplication): {result.cache_hits}/{result.total_items}")
    print(f"    Successful: {result.successful} | Failed: {result.failed}")
    print(f"    Total tokens: {result.total_tokens:,}")
    print(f"    Total cost: ${result.total_cost_usd:.5f}")
    print(f"    Throughput: {result.total_items / max(result.wall_time_seconds, 0.001):.0f} items/sec")

    # Show sample results
    print("\n    Sample results:")
    for r in result.results[:3]:
        cache_icon = "[cache]" if r.from_cache else "[live] "
        print(f"      {r.item_id} {cache_icon} {r.output[:60]}")


async def demo_openai_batch_api():
    """Show OpenAI Batch API preparation."""
    print("\n  [2] OpenAI Batch API (50% discount for async workloads)")

    items = [
        BatchItem(f"TKT-{i:03d}", f"Ticket content {i}: billing question about invoice")
        for i in range(5)
    ]

    # Prepare batch file
    batch_file = "data/batches/demo_batch.jsonl"
    count = prepare_openai_batch_file(
        items,
        system_prompt="Classify this support ticket. Return JSON: {\"category\": \"...\", \"priority\": \"...\"}",
        output_path=batch_file,
    )
    print(f"    Prepared batch file: {batch_file} ({count} requests)")

    # Show cost comparison
    realtime_cost = count * 0.0005    # ~$0.0005 per request realtime
    batch_cost = realtime_cost * 0.5  # 50% discount
    print(f"    Realtime cost: ${realtime_cost:.4f}")
    print(f"    Batch cost:    ${batch_cost:.4f} (50% savings)")
    print(f"    Trade-off: up to 24 hours completion time")


def demo_cost_comparison():
    """Show projected cost savings across all optimization techniques."""
    print("\n  [3] Cost Optimization Summary")

    daily_tickets = 1000
    model_cost = 0.002  # per ticket with gpt-4o-mini

    scenarios = [
        ("No optimization", daily_tickets, model_cost, 0),
        ("Model routing (80/20)", daily_tickets, model_cost * 0.2 + 0.00003 * 0.8, 0),
        ("+ Semantic caching (40% hit)", daily_tickets, (model_cost * 0.2 + 0.00003 * 0.8) * 0.6 + 0.0001, 0),
        ("+ Batch API (50% remaining)", daily_tickets, ((model_cost * 0.2 + 0.00003 * 0.8) * 0.6 + 0.0001) * 0.5, 0),
    ]

    baseline = None
    for name, count, cost_per, _ in scenarios:
        daily = count * cost_per
        monthly = daily * 30
        if baseline is None:
            baseline = daily
            print(f"    {name:<40} ${daily:.2f}/day  ${monthly:.2f}/mo  (baseline)")
        else:
            savings_pct = (baseline - daily) / baseline * 100
            print(f"    {name:<40} ${daily:.2f}/day  ${monthly:.2f}/mo  ({savings_pct:.0f}% savings)")


async def main():
    print("\n" + "=" * 60)
    print("  Batch Processing for Cost Optimization")
    print("=" * 60)

    await demo_batch_processing()
    await demo_openai_batch_api()
    demo_cost_comparison()

    print("\n  Key batch processing patterns:")
    print("    - Deduplication: skip identical items across runs")
    print("    - Concurrency control: semaphore limits parallel workers")
    print("    - Progress tracking: visibility into long-running jobs")
    print("    - OpenAI Batch API: 50% discount for non-realtime workloads")
    print("    - Graceful failures: errors don't stop the whole batch")


if __name__ == "__main__":
    asyncio.run(main())
