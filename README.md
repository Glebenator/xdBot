# xdBot

A modular Discord bot built on top of `discord.py` featuring asynchronous data storage, hybrid command support, Random.org-powered fun commands, and optional LLM integrations.

## ✨ Highlights

- Fully async persistence layer backed by `aiosqlite` with multi-guild awareness
- Hybrid (prefix + slash) commands with automatic ephemeral handling
- Configurable Random.org integration with secure local fallback
- Optional Ollama or OpenRouter-powered LLM responses with chat history management and web search via Tavily
- Modular cog structure for admin, moderation, fun, image, and voice features

## 📦 Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`
- Discord bot token with the necessary intents
- (Optional) Random.org API key for true randomness
- (Optional) Ollama endpoint for local LLM features
- (Optional) OpenRouter API key for hosted LLM access
- (Optional) Tavily API key for LLM web search capabilities

## ⚙️ Configuration

Configuration is centralised in `config.py` and automatically populated from environment variables (including values in `.env` files). The most relevant keys are:

```
DISCORD_TOKEN=your_discord_token
BOT_PREFIX=!
OWNER_IDS=123456789012345678,987654321098765432
GUILD_ID=123456789012345678
RANDOM_ORG_KEY=your_random_org_key_optional
OLLAMA_URL=http://localhost:11434
OPENROUTER_API_KEY=your_openrouter_key_optional
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL=https://your.site (needed only if OpenRouter requires a referrer)
OPENROUTER_APP_NAME=xdBot
OPENROUTER_DEFAULT_MODEL=anthropic/claude-3-haiku (optional preset)
TAVILY_API_KEY=your_tavily_key_optional
```

- `BOT_PREFIX` defaults to `!`.
- `OWNER_IDS` accepts a comma-separated list of user IDs.
- `RANDOM_ORG_KEY` is optional; when omitted, the bot falls back to secure local randomness and lets users know.
- `OLLAMA_URL` default is `http://192.168.50.69:11434` but can be overridden.
- `OPENROUTER_API_KEY` enables hosted models. When omitted, OpenRouter-backed configs are ignored.
- `OPENROUTER_SITE_URL` and `OPENROUTER_APP_NAME` are forwarded to OpenRouter headers for attribution.
- `OPENROUTER_DEFAULT_MODEL` lets the LLM cog auto-register an OpenRouter chat model without manual edits.
- `TAVILY_API_KEY` enables web search capabilities for LLMs. When provided, models can automatically search the web for current information. See `TAVILY_SEARCH_INTEGRATION.md` for details.

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
- `llm`: chat and mention responses via configurable Ollama/OpenRouter models with conversation tracking and web search tool integration; includes admin utilities `/llm_set_model` and `/llm_current_model` to manage the active chat provider
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
