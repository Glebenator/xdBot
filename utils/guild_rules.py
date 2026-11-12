"""Read legacy rules and save edits for each server."""

import asyncio
import json
from pathlib import Path
from typing import Any

from config import settings
from utils.db_handler import DatabaseHandler


def read_rule_defaults(filename: str, fallback=None):
    source = settings.data_dir / filename
    if not source.is_file() and fallback is not None:
        source = fallback
    try:
        return json.loads(Path(source).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None


class GuildRules:
    def __init__(self, db: DatabaseHandler, kind: str, defaults: dict[str, Any]):
        self.db = db
        self.kind = kind
        self.defaults = defaults
        self.cache: dict[int, dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def _load(self, guild_id: int) -> dict[str, Any]:
        if guild_id not in self.cache:
            saved = await self.db.get_rule_set(guild_id, self.kind)
            self.cache[guild_id] = self.defaults if saved is None else saved
        return self.cache[guild_id]

    async def get(self, guild_id: int) -> dict[str, Any]:
        if guild_id in self.cache:
            return self.cache[guild_id]
        async with self.lock:
            return await self._load(guild_id)

    async def set(self, guild_id: int, trigger: str, value: Any) -> bool:
        async with self.lock:
            rules = (await self._load(guild_id)).copy()
            if value is None:
                if trigger not in rules:
                    return False
                del rules[trigger]
            elif trigger in rules and rules[trigger] == value:
                return False
            else:
                rules[trigger] = value
            await self.db.save_rule_set(guild_id, self.kind, rules)
            self.cache[guild_id] = rules
            return True
