"""Centralised application configuration.

This module exposes a `settings` instance that gathers configuration from
environment variables (with sensible defaults) so that the rest of the code
base does not need to touch `os.environ` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import os

try:  # Ensure .env files are loaded before reading environment variables
	from dotenv import load_dotenv

	load_dotenv()  # type: ignore[no-untyped-call]
except Exception:  # pragma: no cover - dotenv is optional at runtime
	pass


DEFAULT_PREFIX = "!"
DEFAULT_OWNER_IDS: List[int] = []
DEFAULT_GUILD_ID: Optional[int] = None
DEFAULT_OLLAMA_URL = "http://192.168.50.69:11434"


def _parse_int(value: Optional[str]) -> Optional[int]:
	if value is None or not value.strip():
		return None
	try:
		return int(value.strip())
	except ValueError:
		return None


def _parse_owner_ids(value: Optional[str]) -> List[int]:
	if not value:
		return []
	owners: List[int] = []
	for piece in value.split(","):
		piece = piece.strip()
		if not piece:
			continue
		try:
			owners.append(int(piece))
		except ValueError:
			continue
	return owners


@dataclass(slots=True)
class Settings:
	"""Runtime configuration container."""

	prefix: str = DEFAULT_PREFIX
	owner_ids: List[int] = field(default_factory=list)
	guild_id: Optional[int] = DEFAULT_GUILD_ID
	discord_token: Optional[str] = None
	random_org_api_key: Optional[str] = None
	ollama_url: str = DEFAULT_OLLAMA_URL

	@property
	def random_org_enabled(self) -> bool:
		return bool(self.random_org_api_key)

	@property
	def has_discord_token(self) -> bool:
		return bool(self.discord_token)


def _load_settings() -> Settings:
	prefix = os.getenv("BOT_PREFIX", DEFAULT_PREFIX)

	owner_ids_env = os.getenv("OWNER_IDS")
	owner_ids = _parse_owner_ids(owner_ids_env)
	if not owner_ids:
		owner_ids = list(DEFAULT_OWNER_IDS)

	guild_id_env = os.getenv("GUILD_ID")
	guild_id = _parse_int(guild_id_env)
	if guild_id is None:
		guild_id = DEFAULT_GUILD_ID

	discord_token = os.getenv("DISCORD_TOKEN")
	random_org_api_key = os.getenv("RANDOM_ORG_KEY")
	ollama_url = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL)

	return Settings(
		prefix=prefix,
		owner_ids=owner_ids,
		guild_id=guild_id,
		discord_token=discord_token,
		random_org_api_key=random_org_api_key,
		ollama_url=ollama_url,
	)


settings = _load_settings()
