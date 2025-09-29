# xdBot

A modular Discord bot built on top of `discord.py` featuring asynchronous data storage, hybrid command support, Random.org-powered fun commands, and optional LLM integrations.

## ✨ Highlights

- Fully async persistence layer backed by `aiosqlite` with multi-guild awareness
- Hybrid (prefix + slash) commands with automatic ephemeral handling
- Configurable Random.org integration with secure local fallback
- Optional Ollama-powered LLM responses with chat history management
- Modular cog structure for admin, moderation, fun, image, and voice features

## 📦 Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`
- Discord bot token with the necessary intents
- (Optional) Random.org API key for true randomness
- (Optional) Ollama endpoint for LLM features

## ⚙️ Configuration

Configuration is centralised in `config.py` and automatically populated from environment variables (including values in `.env` files). The most relevant keys are:

```
DISCORD_TOKEN=your_discord_token
BOT_PREFIX=!
OWNER_IDS=123456789012345678,987654321098765432
GUILD_ID=123456789012345678
RANDOM_ORG_KEY=your_random_org_key_optional
OLLAMA_URL=http://localhost:11434
```

- `BOT_PREFIX` defaults to `!`.
- `OWNER_IDS` accepts a comma-separated list of user IDs.
- `RANDOM_ORG_KEY` is optional; when omitted, the bot falls back to secure local randomness and lets users know.
- `OLLAMA_URL` default is `http://192.168.50.69:11434` but can be overridden.

All values are accessible through `config.settings` for consistent use across the code base.

## 🚀 Getting Started

```bash
git clone <repository-url>
cd xdBot
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # create and update if example is provided
python main.py
```

If `.env.example` is not available, create a `.env` file manually and use the configuration keys listed above.

## 🧠 Key Cogs

- `admin`: owner/admin utilities for streaks, points, and cog management
- `fun`: Random.org rolls, success streak tracking, and leaderboards
- `moderation`: bad-word tracking, stats, and leaderboards
- `llm`: chat and mention responses via Ollama models
- `image`, `general`, `voice`: assorted utility features (see code for details)

## 🛡️ Data Layer

- Async `DatabaseHandler` backed by `aiosqlite`
- Automatic schema migrations to multi-guild tables
- Helper methods covering success stats, streaks, cooldowns, prompts, and word usage

## 🔄 Development Tips

- Use `python -m compileall .` to run fast syntax checks (no network/API calls)
- Reload individual cogs with `!reload <cog>` during testing (owner-only)
- The bot gracefully handles SIGINT/SIGTERM thanks to the shutdown routine in `main.py`

## 🤖 Randomness & Fallbacks

- When `RANDOM_ORG_KEY` is configured, the bot uses true randomness via Random.org
- Without the key, it transparently falls back to `secrets.randbelow`, notifying users that true randomness is temporarily unavailable

## 📚 License

See `LICENSE` (if provided) or add one to document your usage terms.
