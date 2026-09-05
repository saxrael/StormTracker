# PROJECT BRIEF

## 1. One-Line Summary
StormTracker is a Telegram-native, AI-powered assistant designed to automate the tracking, grading, and reporting of daily ear-training assignments for a music group using multimodal image processing and a ReAct agent architecture.

## 2. The Problem
Manually tracking daily ear-training submissions via direct messaging is chaotic, creating a cluttered inbox, wasting hours of manual logging, and providing zero actionable analytics on how students are actually performing. This pain is felt acutely by the administrators and mentors of the Mighty Storm music group (FCS ABU, Zaria) who need to hold members accountable. Without an automated system, members fall off the wagon and administrators drown in screenshots.

## 3. What Was Actually Built
A fully autonomous Telegram ReAct agent built with LangGraph. Users chat with the bot naturally and submit screenshots of their ear-training apps (like TonedEar). The agent uses an LLM to read the image, extract performance metrics, grade them, and store them in PostgreSQL. It maintains long-term conversational memory and autonomously runs anti-cheat algorithms to prevent duplicate submissions. The bot also runs on a cron schedule to send nudges to members who haven't submitted and generates PDF reports for admins at midnight.

```text
      User (Telegram)
             |
             v
    [ Webhook (FastAPI) ]
             |
       [ ARQ Worker ]
             |
      [ LangGraph ReAct Agent (Gemma 4 via OpenRouter) ]
       /                 |                      \
 [ Redis ]       [ Tool Router ]         [ Fact/Summary Extractor ]
(Sliding Window)         |                     (Background)
                         v                          |
                 [ Anti-Cheat & DB ]                v
                 (PostgreSQL/pgvector)   <---- [ RAG / Memory ]
```

## 4. Tech Stack (Verified, Not Assumed)
- **Python 3.11+**: Primary language.
- **FastAPI & Uvicorn**: Web server for handling incoming Telegram webhooks (see `pyproject.toml`).
- **SQLAlchemy (asyncio) & asyncpg**: ORM and async database adapter.
- **Alembic**: Database migrations.
- **pgvector**: Used in PostgreSQL to store image and text embeddings for anti-cheat visual search and long-term memory semantic search (see `app/models/models.py`).
- **LangGraph & LangChain**: Orchestrates the ReAct agent loops, binding tools, and executing the "Think-Plan-Tool-Speak" protocol (see `app/agents/graph.py`).
- **Google GenAI / OpenRouter**: The LLM providers (using Gemma 4 26B/31B models).
- **Redis**: Fast active working memory (50 turns), Mutex locks for background summarization, and ARQ queue.
- **ARQ**: Async task queue for processing Telegram webhooks outside the request cycle (see `app/worker.py`).
- **APScheduler**: Manages chron jobs for morning/evening nudges and midnight PDF reports (see `app/scheduler.py`).
- **FPDF2 & Matplotlib**: Generates the midnight analytics PDF with bar charts.
- **Argon2-cffi**: Hashing admin invite tokens.
- **Docker & Caddy**: Containerization and reverse proxy with automatic SSL (Let's Encrypt).
- **Langfuse**: Tracing and observability for LLM calls.

## 5. Architecture & Design Decisions
- **Decoupled 4-Tier Cognitive Memory System**: 
  - *What was decided*: Split memory into Working (Redis, 50 turns), Narrative Summary (<500 words rolling), Permanent Facts (PGVector), and Historical Archive (Hybrid RAG).
  - *Alternative*: Stuffing everything into the LLM context window, or just using a basic vector database RAG.
  - *Evidence*: `README.md` and `app/services/cognitive_service.py`. This was likely chosen to prevent API costs from blowing up while retaining deep context and avoiding "amnesia."
- **ReAct Agent Pattern instead of Static Handlers**: 
  - *What was decided*: Used LangGraph to let the LLM autonomously decide when to call tools (e.g., `query_analytics`, `search_past_conversations`) instead of using rigid `/slash` commands.
  - *Alternative*: Standard Telegram bot with hardcoded regex or command matching.
  - *Evidence*: `app/agents/graph.py` shows a full state machine.
- **Cross-User Anti-Cheat with Canonical Signatures and Vectors**: 
  - *What was decided*: Check both status bar device metadata (time + battery) as nonces AND cosine distance of image vectors, globally across all users within 24 hours.
  - *Alternative*: Relying only on raw image hashing, which breaks if the image is slightly cropped.
  - *Evidence*: `app/services/fraud_service.py` functions like `compute_canonical_content_signature` and `check_visual_duplicate`.
- **Out-of-band Webhook Processing (ARQ)**: 
  - *What was decided*: Offload Telegram webhook processing to a background worker (`app/worker.py` using `arq`) so the FastAPI endpoint can respond 200 OK instantly.
  - *Alternative*: Processing the LLM response inline, risking Telegram timeout retries.

## 6. The Hardest Problem
**Asynchronous Data Safety During Memory Consolidation**
- *What made it hard*: When a user exceeds the 50-turn sliding window, the overflow is sent to a background worker (`app/services/cognitive_service.py`) to summarize and extract facts using a slow LLM call. If the user sends *new* messages while the LLM is thinking, a naive cache clear would delete the newly arrived messages.
- *How it was solved*: A Redis Mutex lock (`cognitive_lock:{telegram_id}`) prevents concurrent summary runs. To clear the buffer safely, instead of using `DEL`, the service uses `redis_client.ltrim(overflow_key, len(evicted_messages), -1)`. This precisely slices off *only* the specific number of messages processed in that batch from the front of the list, preserving any new messages appended to the tail during the LLM call.
- *Naive solution*: `await redis_client.delete(overflow_key)`, which would result in race conditions and data loss.

## 7. Non-Obvious or Clever Bits
- **UUID Hallucination Fallback**: In `app/services/cognitive_service.py`, the LLM is tasked with extracting facts and updating them using a structured JSON schema. If it outputs `action="UPDATE"` but hallucinates an invalid or non-existent UUID for `target_existing_fact_id`, the system catches the `ValueError` or empty rowcount and gracefully falls back to inserting it as a *new* fact (`CREATE`). This cleverly prevents data loss from LLM hallucinations.
- **Reciprocal Rank Fusion (RRF) for Past Conversations**: In `app/agents/tools.py`, `search_past_conversations` executes a single raw SQL query combining dense cosine vector distance and sparse full-text search (`ts_rank` over `search_tsvector`) to retrieve historical context. This mathematically combines the strengths of both search types.

## 8. What Doesn't Work / Known Limitations
- **Anti-Cheat Bypass via Cropping**: The system relies heavily on device metadata (status bar) as a nonce. If the metadata is missing or degenerate (e.g., 'N/A' or 'None'), the system skips the metadata check entirely to guarantee zero false positives (see `app/services/fraud_service.py` line 238). This means a malicious user could intentionally crop out their status bar to bypass the strongest layer of fraud protection. The fallback (visual similarity) is scoped specifically to identical scores to avoid false positives between two genuine 10/10 submissions, meaning someone with a different score could potentially evade detection if cropped.

## 9. Evolution / Timeline
Based on `git log`, this project was built in a massive burst over just 3 days (April 22-24, 2026).
- The very first commit was a massive dump of the database models and initial schemas.
- A huge pivot/refactor occurred in commit `c12137bdeefc` on April 24, where the author added the LangGraph infrastructure, the 4-tier hybrid memory, and the autonomous reporting pipeline (+1529 lines). This indicates they moved from a simpler scripted concept to a full ReAct agent very quickly.

## 10. Results / Evidence It Works
- There is a rich suite of tests specifically targeting the fraud service (`tests/test_fraud_service.py`, `tests/test_challenger_m2_dedup.py`). The sizes of these files (up to 24KB) suggest the anti-cheat logic is highly tested and hardened.
- The `README.md` explicitly links to a live Telegram bot (`@MightyStormBot`).
- GitHub Actions deployment pipelines (`deploy.yml`) are configured, and a production `docker-compose.prod.yml` using Caddy indicates it runs in a real environment.

## 11. How This Compares
Instead of utilizing standard OCR APIs (like Tesseract or Google Cloud Vision) or rigid regex bots to extract metrics, it utilizes a multimodal LLM (Gemma 4 via OpenRouter) to both converse and extract metrics from images natively in a single ReAct loop. This is heavier but allows for natural language interaction in the same flow as grading.

## 12. Codebase Vitals
- **Rough Size**: ~2000-3000 Lines of Code. ~35 Python files.
- **Primary Language**: 100% Python.
- **Contributors**: 1 (Israel Ayeni / saxrael).
- **Test-to-Code Ratio**: Strong specifically for the `fraud_service` logic (4 large test files), though less evident for UI/Telegram interactions.
- **Overall Maturity**: Actively maintained prototype currently deployed to production.

## 13. Glossary
- **ReAct**: Reason + Act. An agentic design pattern where the AI thinks out loud before executing tools.
- **RRF (Reciprocal Rank Fusion)**: An algorithm that combines the scores of multiple search methods (e.g., dense vector search and sparse keyword search) to produce a unified ranking.
- **Nonce**: A unique, one-time value. In this project, device metadata (status bar time + battery) acts as a nonce to prove screenshot uniqueness.
- **FCS ABU**: Fellowship of Christian Students at Ahmadu Bello University (Zaria, Nigeria) — the community this was built for.
- **TonedEar**: An ear-training application that users screenshot for their submissions.

## 14. OPEN QUESTIONS FOR THE AUTHOR
- **Personal Motivation**: Why did you start this? Are you a member or administrator of Mighty Storm? Was this born out of your own frustration tracking assignments manually?
- **Impact & Usage**: How many users are actually actively submitting assignments through `@MightyStormBot` right now? Did it save the admins time?
- **Design Choices**: Why use a heavy ReAct LangGraph setup for something that is essentially an image upload + OCR + stats dashboard? Was it specifically to provide conversational mentorship, or was the agent architecture an experiment?
- **Cost**: How much does it cost to run the 31B Gemma models for summarizing every 50 turns?
- **Timeline**: The git history suggests a 3-day sprint. Were you building this locally for weeks prior, or was this genuinely built from scratch over a weekend?
