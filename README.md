# StormTracker 🌩️

StormTracker is a Telegram-native, AI-powered assistant designed to automate the tracking, grading, and reporting of daily ear-training assignments for music groups.

Tracking daily submissions via direct messaging creates a cluttered inbox, wastes hours of manual logging, and provides zero analytics. StormTracker solves this by acting as an autonomous group manager. It collects screenshots, reads the scores using multimodal AI, prevents cheating, and delivers proactive reminders and beautiful PDF reports.

## ✨ Core Features

*   **🤖 AI Image Processing:** Users simply send a screenshot of their daily exercise (e.g., from TonedEar). StormTracker's AI reads the image, understands the exercise type, and extracts the exact metrics automatically.
*   **🛡️ Cryptographic Anti-Fraud:** To prevent users from submitting the same screenshot twice, the system converts every image into a mathematical vector and checks the phone's battery/timestamp metadata. Duplicate images are instantly rejected.
*   **⏰ Proactive Nudges:** StormTracker manages its own time. If a user hasn't submitted their assignment, the bot sends them a friendly direct message at 9:00 AM and 8:00 PM.
*   **📊 Automated PDF Reporting:** At midnight, the system generates a detailed PDF report containing group averages, visual bar charts, and a list of missing submissions, delivering it directly to all group administrators.
*   **🧠 On-Demand Analytics:** Admins and users can chat with the bot naturally. Ask, *"How is John doing on Chords this week?"* or *"What is my average score?"*, and the AI will query the database to provide instant, synthesized answers.

## ⚙️ How It Works

StormTracker operates using a state-of-the-art **ReAct (Reason + Act) Agent** architecture, ensuring it behaves like a human manager rather than a rigid script.

1.  **Ingress:** Users interact via Telegram. The bot ensures users are securely onboarded with their real names.
2.  **The Brain:** Powered by `Gemma 4 31B`, the agent analyzes intents. It decides whether to extract metrics, run a database query, or just have a helpful conversation.
3.  **Hybrid Memory:** The system remembers you. It utilizes a 5-Tier memory architecture (Redis + PostgreSQL) to maintain conversation history, summarize past interactions, and remember permanent facts.
4.  **Zero-Disk Operations:** Images are never saved permanently. They are processed entirely in RAM, ensuring maximum privacy and server efficiency.

## 🚀 Getting Started (Self-Hosting)

StormTracker is designed for lean, single-node deployments using Docker. 

### Prerequisites
*   A Telegram Bot Token (via [@BotFather](https://t.me/botfather))
*   API Keys for Google AI Studio (Gemma 4) and OpenRouter (Nemotron Embeddings)
*   Docker & Docker Compose installed on your host machine.

### Quick Start
1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/stormtracker.git
   cd stormtracker
2. **Configure your environment:**
Copy .env.example to .env and fill in your API keys and Domain Name.
3. **Deploy:**
docker compose -f docker-compose.prod.yml up -d --build
Note: The production compose file utilizes Caddy to automatically provision and renew Let's Encrypt SSL certificates required for Telegram Webhooks.

## 🔒 Security & Access
1. **Role-Based Access:** Standard users can only query their own data. Admin tools (like group reports and cross-user analytics) are cryptographically locked.
2. **Bootstrapping:** The first admin is created using a one-time, secure ROOT_CLAIM_TOKEN injected during deployment. Once claimed, admins can dynamically generate single-use invite passkeys for other staff.
