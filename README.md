# xdBot

A modular Discord bot built on discord.py: LLM chat with web search and tool calling, stock quotes,
charts and indicators, music playback, a quote hall, auto-replies, word tracking, and a few games.
Each feature is a cog in `cogs/`, and every command works both as a slash command and with the `!` prefix.

## Features

| Area | What it does | Needs |
|---|---|---|
| LLM chat | `/chat` answers with a local Ollama model or an OpenRouter model, keeps per-user history, and can call tools: web search and live stock data. Mentioning the bot gets a shorter, more casual reply. | Ollama or OpenRouter |
| Web search | A tool the chat model can call. SearXNG first, Tavily as the fallback. | SearXNG or Tavily |
| Stocks | Quotes, company info, news, dividends, splits, market status, candlestick, line and area charts, comparisons, and RSI, SMA, EMA, MACD and golden-cross signals. | Polygon.io key |
| Music | Plays YouTube audio in a voice channel with a queue, pause, skip and volume. | FFmpeg |
| Quote hall | Saves messages as quotes and shows random, per-user and recent ones. | |
| Auto-replies | Replies with text and reactions when a message contains a trigger phrase. | |
| Word tracking | Counts tracked words per user, with stats and a leaderboard. | |
| Image | `/deamonify` finds the eyes in an attached photo and makes them glow. | MediaPipe (installed) |
| Games | A daily "success" roll from Random.org with streaks and a leaderboard, and `/roll`. | Random.org key (optional) |

## Requirements

- Python 3.11. The pinned MediaPipe release has no wheels for newer Pythons.
- FFmpeg on the `PATH`, for music.
- A Discord application with a bot token. In the Developer Portal, turn on the **Message Content** and
  **Server Members** privileged intents. Invite the bot with the `bot` and `applications.commands` scopes.

## Run it locally

```bash
git clone https://github.com/Glebenator/xdBot.git
cd xdBot
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in DISCORD_TOKEN and any optional keys
python main.py
```

The bot creates `data/bot.db` (SQLite) on first start and syncs its slash commands globally, which can
take a few minutes to show up in Discord.

## Run it with Docker

```bash
cp .env.example .env               # fill it in
docker compose up -d --build
```

- Compose passes `.env` to the container as environment variables. The image never contains it.
- Only `./data` is mounted, so the database, replies and word filter survive rebuilds.
- The container runs as an unprivileged user with UID and GID 1000. If `./data` on the host belongs to
  another user, build with `docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g)`.
- Inside the container, `localhost` is the container itself. For Ollama or SearXNG on the Docker host, use
  `http://host.docker.internal:11434` and `http://host.docker.internal:8888`.

CI publishes an image to Docker Hub after the tests pass on the default branch.

## Configuration

All settings are environment variables, read from `.env` by `config.py`. Only `DISCORD_TOKEN` is required.

| Variable | Default | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | | Bot token from the Developer Portal |
| `BOT_PREFIX` | `!` | Prefix for text commands. Mentioning the bot also works as a prefix. |
| `OWNER_IDS` | the application owner | Comma-separated user IDs allowed to run `!reload` and `!sync` |
| `GUILD_ID` | | Read into the settings but not used yet |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_CHAT_MODEL` | `qwen3:4b` | Model for `/chat`; it must support tool calling for search and stocks |
| `OLLAMA_MENTION_MODEL` | the chat model | Model for replies to @mentions, such as a custom persona built from a Modelfile |
| `OPENROUTER_API_KEY` | | Enables OpenRouter models |
| `OPENROUTER_DEFAULT_MODEL` | | Registers an OpenRouter model that `/llm_set_model` can choose |
| `OPENROUTER_BASE_URL`, `OPENROUTER_SITE_URL`, `OPENROUTER_APP_NAME` | OpenRouter API, none, `xdBot` | Sent to OpenRouter with each request |
| `SEARXNG_URL` | `http://localhost:8888` | SearXNG instance with the JSON format enabled |
| `TAVILY_API_KEY` | | Search fallback when SearXNG is unavailable |
| `POLYGON_API_KEY` | | Stock commands and the chat model's stock tools |
| `RANDOM_ORG_KEY` | | True randomness for `/успех` and `/roll` |
| `MUSIC_MAX_QUEUE_SIZE`, `MUSIC_IDLE_TIMEOUT`, `MUSIC_DEFAULT_VOLUME`, `MUSIC_MAX_DURATION` | `100`, `300` s, `0.5`, `3600` s | Music limits |
| `LLM_LOG_LEVEL` | `INFO` | Log level for LLM and search calls |

## Commands

Every command is a slash command and a prefix command, except `!reload` and `!sync`.
Commands marked **admin** need the Administrator permission, and **mod** needs Manage Messages.

**General:** `help`, `ping`

**LLM:** `chat`, `clear_chat`, `show_history`, `llm_current_model`, `llm_set_model` (admin), `model_stats` (admin)

**Stocks:** `stock` (also `stockquote`, `price`), `stockinfo`, `stocksearch`, `marketstatus`, `stocknews`,
`stockdividends`, `stocksplits`, `stockchart ticker days chart_type`, `stockcompare`, `stockrsi`, `stocksma`,
`stockema`, `stockmacd`, `goldencross`

**Music:** `join`, `play`, `pause`, `resume`, `skip`, `stop`, `volume`, `leave` (also `disconnect`, `dc`)

**Quote hall:** `quote`, `quote add`, `quote random`, `quote user`, `quote list`, `quote delete`

**Auto-replies:** `listreplies`, `addreply` (mod), `addreaction` (mod), `removereply` (mod)

**Word tracking:** `addword`, `removeword`, `wordstats`, `wordleaderboard` (all mod)

**Games:** `успех`, `успехстат`, `топ`, `roll`, `огурчик`, `увлажнение`, `logitech`, `razer`

**Image:** `deamonify` (attach a photo)

**Points (admin):** `setpoints`, `addpoints`, `removepoints`, `setstreak`, `resetstats`

**Owner:** `!reload <cog>`, `!sync`

## How it fits together

- `main.py` starts the bot, turns on the intents, and loads every module in `cogs/` that defines
  `async def setup`.
- `config.py` reads the environment once into a `Settings` object.
- `utils/` holds the shared parts: the SQLite layer (`db_handler.py`), the LLM handler with Ollama and
  OpenRouter providers and tool calling (`ollama_handler.py`), search (`search_tool.py`), the Polygon client,
  charts and indicators, and the voice and queue handling for music.
- `data/` holds runtime state: `bot.db`, `replies.json` and `bad_words.json`.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
make check        # compile, ruff, pytest
```

Tests that call external services are marked `integration` and are skipped by default;
run them with `pytest -m integration`. CI runs the same checks on every push and pull request.

Dependencies are pinned to versions that pass the suite. Raise them on purpose and run `make check`:
a MediaPipe patch release once removed the face-mesh API that `cogs/image.py` uses. discord.py is
installed with its `voice` extra, which brings PyNaCl and `davey`; without `davey`, voice and music are off.
