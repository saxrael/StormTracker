# StormTracker 🌩️

StormTracker is a Telegram-native, AI-powered assistant designed to automate the tracking, grading, and reporting of daily ear-training assignments for music groups.

> **Origins**: This project was originally built for **Mighty Storm**, a dedicated music group within the **Fellowship of Christian Students (FCS) at Ahmadu Bello University (ABU), Samaru, Zaria, Kaduna State, Nigeria**, to help members stay accountable in their daily musical development.

---

## 🌟 Part 1: User-Friendly Overview

### What is StormTracker?

Tracking daily submissions via direct messaging creates a cluttered inbox, wastes hours of manual logging, and provides zero actionable analytics. StormTracker solves this by acting as your autonomous group manager. 

Instead of dealing with spreadsheets or manual checklists, users simply send screenshots of their daily exercises to the bot. StormTracker instantly reads the images, understands the exercise types, extracts the exact metrics, and logs them. 

### Not Just a Bot, but a True AI Agent
StormTracker is not a rigid, amnesiac script. It is built as a **ReAct (Reason + Act) AI Agent**, meaning it behaves like a human manager:
- **It Remembers You**: It maintains an ongoing understanding of your past conversations and tracks your performance over time. 
- **It Thinks Before Acting**: When you ask a question, it pauses to *reason* about what you need, decides whether to check the database or just chat naturally, and then responds.
- **It Takes Initiative**: It doesn't just wait for you to text it. It manages its own schedule to ensure everyone stays on track.

### 🎯 Key Benefits & Features

*   **Effortless Image Processing**: Send a screenshot of your daily exercise (e.g., from TonedEar). The AI instantly reads the image, grades it, and logs your score.
*   **Proactive Reminders (Nudges)**: If you forget to submit your assignment, the bot will send you friendly direct messages at 9:00 AM and 8:00 PM to keep you accountable.
*   **Zero Cheating**: Trying to send the same screenshot twice? The system instantly recognizes duplicate images and rejects them, ensuring complete fairness across the group.
*   **Automated PDF Reports**: At midnight, StormTracker generates a beautiful, detailed PDF report containing group averages, visual bar charts, and a list of missing submissions, delivering it directly to administrators.
*   **Chat with your Data**: Ask naturally, *"How is John doing on Chords this week?"* or *"What is my average score?"*, and the AI will analyze the data and provide instant answers.

---

## ⚙️ Part 2: Technical Architecture & Innovations

This section details the advanced engineering, security layers, and architectural patterns that power StormTracker for developers and system administrators.

### Core Intelligence & Routing
StormTracker is driven by a hybrid intelligence model:
- **Primary Engine**: The core conversational and analytical tasks are powered by `Gemma 4 31B`, ensuring fast and highly capable intent recognition and tool execution.
- **Dynamic Routing & Reasoning**: The system leverages an OpenRouter integration to dynamically route complex background tasks (such as cognitive fact extraction and long-term memory synthesis) to specialized reasoning models. 

### Advanced Prompt Engineering & Agent Control
StormTracker utilizes a Tier-1 production-grade system prompt designed to tightly control the ReAct Agent's autonomous behavior:
- **Negative Prompting (Behavioral Fences)**: Explicit constraints prevent the classic "overly-hyped chatbot" syndrome, forcing the agent to act as a strict, professional musical mentor.
- **Cognitive Memory Protocols**: Strict logical boundaries separate the use of qualitative contextual memory (RAG) from quantitative data fetching (Database Analytics), completely eliminating data hallucination.
- **Immutable RBAC**: Role-Based Access Control is hardcoded directly into the prompt via Markdown tables, which the LLM parses natively to prevent privilege escalation attacks.
- **Recency Bias Optimization**: Highly dynamic data arrays (like active memory facts and system status) are injected at the absolute bottom of the prompt to maximize the LLM's attention mechanism right before token generation.

### Cognitive Memory Efficiency (5-Tier Architecture)
To support continuous context without amnesia while keeping API costs low, the system utilizes a highly optimized **5-Tier Memory Architecture** distributed across Redis and PostgreSQL:

1. **Short-Term Working Memory (Redis)**: The most recent 20 messages are instantly loaded into the LLM's context window for immediate conversational awareness.
2. **Overflow Buffer (Redis)**: As conversations grow, older messages are evicted from working memory and staged in a temporary buffer. 
3. **Rolling Summarization (Redis)**: Once the buffer hits 20 messages, a background reasoning model condenses them into a dense, chronological summary (< 200 words). This summary stays in the LLM context, providing medium-term awareness without ballooning token counts.
4. **Semantic Fact Database (Memory RAG Pipeline)**: The system utilizes a continuous **Retrieval-Augmented Generation (RAG)** pipeline for long-term memory. It automatically extracts permanent, high-value facts (e.g., names, specific music goals, preferences) from the background buffer. These facts are converted to vector embeddings and dynamically injected into the agent's prompt via Cosine Similarity *before* the AI processes the user's message, ensuring deep context without bloated token counts.
5. **Immutable Audit Log (PostgreSQL)**: Every raw message is permanently stored in a relational database for administrative analytics and historical fallback.

### Robust Vision Accessibility & Multimodality
The ingress layer is built to handle the chaotic nature of real-world file uploads safely:
- **Document Safety Gates**: The webhook gracefully processes both compressed photos and raw document uploads, enforcing a strict **5MB payload limit** to prevent memory exhaustion.
- **Payload Normalization**: Advanced content normalization ensures stable multimodal interactions with OpenRouter schemas, preventing TypeErrors and crashes during complex image processing.

### Security & Anti-Fraud
Ensuring data integrity is paramount, especially when grading group assignments:
- **Cosine Distance Vector Comparisons**: The cryptographic anti-fraud system converts every uploaded image into a mathematical vector embedding. It uses Cosine Distance to compare incoming vectors against past submissions, instantly catching visual duplicates even if the image metadata was altered.
- **Prompt Isolation**: Background memory synthesis tasks are hardened against prompt injection attacks using strict **XML-based prompt isolation**.
- **Safe Rich-Text Egress**: A dedicated **Markdown-to-HTML Translation Layer** sanitizes and formats all outgoing messages. This ensures that dynamic code blocks, links, and bold text never cause Telegram API parsing crashes.

### Advanced Resilience & Scheduling
StormTracker operates independently and must be fault-tolerant:
- **Out-of-Band Memory Synchronization**: When the bot sends automated nudges, these actions are injected out-of-band directly into the persistent conversation timeline. The AI agent retains full context of its own automated reminders.
- **Fault-Tolerant Async Scheduler**: Proactive tasks are driven by APScheduler, utilizing Redis-backed locking to ensure background jobs (like midnight reports) execute flawlessly even in multi-instance or crashing scenarios.
- **Exponential Backoff**: Critical external API calls (e.g., OpenRouter embeddings) are protected by `tenacity` retry logic with exponential backoff to gracefully handle HTTP 429 rate limits.

### Observability & Tracing
- **Langfuse Integration**: The complex graph of asynchronous reasoning, tool execution, and background memory synthesis is continuously traced using Langfuse, providing deep observability into the ReAct agent's decision-making pathways and token usage.

### 🚀 Getting Started (Self-Hosting)

StormTracker is designed for lean, single-node deployments using Docker.

#### Prerequisites
*   A Telegram Bot Token (via [@BotFather](https://t.me/botfather))
*   API Keys for Google AI Studio (Gemma 4), OpenRouter (Nemotron Embeddings, Reasoning Models), and Langfuse (optional).
*   Docker & Docker Compose installed on your host machine.

#### Quick Start
1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/stormtracker.git
   cd stormtracker
   ```
2. **Configure your environment:**
   Copy `.env.example` to `.env` and fill in your required API keys and Domain Name.
3. **Deploy:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
   *Note: The production compose file utilizes Caddy to automatically provision and renew Let's Encrypt SSL certificates required for Telegram Webhooks.*

#### Security & Access Control
- **Role-Based Access**: Standard users can only query their own data. Admin tools (like generating group reports and cross-user analytics) are locked down.
- **Bootstrapping**: The first admin is created using a one-time, secure `ROOT_CLAIM_TOKEN` injected during deployment. Once claimed, admins can dynamically generate single-use invite passkeys for other staff.
