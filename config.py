"""Load bot settings from the environment."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int_setting(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer.") from None
    if number < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return number


def _volume_setting() -> float:
    value = os.getenv("MUSIC_DEFAULT_VOLUME", "").strip()
    try:
        volume = float(value) if value else 0.5
    except ValueError:
        raise ValueError("MUSIC_DEFAULT_VOLUME must be a number.") from None
    if not 0 <= volume <= 1:
        raise ValueError("MUSIC_DEFAULT_VOLUME must be between 0 and 1.")
    return volume


def _owner_ids() -> set[int]:
    try:
        ids = {int(value) for value in os.getenv("OWNER_IDS", "").split(",") if value.strip()}
    except ValueError:
        raise ValueError("OWNER_IDS must contain comma-separated Discord user IDs.") from None
    if any(value <= 0 for value in ids):
        raise ValueError("OWNER_IDS must contain positive Discord user IDs.")
    return ids


@dataclass(slots=True)
class Settings:
    prefix: str
    owner_ids: set[int]
    discord_token: str | None
    random_org_api_key: str | None
    polygon_api_key: str | None
    data_dir: Path
    ready_file: Path | None
    music_max_queue_size: int
    music_idle_timeout: int
    music_default_volume: float
    music_max_duration: int

    @property
    def random_org_enabled(self) -> bool:
        return bool(self.random_org_api_key)

    @property
    def polygon_enabled(self) -> bool:
        return bool(self.polygon_api_key)


def _load_settings() -> Settings:
    ready_file = os.getenv("XDBOT_READY_FILE")
    return Settings(
        prefix=os.getenv("BOT_PREFIX", "").strip() or "!",
        owner_ids=_owner_ids(),
        discord_token=os.getenv("DISCORD_TOKEN") or None,
        random_org_api_key=os.getenv("RANDOM_ORG_KEY") or None,
        polygon_api_key=os.getenv("POLYGON_API_KEY") or None,
        data_dir=Path(os.getenv("XDBOT_DATA_DIR") or "data"),
        ready_file=Path(ready_file) if ready_file else None,
        music_max_queue_size=_int_setting("MUSIC_MAX_QUEUE_SIZE", 100),
        music_idle_timeout=_int_setting("MUSIC_IDLE_TIMEOUT", 300),
        music_default_volume=_volume_setting(),
        music_max_duration=_int_setting("MUSIC_MAX_DURATION", 3600),
    )


settings = _load_settings()
