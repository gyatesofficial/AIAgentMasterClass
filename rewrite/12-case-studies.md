# Module 12: Case Studies — Real-World Systems

This module examines five systems operating at extraordinary scale. For each, we'll focus on the business problem, the architectural decisions, and the lessons you can apply to your own work.

---

## 12.1 Netflix: The Analytics Platform

### The Business Challenge

Netflix serves 200+ million subscribers across 190 countries. Every interaction — every play, pause, search, scroll, and skip — generates events that feed recommendations, A/B tests, content decisions, and business intelligence. The platform processes **500 billion events per day**.

The core challenge: Netflix needs both real-time processing (personalize what you see *right now*) and batch processing (understand what content to license and produce). These have fundamentally different latency requirements, reliability needs, and computational characteristics.

### Scale

- 500 billion events/day from 200M+ subscribers
- Real-time recommendations served in <100ms
- Thousands of A/B experiments running simultaneously
- Processing infrastructure spans multiple AWS regions

### Architecture Overview

Netflix's architecture cleanly separates two data paths. The **real-time path** uses Mantis (their custom stream processing framework) and Keystone (their event collection pipeline) to process member interactions in milliseconds. When you open Netflix, your recommendations are generated in under 100ms based on your most recent behavior.

The **batch path** uses Spark on EMR, orchestrated by Genie (their job management system), to process the complete event history. This produces the business intelligence that drives content strategy — which shows to renew, what genres to invest in, which markets to expand to.

Events flow through Kafka, with regional clusters handling data residency (EU data stays in EU for GDPR compliance). Every event includes a schema ID from their Schema Registry, enabling safe evolution without breaking consumers.

### Key Technical Innovation: The Experimentation Platform

Netflix's secret weapon isn't their recommendation algorithm — it's their ability to test *everything*. They run thousands of A/B experiments simultaneously, each with rigorous statistical controls.

Here's a simplified view of how experiment assignment works — the critical insight is that assignment is deterministic (same user always gets the same variant) using consistent hashing:

```python
import hashlib

def assign_experiment_variant(member_id: str, experiment_id: str,
                               variants: list, traffic_split: list) -> str:
    """Deterministic experiment assignment using consistent hashing.

    The same member always gets the same variant for a given experiment,
    even across different servers and sessions. This is critical for
    accurate measurement — inconsistent assignment corrupts results.
    """
    hash_input = f"{member_id}:{experiment_id}".encode()
    hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16)
    bucket = hash_value % 10000  # 10,000 buckets for 0.01% granularity

    cumulative = 0
    for variant, split in zip(variants, traffic_split):
        cumulative += split * 10000
        if bucket < cumulative:
            return variant
    return variants[-1]  # Fallback to last variant
```

Every experiment has guardrail metrics (like churn rate) that automatically halt the experiment if they degrade, regardless of how well the primary metric is performing.

### Lessons Learned

1. **Separate real-time and batch** — they have different requirements and shouldn't compromise each other
2. **Schema evolution is a first-class concern** — with thousands of producers and consumers, breaking changes are catastrophic
3. **Experimentation culture requires infrastructure** — the ability to test everything requires a platform that makes experiments easy, reliable, and statistically rigorous
4. **Build custom when off-the-shelf can't meet your requirements** — Netflix built Mantis because existing stream processors couldn't handle their scale and latency needs

---

## 12.2 Uber: Surge Pricing and Geospatial Processing

### The Business Challenge

Uber operates a two-sided marketplace connecting riders and drivers across 10,000+ cities. The fundamental problem: supply (drivers) and demand (riders) are unevenly distributed and constantly shifting. Surge pricing is the mechanism that balances this marketplace in real-time — every 30 seconds.

### Scale

- 15 million trips per day across 10,000+ cities
- 5 million driver location updates per minute (GPS every 5 seconds)
- Pricing decisions every 30 seconds per geographic cell
- Sub-100ms latency for pricing calculations

### Architecture Overview

Uber's pricing system is built on their **H3 hexagonal grid** — an open-source library that divides the world into hexagonal cells at various resolutions. At resolution 9 (~0.5km hexagons), each city is divided into thousands of cells. For each cell, every 30 seconds, the system calculates supply (available drivers), demand (recent ride requests), and a surge multiplier.

Data flows through Kafka from rider apps and driver apps, processed by Flink for real-time aggregation. An ML demand forecasting model predicts demand 15-30 minutes ahead, enabling proactive driver positioning rather than reactive surge pricing.

### Key Technical Innovation: H3 Hexagonal Grid

Why hexagons instead of squares? Hexagons have a unique property: every neighbor is equidistant from the center. In a square grid, diagonal neighbors are √2 times farther than edge neighbors. This matters for spatial queries like "find all drivers within 2km" — hexagons give consistent distance calculations in all directions.

```python
import h3

def calculate_surge_for_cell(h3_cell: str, drivers: dict,
                              requests: list, config: dict) -> float:
    """Calculate surge multiplier for a single hexagonal cell.

    The algorithm balances three objectives:
    1. Minimize rider wait times (attract more drivers)
    2. Ensure fair driver earnings (incentivize driving)
    3. Maintain rider satisfaction (don't price out customers)
    """
    # Count available drivers in this cell and neighbors
    ring_cells = h3.k_ring(h3_cell, 2)  # Cell + 2 rings of neighbors
    supply = sum(len(drivers.get(cell, [])) for cell in ring_cells)

    # Count recent demand (requests in last 5 minutes)
    recent_cutoff = time.time() - 300
    demand = len([r for r in requests if r['timestamp'] > recent_cutoff])

    if demand == 0:
        return 1.0  # No demand, no surge

    ratio = supply / demand

    # Supply/demand → surge multiplier (exponential curve)
    if ratio >= 2.0:
        # Excess supply — slight discount to attract riders
        return max(0.8, 1.0 - (ratio - 2.0) * 0.1)
    elif ratio >= 1.0:
        # Balanced — no surge
        return 1.0
    else:
        # Supply shortage — surge to attract drivers
        sensitivity = config.get('sensitivity', 2.0)
        max_surge = config.get('max_multiplier', 5.0)
        raw_surge = 1.0 / (ratio ** sensitivity)
        return min(raw_surge, max_surge)
```

The surge price is smoothed over time (exponential smoothing prevents jarring price jumps) and constrained by regulatory limits per city.

### Lessons Learned

1. **Geospatial indexing is a foundational capability** — H3 enables consistent spatial queries at any scale
2. **Forecasting beats reacting** — predicting demand 15 minutes ahead is more valuable than optimizing surge after demand has already spiked
3. **Smoothing matters for user experience** — prices that change every 30 seconds feel chaotic; smoothed prices feel fair
4. **Local context matters** — surge parameters differ by city due to regulation, culture, and market dynamics

---

## 12.3 Spotify: The Recommendation Engine

### The Business Challenge

Spotify has 400+ million users and 80+ million songs. The challenge isn't having enough content — it's matching each user with the right content at the right moment. Too much familiar music and users get bored. Too much new music and they feel lost. The balance between **exploitation** (play what you know you like) and **exploration** (discover something new) is Spotify's core technical challenge.

### Scale

- 30+ billion events per day from 400M+ users
- 100,000 new songs added daily
- 2 billion recommendation requests per day
- Discover Weekly: 400 million personalized playlists generated weekly

### Architecture Overview

Spotify's recommendation system maintains a real-time **taste profile** for every user. As you listen, skip, save, or add to playlists, your profile updates in real-time using exponential moving averages. The system tracks preferences across multiple dimensions: audio features (danceability, energy, tempo), genre weights, artist affinities, and even time-of-day preferences (you might prefer upbeat music during workouts and calm music at night).

A key design choice: **asymmetric learning rates**. The system learns from positive signals (completing a song, saving it) at a rate of 0.1, but learns from negative signals (skipping) at only 0.05. This prevents a single accidental skip from dramatically shifting your profile.

### Key Technical Innovation: Multi-Armed Bandits for Strategy Selection

Spotify doesn't use a single recommendation algorithm. They maintain eight strategies (collaborative filtering, content-based, popularity-based, genre exploration, etc.) and use a **multi-armed bandit** to select which strategy to use for each recommendation slot.

The Upper Confidence Bound (UCB) algorithm balances exploiting the best-known strategy with exploring less-tried ones:

```python
import math

class RecommendationBandit:
    """Multi-armed bandit for selecting recommendation strategies.

    Each strategy is an 'arm'. The bandit tracks the average reward
    (user engagement) for each strategy and explores less-tried ones
    to discover if they might be better.
    """

    def __init__(self, strategies: list):
        self.strategies = strategies
        self.pulls = {s: 0 for s in strategies}     # Times each was used
        self.rewards = {s: 0.0 for s in strategies}  # Cumulative reward
        self.total_pulls = 0

    def select_strategy(self) -> str:
        """Select a strategy using Upper Confidence Bound (UCB).

        UCB = average_reward + confidence_bonus
        The confidence bonus is high for rarely-tried strategies,
        ensuring they get explored. It decreases with more pulls,
        so well-tested strategies are eventually chosen by merit.
        """
        self.total_pulls += 1

        # Ensure each strategy is tried at least 10 times
        for strategy in self.strategies:
            if self.pulls[strategy] < 10:
                return strategy

        # UCB selection
        best_strategy = None
        best_score = -1

        for strategy in self.strategies:
            avg_reward = self.rewards[strategy] / self.pulls[strategy]
            confidence = math.sqrt(
                2 * math.log(self.total_pulls) / self.pulls[strategy]
            )
            ucb_score = avg_reward + confidence

            if ucb_score > best_score:
                best_score = ucb_score
                best_strategy = strategy

        return best_strategy

    def record_feedback(self, strategy: str, reward: float):
        """Update strategy stats based on user engagement.

        Reward signals: completed song (+1.0), saved (+3.0),
        added to playlist (+2.5), shared (+4.0), skipped (-1.0).
        """
        self.pulls[strategy] += 1
        self.rewards[strategy] += reward
```

Discover Weekly generation adds an additional layer: **diversity optimization**. The system uses Maximal Marginal Relevance (MMR) to ensure playlists have variety in genre, artist, and energy level. No more than 2 songs per artist, and the energy arc follows a deliberate shape — moderate start, peak in the middle, gentle wind-down.

### Lessons Learned

1. **Exploration is a feature, not a bug** — users value discovering new music, not just hearing favorites
2. **Asymmetric learning prevents over-correction** — learn faster from positive signals than negative ones
3. **Contextual recommendations outperform static ones** — what you want at 7 AM is different from 11 PM
4. **A/B test everything** — Spotify treats every feature as an experiment and measures engagement rigorously

---

## 12.4 Airbnb: Search and Discovery

### The Business Challenge

Airbnb matches travelers with accommodations from 7+ million listings across 220 countries. Unlike hotel search (where listings are standardized), Airbnb listings are wildly diverse — a Tokyo capsule hotel, a Tuscan villa, a treehouse in Costa Rica. The search system needs to understand not just *where* you want to go, but *what kind of experience* you're looking for.

### Scale

- 500 million searches per year
- 7+ million active listings across 220 countries
- <200ms search latency requirement
- 8% search-to-booking conversion rate

### Architecture Overview

Airbnb's search system processes queries through multiple stages: **query understanding** (NLP to extract intent, dates, guest count, location), **candidate retrieval** (find relevant listings from the 7M catalog), **personalized ranking** (score and order results based on user preferences), and **diversity optimization** (ensure varied results).

The key insight: travel booking is highly contextual. The same user wants different things for a business trip (WiFi, workspace, instant book) versus a family vacation (multiple bedrooms, safety features, kitchen) versus a romantic getaway (unique property, good reviews, scenic location). Airbnb classifies search intent using regex patterns and ML models, then adjusts ranking accordingly.

### Key Technical Innovation: Multi-Signal Personalized Ranking

Airbnb's ranking considers far more than relevance to the query. It combines:

- **Preference match** (40% weight): Does this listing match the user's historical preferences (property type, price range, location type)?
- **Interaction signals** (30% weight): Has the user viewed, saved, or wishlisted similar listings? Have similar users booked this listing?
- **Segment score** (30% weight): Segment-specific features — business travelers value instant book and WiFi; families value capacity and safety; luxury seekers value ratings and uniqueness.

After scoring, a **diversity optimizer** using MMR ensures the top results aren't all the same type of listing. This is crucial — showing 20 similar apartments isn't as helpful as showing a mix of apartments, unique stays, and different neighborhoods.

### Lessons Learned

1. **Intent matters more than keywords** — understanding *why* someone is searching unlocks better results
2. **Diversity is a feature** — homogeneous results feel limiting; varied results feel empowering
3. **Personalization requires restraint** — over-personalizing creates filter bubbles; Airbnb deliberately shows some unexpected options
4. **Multi-modal search is the future** — combining text, images, location, and behavior outperforms any single signal

---

## 12.5 Twitter: Real-Time Analytics

### The Business Challenge

Twitter processes 500+ million tweets per day from 400+ million users. The system must detect trending topics within minutes, identify viral content within seconds, filter spam in real-time, and generate personalized timelines for every user — all while handling 10x traffic spikes during breaking news events.

### Scale

- 500 million tweets/day (25,000 peak tweets/second)
- 50 billion timeline requests per day
- 200 billion timeline generation requests per day
- Trending topics updated every 60 seconds

### Architecture Overview

Twitter's architecture prioritizes speed over perfection. Their trending topic detection uses a **sliding window** approach: for each topic (hashtag or keyword), the system tracks mention frequency over a 15-minute window. The "trending" score isn't just frequency — it's **momentum**: how quickly the topic's mention rate is accelerating compared to its recent baseline.

A topic mentioned 10,000 times per hour isn't trending if it's always at that level. A topic that jumped from 100 to 5,000 mentions in 5 minutes is trending even though its absolute volume is lower.

### Key Technical Innovation: Speed Over Perfection

Twitter's engineering philosophy is a masterclass in pragmatic trade-offs:

```python
class TrendingTopicDetector:
    """Detect trending topics using frequency + momentum.

    The key insight: trending = acceleration, not volume.
    A topic with 10x growth in 5 minutes is more "trending"
    than a topic with 100x the volume but stable rate.
    """

    def __init__(self, window_minutes: int = 15):
        self.window = window_minutes * 60  # seconds
        self.topic_timestamps = {}  # topic -> list of timestamps

    def record_mention(self, topic: str, timestamp: float):
        if topic not in self.topic_timestamps:
            self.topic_timestamps[topic] = []
        self.topic_timestamps[topic].append(timestamp)

    def get_trending(self, now: float, top_n: int = 50) -> list:
        """Calculate trending topics using frequency × momentum.

        Uses approximate algorithms — we accept ~90% accuracy
        for 10x lower latency. In a system processing 25K tweets/sec,
        exact counting would be too expensive.
        """
        cutoff = now - self.window
        scores = []

        for topic, timestamps in self.topic_timestamps.items():
            # Remove old mentions outside the window
            recent = [t for t in timestamps if t > cutoff]
            self.topic_timestamps[topic] = recent

            if len(recent) < 5:
                continue  # Not enough signal

            # Split window: recent half vs earlier half
            midpoint = now - (self.window / 2)
            recent_half = len([t for t in recent if t > midpoint])
            earlier_half = len(recent) - recent_half

            # Momentum: ratio of recent to earlier activity
            if earlier_half > 0:
                momentum = recent_half / earlier_half
            else:
                momentum = recent_half  # New topic, all recent

            # Score = recent volume × momentum
            score = recent_half * momentum
            scores.append({"topic": topic, "score": score,
                          "volume": len(recent), "momentum": momentum})

        # Return top N by score
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_n]
```

This algorithm uses approximate counting and simple arithmetic rather than sophisticated statistical models. It's not as accurate as a full probabilistic model, but it runs in milliseconds across thousands of topics — and at Twitter's scale, that trade-off is the right one.

### Lessons Learned

1. **90% accurate in 100ms beats 99% accurate in 1 second** — for real-time systems, speed wins
2. **Momentum matters more than volume** — acceleration is a better signal than absolute count
3. **Design for spikes** — breaking news can 10x your traffic in minutes; your system must absorb this gracefully
4. **Approximate algorithms are often sufficient** — HyperLogLog for cardinality, Count-Min Sketch for frequency, sampling for analytics

---

## Cross-Company Patterns

Looking across all five case studies, several patterns emerge:

**Event-driven architecture is universal.** Every company uses Kafka (or equivalent) as the backbone for data flow. Events decouple producers from consumers and enable both real-time and batch processing.

**Custom infrastructure at scale.** Netflix built Mantis, Uber built H3, Twitter built custom trending detection. At extreme scale, off-the-shelf solutions hit limits. But most companies should exhaust existing tools before building custom ones — these companies have thousands of engineers maintaining their custom systems.

**ML is deeply integrated into the data path.** Recommendations, pricing, ranking, and content moderation all use ML models served in real-time with strict latency budgets. The feature store pattern appears at every company.

**Experimentation culture requires infrastructure.** Netflix, Spotify, and Airbnb all invest heavily in A/B testing platforms. Making experimentation easy and rigorous accelerates learning and product improvement.

**Trade-offs are explicit and deliberate.** Twitter chooses speed over accuracy. Netflix separates real-time from batch. Uber smooths prices for user experience. Every company makes trade-offs consciously — and documents why.

> **Key Takeaway:** These systems weren't designed on a whiteboard and built in one go. They evolved over years, driven by real problems at real scale. The patterns they settled on — event-driven, separation of concerns, ML integration, experimentation — are battle-tested. Learn from their decisions, but always evaluate trade-offs in the context of *your* specific requirements and scale.

---

## What's Next

Module 13 takes everything you've learned and prepares you for system design interviews and portfolio projects. You'll practice applying these concepts under time pressure and learn to communicate your design decisions clearly.
