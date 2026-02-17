"""Centralised application configuration.

This module exposes a `settings` instance that gathers configuration from
environment variables (with sensible defaults) so that the rest of the code
base does not need to touch `os.environ` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:  # Ensure .env files are loaded before reading environment variables
    from dotenv import load_dotenv

    load_dotenv()  # type: ignore[no-untyped-call]
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


DEFAULT_PREFIX = "!"
DEFAULT_OWNER_IDS: List[int] = []
DEFAULT_GUILD_ID: Optional[int] = None
DEFAULT_OLLAMA_URL = "http://192.168.50.69:11434"
DEFAULT_OLLAMA_CHAT_MODEL = "qwen3:4b"
DEFAULT_OLLAMA_MENTION_MODEL = "xdbot-rude"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_APP_NAME = "xdBot"
DEFAULT_MUSIC_MAX_QUEUE_SIZE = 100
DEFAULT_MUSIC_IDLE_TIMEOUT = 300
DEFAULT_MUSIC_DEFAULT_VOLUME = 0.5
DEFAULT_MUSIC_MAX_DURATION = 3600


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


def _parse_float(value: Optional[str], default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


@dataclass(slots=True)
class Settings:
    """Runtime configuration container."""

    prefix: str = DEFAULT_PREFIX
    owner_ids: List[int] = field(default_factory=list)
    guild_id: Optional[int] = DEFAULT_GUILD_ID
    discord_token: Optional[str] = None
    random_org_api_key: Optional[str] = None
    ollama_url: str = DEFAULT_OLLAMA_URL
    ollama_chat_model: str = DEFAULT_OLLAMA_CHAT_MODEL
    ollama_mention_model: str = DEFAULT_OLLAMA_MENTION_MODEL
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = DEFAULT_OPENROUTER_BASE_URL
    openrouter_site_url: Optional[str] = None
    openrouter_app_name: str = DEFAULT_OPENROUTER_APP_NAME
    openrouter_default_model: Optional[str] = None
    tavily_api_key: Optional[str] = None
    polygon_api_key: Optional[str] = None

    # Music settings
    music_max_queue_size: int = DEFAULT_MUSIC_MAX_QUEUE_SIZE
    music_idle_timeout: int = DEFAULT_MUSIC_IDLE_TIMEOUT  # seconds (5 minutes)
    music_default_volume: float = DEFAULT_MUSIC_DEFAULT_VOLUME  # 0.0 to 1.0
    music_max_duration: int = DEFAULT_MUSIC_MAX_DURATION  # seconds (1 hour)

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
    ollama_chat_model = os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_CHAT_MODEL)
    ollama_mention_model = os.getenv("OLLAMA_MENTION_MODEL", DEFAULT_OLLAMA_MENTION_MODEL)
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)
    openrouter_site_url = os.getenv("OPENROUTER_SITE_URL") or None
    openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", DEFAULT_OPENROUTER_APP_NAME)
    openrouter_default_model = os.getenv("OPENROUTER_DEFAULT_MODEL") or None
    tavily_api_key = os.getenv("TAVILY_API_KEY") or None
    polygon_api_key = os.getenv("POLYGON_API_KEY") or None
    music_max_queue_size = _parse_int(os.getenv("MUSIC_MAX_QUEUE_SIZE")) or DEFAULT_MUSIC_MAX_QUEUE_SIZE
    music_idle_timeout = _parse_int(os.getenv("MUSIC_IDLE_TIMEOUT")) or DEFAULT_MUSIC_IDLE_TIMEOUT
    music_default_volume = _parse_float(
        os.getenv("MUSIC_DEFAULT_VOLUME"),
        DEFAULT_MUSIC_DEFAULT_VOLUME,
    )
    music_max_duration = _parse_int(os.getenv("MUSIC_MAX_DURATION")) or DEFAULT_MUSIC_MAX_DURATION
    music_default_volume = max(0.0, min(1.0, music_default_volume))

    return Settings(
        prefix=prefix,
        owner_ids=owner_ids,
        guild_id=guild_id,
        discord_token=discord_token,
        random_org_api_key=random_org_api_key,
        ollama_url=ollama_url,
        ollama_chat_model=ollama_chat_model,
        ollama_mention_model=ollama_mention_model,
        openrouter_api_key=openrouter_api_key,
        openrouter_base_url=openrouter_base_url,
        openrouter_site_url=openrouter_site_url,
        openrouter_app_name=openrouter_app_name,
        openrouter_default_model=openrouter_default_model,
        tavily_api_key=tavily_api_key,
        polygon_api_key=polygon_api_key,
        music_max_queue_size=music_max_queue_size,
        music_idle_timeout=music_idle_timeout,
        music_default_volume=music_default_volume,
        music_max_duration=music_max_duration,
    )


settings = _load_settings()
