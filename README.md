# StormTracker 🌩️

StormTracker is a Telegram-native, AI-powered assistant designed to automate the tracking, grading, and reporting of daily ear-training assignments for music groups.

> 🤖 **Live Bot**: StormTracker is live on Telegram! Chat with the assistant directly at [@MightyStormBot](https://t.me/MightyStormBot) (`https://t.me/MightyStormBot`).

> **Origins**: This project was originally built for **Mighty Storm**, a dedicated music group within the **Fellowship of Christian Students (FCS) at Ahmadu Bello University (ABU), Samaru, Zaria, Kaduna State, Nigeria**, to help members stay accountable in their daily musical development.

---

## 🌟 Part 1: User-Friendly Overview

### What is StormTracker?

Tracking daily submissions via direct messaging creates a cluttered inbox, wastes hours of manual logging, and provides zero actionable analytics. StormTracker solves this by acting as an autonomous group manager that handles the collection, grading, and analysis of daily assignments entirely through natural chat.

### Not Just a Bot, but a True AI Agent
StormTracker is not a rigid, amnesiac script. It is built as a **ReAct (Reason + Act) AI Agent**, meaning it behaves like a human manager:
- **It Remembers You**: It maintains a deep, 4-tiered memory system spanning active context (50 turns), narrative summaries (500 words), permanent knowledge graphs, and a hybrid RRF historical archive.
- **It Thinks Before Acting**: When you ask a question, it pauses to *reason* about what you need using a strict Think-Plan-Tool-Speak protocol, deciding whether to check analytics, search past conversations via hybrid RAG, or chat naturally.
- **It Takes Initiative**: It doesn't just wait for you to text it. It manages its own schedule to send reminders, generate midnight reports, and maintain long-term memory background workers.

### 🎯 Key Benefits & Features

*   **Effortless Image Processing**: Send a screenshot of your daily exercise (e.g., from TonedEar). The AI instantly reads the image, grades it, extracts device nonces, and logs your score.
*   **Deep Active Context (50 Turns)**: The agent holds up to 50 active dialogue turns in fast working memory, allowing for long, natural conversations without forgetting immediate instructions.
*   **Hybrid RRF Past Conversation Search**: Ask about previous topics, advice, or instructions (*"What reference song did you suggest for minor 2nds last week?"*), and the agent runs multi-query parallel hybrid searches (dense vector + sparse text search) to retrieve exact historical dialogue.
*   **Proactive Reminders (Nudges)**: If you forget to submit your assignment, the bot sends friendly direct messages at 9:00 AM and 8:00 PM to keep you accountable.
*   **Cross-User Anti-Cheat Protection**: The system performs vector similarity and metadata nonces checks across the **entire database (all users)**, instantly rejecting duplicate submissions even if shared across members.
*   **Automated PDF Reports**: At midnight, StormTracker generates a detailed PDF report containing group averages, visual bar charts, and a list of missing submissions, delivering it directly to administrators.
*   **Chat with your Data & On-Demand Reporting**: Ask naturally, *"How is John doing on Chords this week?"* or *"What is my average score?"*, and the AI analyzes performance metrics instantly.
*   **Direct Admin Communication**: Administrators can send direct one-on-one messages or group broadcasts through the bot, automatically injecting notifications into members' persistent memory.
*   **Autonomous Profile Management**: Users can dynamically update their personal information (such as correcting their full name) at any time through natural conversation.
*   **Universal Access**: Not part of the official group? Join as a **Public User** to track your progress privately while core members follow the group curriculum.

---

## ⚙️ Part 2: Technical Architecture & Innovations

This section details the advanced engineering, security layers, and memory architecture powering StormTracker.

### Core Intelligence & Routing
StormTracker is driven by a hybrid intelligence model:
- **Primary Engine**: Core conversational, reasoning, and tool execution tasks are powered by `Gemma 4 26B-A4B-it` / `Gemma 4 31b-it`.
- **Dynamic Routing & Reasoning**: OpenRouter integrations route background summarization, embedding generation, and fact extraction to dedicated reasoning models.

### Advanced Prompt Engineering & Agent Control
StormTracker utilizes a production-grade system prompt designed to control the ReAct Agent's autonomous behavior:
- **Think-Plan-Tool-Speak Cognitive Protocol**: Enforces step-by-step reasoning before tool calls or user responses.
- **Strict RAG Tool Prompt Enforcement**: Mandates autonomous invocation of `search_past_conversations` whenever a user asks about past conversations, advice, or prior instructions not present in active memory or facts.
- **Prompt-Enforced RBAC & Gatekeeping**: Role-Based Access Control and onboarding state machines (New -> Pending -> Member/Public) are enforced natively via prompt rules and execution guards.
- **Recency Bias Optimization**: Dynamic memory blocks (summary, facts, status) are injected at the absolute bottom of the system prompt to maximize attention mechanism focus right before token generation.

---

### 🧠 Cognitive Memory Architecture (4-Tier Hybrid System)

To support continuous context without amnesia while keeping API costs low, StormTracker implements a **4-Tier Cognitive Memory System** distributed across Redis and PostgreSQL (Supabase):

```
┌─────────────────────────────────────────────────────────────┐
│ 1. WORKING MEMORY (Redis Cache / DB Cold-Start)              │
│    - Fast sliding window of 50 active dialogue turns       │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Eviction via Redis LTRIM)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. EPISODIC NARRATIVE SUMMARY (Gemma 31B Background Loop)   │
│    - Rolling summary (< 500 words) of narrative & momentum │
│    - Mathematically calibrated max_tokens = 875             │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────┴──────────────────────────────┐
│ 3. SEMANTIC KNOWLEDGE GRAPH  │ 4. DEEP HISTORICAL RAG ARCHIVE│
│    (PGVector Cosine Search) │    (Hybrid Dense + TSVector)  │
│    - Permanent facts        │    - Role-attributed chunks   │
│    - Think-Plan-Execute JSON│    - Reciprocal Rank Fusion   │
│    - UUID hallucination     │    - Multi-query parallel     │
│      fallback to CREATE     │      search tool              │
└──────────────────────────────┴──────────────────────────────┘
```

#### Tier 1: Working Memory (Sliding Window & Cold-Start Recovery)
- **Active Window**: Holds up to **50 dialogue turns** in Redis (`chat:history:{telegram_id}`).
- **Cold-Start Recovery**: If Redis cache expires, the system queries PostgreSQL (`ChatMessage`), pulling the last 50 turns ordered by `created_at DESC` and reversing in-memory to instantly restore chronological context.

#### Tier 2: Episodic Narrative Summary (Background Worker)
- **Buffer & Trigger**: When active history exceeds 50 turns, evicted messages are formatted with speaker role tags (`HUMAN: ...`, `AI: ...`, `SYSTEM: ...`) and appended to `chat:overflow:{telegram_id}`. Once the overflow buffer reaches 20 messages, a background worker (`process_cognitive_memory`) runs under a Redis Mutex (`cognitive_lock:{telegram_id}`).
- **Narrative Scope**: Updates `User.conversation_summary` to keep a chronological narrative (**strictly under 500 words**) focused on momentum and current struggles.
- **Mathematical Token Calibration**: `max_tokens` for summary generation is mathematically calculated as:
  $$\text{Base Tokens} = 500 \text{ words} \times 1.4 \text{ BPE tokens/word} = 700 \text{ tokens}$$
  $$\text{Max Tokens} = 700 \times 1.25 \text{ (25\% reasoning/safety buffer)} = 875 \text{ tokens}$$

#### Tier 3: Semantic Knowledge Graph (Fact Extraction & Auto-Retrieval)
- **Think-Plan-Execute Protocol**: Background processing executes Pipeline B using `FACT_EXTRACTOR_PROMPT`. The LLM outputs structured JSON (`think`, `plan`, `action`, `target_existing_fact_id`, `final_fact_text`) to manage permanent facts.
- **Robust UUID Fallback**: If an LLM returns a hallucinated, non-existent, or invalid UUID during an `UPDATE` action, the system catches `ValueError` and checks `rowcount > 0`, automatically falling back to creating a new `UserMemoryFact` (`CREATE`) to eliminate memory loss.
- **Auto-Retrieval**: On incoming messages, `retrieve_relevant_facts` generates a text embedding, calculates cosine distance (`distance < 0.75`), and auto-injects top matching permanent facts into system prompt context.

#### Tier 4: Deep Historical Archive & Hybrid RRF RAG Engine
- **Role-Attributed Storage**: Evicted message blocks are stored as `ChatHistoryChunk` in PostgreSQL with role attribution, 2048-dim vector embeddings, and GIN-indexed `TSVector` columns (`search_tsvector = Computed("to_tsvector('english', chunk_text)", persisted=True)`).
- **Reciprocal Rank Fusion (RRF)**: The `vector_service.py` engine executes a single raw SQL query combining dense cosine vector distance (`<=> < 0.75`) and sparse full-text search (`ts_rank` over `search_tsvector`) with rank constant $k=60$:
  $$\text{RRF Score} = \frac{1}{60 + \text{Dense Rank}} + \frac{1}{60 + \text{Sparse Rank}}$$
- **Multi-Query Parallel RAG Tool (`search_past_conversations`)**: Generates embeddings and executes hybrid searches in parallel via `asyncio.gather`, deduplicates chunks by peak RRF score, filters low-confidence matches (`score < 0.015`), and surfaces top 5 formatted chunks to the agent.

---

### Cloud Infrastructure & Supabase Decoupling Architecture

StormTracker's production topology utilizes a **Decoupled Managed Cloud Infrastructure**:
- **Managed Database Layer (Supabase)**: The database is fully offloaded to a managed cloud PostgreSQL instance running `pgvector` and `TSVector` capabilities. This eliminates RAM pressure on single-node deployment hosts, guarantees zero-downtime connection pooling (`asyncpg`), and delegates hardware backups to Supabase.
- **Clean Lifespan Decoupling**: Database extensions (`vector`) are managed directly via cloud dashboard privileges, removing programmatic `CREATE EXTENSION` startup locks to comply with managed cloud permission models.
- **Lightweight Micro-Services Container Stack (`docker-compose.prod.yml`)**:
  - `app`: FastAPI application server running Uvicorn workers.
  - `redis`: Ultra-fast in-memory cache for working memory sliding windows, mutex locks, and rate limits.
  - `caddy`: Production reverse proxy providing automatic Let's Encrypt SSL certificates.

---

### Security, Anti-Cheat & Asynchronous Data Safety

- **Redis LTRIM Async Data Safety**: To prevent data erasure when users send messages during background summarization/embedding runs, `process_cognitive_memory` executes `await redis_client.ltrim(overflow_key, len(evicted_messages), -1)`, removing only the processed batch while safely preserving incoming turns.
- **Cross-User Anti-Cheat System**: `fraud_service.py` scans `Metric.image_vector` and `Metric.device_metadata` nonces (status bar time + battery percentage) across the **entire database (all users)**, blocking cross-user screenshot sharing within 24-hour windows.
- **Argon2id Async Passkey Hashing**: All invite tokens use prefix-based `prefix-secret` keys in Redis ($O(1)$ lookup) and Argon2id hashing offloaded to `asyncio.to_thread`.
- **Role-Based Rate Limiting**: Intercepts webhook traffic enforcing request quotas (20 req/min for members/admins; 5 req/min for public users).

---

### Legal Compliance & Static Egress
- **Inline Consent Gateway**: New users accept Privacy Policy & Terms of Use via Inline Keyboards prior to processing. Agreement logs (`has_consented`, `consented_at`) are saved in PostgreSQL.
- **Static Asset Mount**: Served securely via Caddy SSL reverse proxy.

---

### Observability & Resilience
- **Langfuse Tracing**: Complete observability over LangGraph node execution, OpenRouter tool bindings, and background cognitive processing.
- **APScheduler & Out-of-Band Persistence**: Nudge reminders and midnight reports execute out-of-band while persisting system turns into user memory timelines via `persist_turn`.
- **Automated CI/CD Pipeline**: GitHub Actions (`deploy.yml`) builds container images, performs linting checks, deploys container services to production hosts, and runs async database schema migrations (`alembic upgrade head`) directly against Supabase.

---

## 🚀 Getting Started

### Prerequisites
* Telegram Bot Token (via [@BotFather](https://t.me/botfather))
* API Keys for OpenRouter (Embeddings & Reasoning Models), Google AI Studio, and Langfuse (optional).
* Supabase PostgreSQL Database URI (`DATABASE_URL`).
* Docker & Docker Compose installed.

### Quick Start
1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/stormtracker.git
   cd stormtracker
   ```
2. **Configure your environment:**
   Copy `.env.example` to `.env` and fill in required keys (including your Supabase `DATABASE_URL`).
3. **Deploy:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

### Access Control & Roles
- **Root**: System owners (manage verifications, invite tokens, broadcasts).
- **Admin**: Staff (message members, run reports, query group analytics).
- **Member**: Verified group members (data included in group reports).
- **Public**: Guests (data excluded from group reports).
