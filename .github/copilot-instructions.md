# xdBot

Read `AGENTS.md` for repository instructions and `README.md` for commands and deployment.

- Use `commands.hybrid_command` for commands that support prefix and slash forms.
- Keep permission checks on both command forms. Use private responses for word statistics.
- Use the shared database handler. Keep database transactions short. Use a temporary database for tests.
- Read secrets and settings from `config.settings`. Keep secret values out of responses and logs.
- Keep live Discord and provider calls out of the default tests.
