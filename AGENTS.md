# xdBot repository guide

Use Python 3.11. Read `README.md` for the commands and Linux deployment procedure.

- `main.py` starts the bot and loads cogs with an asynchronous `setup` function.
- `config.py` loads settings. Get runtime settings from `config.settings`.
- `utils/db_handler.py` manages SQLite. Start a transaction before a change that must succeed as a unit. Test changes with a temporary database and existing data.
- Keep the prefix and slash forms of the retained commands. Use `defer_hybrid` for work that can exceed the Discord response deadline.
- Use the server ID for bot data that belongs to a server. Keep message quotes in their source channel or thread.
- `cogs/music.py` runs one playback worker per server. `utils/voice_handler.py` resolves YouTube tracks and creates audio sources.
- `main.py --check` loads all cogs offline. Run it with `python -m ruff check .` and `python -m pytest` before a release.
- `.github/workflows/ci.yml` tests changes and publishes a tested image after a push to `botv2`. `deploy/` contains the Linux update service and timer.
