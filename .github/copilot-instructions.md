# Copilot Instructions for xdBot

## Architecture snapshot
- Entry point `main.py` constructs `DiscordBot`, configures intents, and autodiscovers every module under `cogs/` via `load_extensions`; add new features as `cogs/<name>.py` with an `async def setup(bot)` (modules without a `setup` coroutine are skipped).
- Runtime configuration lives in `config.settings`; always read tokens, prefixes, and URLs from there instead of `os.environ`.
- Persistence goes through `utils/db_handler.py`; grab the shared instance through `get_database_handler()` so schema bootstrapping and migrations in `data/bot.db` stay centralised.

## Command patterns
- Commands are predominantly `@commands.hybrid_command`, enabling both prefix and slash usage—follow the examples in `cogs/fun.py` or `cogs/moderation.py` and call `await defer_hybrid(ctx, ...)` (from `utils.helpers`) when the handler can take time or should be ephemeral, instead of touching `ctx.defer()` directly.
- Reuse `utils.helpers.send_hybrid_message` for responses that should be ephemeral when invoked as slash commands and `create_embed` for consistent embed styling.
- Owner/admin checks rely on decorators (`@commands.is_owner`, `@commands.has_permissions`) and the helper `_require_guild(ctx)` to guard DM contexts; match that pattern when adding privileged commands.
- When commands rely on uploaded files, read attachments from both `ctx.interaction.attachments` and `ctx.message.attachments` so hybrid usage works in either mode.
- For long-running background work (LLM calls, heavy processing) follow the task pattern in `cogs/llm.py` to avoid blocking listeners.

## Persistence & cooldown conventions
- Before recording stats, call `DatabaseHandler.update_user(guild_id, user_id, display_name)` so usernames stay current.
- Daily success flow (`cogs/fun.py`) uses `log_command_usage`, `add_total_success`, `update_success_streak`, `update_command_cooldown`, and `record_command_execution`; when adding related mechanics, reuse those helpers and keep the `'успех'` command name consistent so queries resolve.
- Word tracking (`cogs/moderation.py`, `utils/word_filter.py`) stores per-guild counts and hides sensitive terms with spoiler formatting—extend from these utilities rather than touching JSON/SQL directly.

## External integrations
- Random.org access is wrapped by `utils.rng.RandomOrgRNG`; always request numbers through it so the fallback to `secrets.randbelow` and quota tracking remains intact.
- LLM features (`cogs/llm.py`) call `utils.ollama_handler.OllamaHandler.generate_response`, which manages per-user history, retries, and metrics—register new models with `ModelConfig` and respect the chunked messaging helpers when formatting large replies.
- Image transformations (`cogs/image.py`) depend on OpenCV + MediaPipe; keep heavy processing inside `await ctx.defer()` blocks and clean up temp files after sending results.

## Developer workflows & ops
- Local run: create a virtualenv, `pip install -r requirements.txt`, set secrets in `.env`, then launch with `python main.py`; Docker users can run `docker-compose up --build` which mirrors that setup.
- Use `python -m compileall .` for fast syntax validation and the owner-only in-chat commands `!reload <cog>` / `!sync` (see `cogs/admin.py`) to iterate without restarting the bot.
- Slash-command registration happens in `DiscordBot.setup_hook` via `self.tree.sync()`, so expect a sync on startup; manual resync is rarely needed unless commands were added or permissions changed.
- Adopt the shared logging approach: `main.py` configures structured output, so new modules should declare `logger = logging.getLogger(__name__)` and avoid `print` in favour of structured log calls with useful context.

## Data & housekeeping
- Persisted files live in `data/` (`bot.db`, `bad_words.json`, `replies.json`); treat them as runtime state and avoid hardcoding absolute paths when extending functionality.
- Each cog that opens external resources (e.g., `RandomOrgRNG`, MediaPipe) defines a cleanup method (`cog_unload`, `.close()`); ensure new long-lived clients are closed the same way to prevent resource leaks.
