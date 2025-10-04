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
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_APP_NAME = "xdBot"


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
	openrouter_api_key: Optional[str] = None
	openrouter_base_url: str = DEFAULT_OPENROUTER_BASE_URL
	openrouter_site_url: Optional[str] = None
	openrouter_app_name: str = DEFAULT_OPENROUTER_APP_NAME
	openrouter_default_model: Optional[str] = None
	tavily_api_key: Optional[str] = None
	polygon_api_key: Optional[str] = None
	
	# Music settings
	music_max_queue_size: int = 100
	music_idle_timeout: int = 300  # seconds (5 minutes)
	music_default_volume: float = 0.5  # 0.0 to 1.0
	music_max_duration: int = 3600  # seconds (1 hour)

	@property
	def random_org_enabled(self) -> bool:
		return bool(self.random_org_api_key)

	@property
	def has_discord_token(self) -> bool:
		return bool(self.discord_token)

	@property
	def openrouter_enabled(self) -> bool:
		return bool(self.openrouter_api_key)

	@property
	def tavily_enabled(self) -> bool:
		return bool(self.tavily_api_key)

	@property
	def polygon_enabled(self) -> bool:
		return bool(self.polygon_api_key)


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
	openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
	openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)
	openrouter_site_url = os.getenv("OPENROUTER_SITE_URL") or None
	openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", DEFAULT_OPENROUTER_APP_NAME)
	openrouter_default_model = os.getenv("OPENROUTER_DEFAULT_MODEL") or None
	tavily_api_key = os.getenv("TAVILY_API_KEY") or None
	polygon_api_key = os.getenv("POLYGON_API_KEY") or None

	return Settings(
		prefix=prefix,
		owner_ids=owner_ids,
		guild_id=guild_id,
		discord_token=discord_token,
		random_org_api_key=random_org_api_key,
		ollama_url=ollama_url,
		openrouter_api_key=openrouter_api_key,
		openrouter_base_url=openrouter_base_url,
		openrouter_site_url=openrouter_site_url,
		openrouter_app_name=openrouter_app_name,
		openrouter_default_model=openrouter_default_model,
		tavily_api_key=tavily_api_key,
		polygon_api_key=polygon_api_key,
	)


settings = _load_settings()
