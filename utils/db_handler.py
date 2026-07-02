from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseHandler:
    """Asynchronous database helper built on top of aiosqlite."""

    def __init__(self, db_path: str = "data/bot.db") -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.init_database()

    # ------------------------------------------------------------------
    # Schema initialisation & migration helpers
    # ------------------------------------------------------------------
    def init_database(self) -> None:
        logger.info("Initialising database", extra={"db_path": self.db_path})
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("PRAGMA foreign_keys = OFF")

            self._ensure_users_table(cursor)
            self._ensure_command_usage_table(cursor)
            self._ensure_command_cooldowns_table(cursor)
            self._ensure_word_usage_table(cursor)
            self._ensure_word_stats_table(cursor)
            self._ensure_prompts_table(cursor)
            self._ensure_command_executions_table(cursor)
            self._ensure_llm_settings_table(cursor)
            self._ensure_music_history_table(cursor)
            self._ensure_indexes(cursor)

            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    def _table_exists(self, cursor: sqlite3.Cursor, table: str) -> bool:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cursor.fetchone() is not None

    def _table_has_column(self, cursor: sqlite3.Cursor, table: str, column: str) -> bool:
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    def _migrate_table(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        create_sql: str,
        column_mapping: Dict[str, str],
    ) -> None:
        legacy_name = f"{table_name}_legacy"
        cursor.execute(f"ALTER TABLE {table_name} RENAME TO {legacy_name}")
        cursor.execute(create_sql)

        insert_columns = ", ".join(column_mapping.keys())
        select_columns = ", ".join(column_mapping.values())
        cursor.execute(
            f"INSERT INTO {table_name} ({insert_columns}) SELECT {select_columns} FROM {legacy_name}"
        )
        cursor.execute(f"DROP TABLE {legacy_name}")

    def _ensure_users_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_success INTEGER DEFAULT 0,
                success_streak INTEGER DEFAULT 0,
                last_success_check TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        if not self._table_exists(cursor, "users"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "users", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "users",
            schema,
            {
                "guild_id": "0",
                "user_id": "user_id",
                "username": "username",
                "first_seen": "first_seen",
                "last_active": "last_active",
                "total_success": "COALESCE(total_success, 0)",
                "success_streak": "COALESCE(success_streak, 0)",
                "last_success_check": "last_success_check",
            },
        )

    def _ensure_command_usage_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS command_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success_level INTEGER,
                roll_value INTEGER,
                FOREIGN KEY (guild_id, user_id) REFERENCES users (guild_id, user_id)
            )
            """
        )

        if not self._table_exists(cursor, "command_usage"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "command_usage", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "command_usage",
            schema,
            {
                "id": "id",
                "guild_id": "0",
                "user_id": "user_id",
                "command_name": "command_name",
                "used_at": "used_at",
                "success_level": "success_level",
                "roll_value": "roll_value",
            },
        )

    def _ensure_command_cooldowns_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS command_cooldowns (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                last_used TIMESTAMP,
                PRIMARY KEY (guild_id, user_id, command_name),
                FOREIGN KEY (guild_id, user_id) REFERENCES users (guild_id, user_id)
            )
            """
        )

        if not self._table_exists(cursor, "command_cooldowns"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "command_cooldowns", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "command_cooldowns",
            schema,
            {
                "guild_id": "0",
                "user_id": "user_id",
                "command_name": "command_name",
                "last_used": "last_used",
            },
        )

    def _ensure_word_usage_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS word_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                message_id INTEGER,
                channel_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guild_id, user_id) REFERENCES users (guild_id, user_id)
            )
            """
        )

        if not self._table_exists(cursor, "word_usage"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "word_usage", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "word_usage",
            schema,
            {
                "id": "id",
                "guild_id": "0",
                "user_id": "user_id",
                "word": "word",
                "message_id": "message_id",
                "channel_id": "channel_id",
                "used_at": "used_at",
            },
        )

    def _ensure_word_stats_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS word_stats (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                usage_count INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                PRIMARY KEY (guild_id, user_id, word),
                FOREIGN KEY (guild_id, user_id) REFERENCES users (guild_id, user_id)
            )
            """
        )

        if not self._table_exists(cursor, "word_stats"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "word_stats", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "word_stats",
            schema,
            {
                "guild_id": "0",
                "user_id": "user_id",
                "word": "word",
                "usage_count": "usage_count",
                "last_used": "last_used",
            },
        )

    def _ensure_prompts_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS prompts (
                guild_id INTEGER,
                model_name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_user_id INTEGER,
                updated_by_guild_id INTEGER,
                PRIMARY KEY (guild_id, model_name)
            )
            """
        )

        if not self._table_exists(cursor, "prompts"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "prompts", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "prompts",
            schema,
            {
                "guild_id": "NULL",
                "model_name": "model_name",
                "system_prompt": "system_prompt",
                "last_updated": "last_updated",
                "updated_by_user_id": "updated_by",
                "updated_by_guild_id": "NULL",
            },
        )

    def _ensure_command_executions_table(self, cursor: sqlite3.Cursor) -> None:
        schema = (
            """
            CREATE TABLE IF NOT EXISTS command_executions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id, command_name),
                FOREIGN KEY (guild_id, user_id) REFERENCES users (guild_id, user_id)
            )
            """
        )

        if not self._table_exists(cursor, "command_executions"):
            cursor.execute(schema)
            return

        if self._table_has_column(cursor, "command_executions", "guild_id"):
            return

        self._migrate_table(
            cursor,
            "command_executions",
            schema,
            {
                "guild_id": "0",
                "user_id": "user_id",
                "command_name": "command_name",
                "execution_time": "execution_time",
            },
        )

    def _ensure_llm_settings_table(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_settings (
                guild_id INTEGER PRIMARY KEY,
                model_key TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by_user_id INTEGER
            )
            """
        )

    def _ensure_music_history_table(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS music_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                song_title TEXT NOT NULL,
                song_url TEXT NOT NULL,
                song_duration INTEGER DEFAULT 0,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _ensure_indexes(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_command_usage_guild_user ON command_usage (guild_id, user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_command_usage_guild_command ON command_usage (guild_id, command_name)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_word_usage_guild_word ON word_usage (guild_id, word)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_word_stats_guild_word ON word_stats (guild_id, word)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_music_history_guild_user ON music_history (guild_id, user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_music_history_guild_song ON music_history (guild_id, song_url)"
        )

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        logger.debug("Opening database connection", extra={"db_path": self.db_path})
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            await conn.close()
            logger.debug("Closed database connection", extra={"db_path": self.db_path})

    # ------------------------------------------------------------------
    # Prompt management
    # ------------------------------------------------------------------
    async def get_prompt(self, model_name: str, guild_id: Optional[int] = None) -> Optional[str]:
        async with self._connect() as conn:
            if guild_id is not None:
                async with conn.execute(
                    """
                    SELECT system_prompt
                    FROM prompts
                    WHERE guild_id = ? AND model_name = ?
                    """,
                    (guild_id, model_name),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row["system_prompt"]

            async with conn.execute(
                """
                SELECT system_prompt
                FROM prompts
                WHERE guild_id IS NULL AND model_name = ?
                """,
                (model_name,),
            ) as cursor:
                row = await cursor.fetchone()
                return row["system_prompt"] if row else None

    async def set_prompt(
        self,
        model_name: str,
        system_prompt: str,
        *,
        guild_id: Optional[int] = None,
        updated_by_user_id: Optional[int] = None,
        updated_by_guild_id: Optional[int] = None,
    ) -> None:
        async with self._connect() as conn:
            if guild_id is None:
                cursor = await conn.execute(
                    """
                    UPDATE prompts
                    SET system_prompt = ?,
                        last_updated = CURRENT_TIMESTAMP,
                        updated_by_user_id = ?,
                        updated_by_guild_id = ?
                    WHERE guild_id IS NULL AND model_name = ?
                    """,
                    (system_prompt, updated_by_user_id, updated_by_guild_id, model_name),
                )
                if cursor.rowcount == 0:
                    await conn.execute(
                        """
                        INSERT INTO prompts (
                            guild_id,
                            model_name,
                            system_prompt,
                            last_updated,
                            updated_by_user_id,
                            updated_by_guild_id
                        )
                        VALUES (NULL, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                        """,
                        (model_name, system_prompt, updated_by_user_id, updated_by_guild_id),
                    )
                await conn.commit()
                return

            await conn.execute(
                """
                INSERT INTO prompts (guild_id, model_name, system_prompt, last_updated, updated_by_user_id, updated_by_guild_id)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(guild_id, model_name) DO UPDATE SET
                    system_prompt = excluded.system_prompt,
                    last_updated = CURRENT_TIMESTAMP,
                    updated_by_user_id = excluded.updated_by_user_id,
                    updated_by_guild_id = excluded.updated_by_guild_id
                """,
                (guild_id, model_name, system_prompt, updated_by_user_id, updated_by_guild_id),
            )
            await conn.commit()

    async def get_prompt_history(
        self, model_name: str, guild_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with self._connect() as conn:
            params: Sequence[Any]
            if guild_id is not None:
                query = (
                    """
                    SELECT p.*, u.username AS updated_by_name
                    FROM prompts p
                    LEFT JOIN users u
                        ON p.updated_by_guild_id = u.guild_id
                        AND p.updated_by_user_id = u.user_id
                    WHERE p.model_name = ? AND p.guild_id = ?
                    ORDER BY p.last_updated DESC
                    """
                )
                params = (model_name, guild_id)
            else:
                query = (
                    """
                    SELECT p.*, u.username AS updated_by_name
                    FROM prompts p
                    LEFT JOIN users u
                        ON p.updated_by_guild_id = u.guild_id
                        AND p.updated_by_user_id = u.user_id
                    WHERE p.model_name = ? AND p.guild_id IS NULL
                    ORDER BY p.last_updated DESC
                    """
                )
                params = (model_name,)

            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # User & success tracking
    # ------------------------------------------------------------------
    async def update_user(self, guild_id: int, user_id: int, username: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO users (guild_id, user_id, username, last_active)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    username = excluded.username,
                    last_active = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, username),
            )
            await conn.commit()

    async def add_total_success(self, guild_id: int, user_id: int, amount: int) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                UPDATE users
                SET total_success = COALESCE(total_success, 0) + ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ?
                """,
                (amount, guild_id, user_id),
            )
            await conn.commit()

    async def set_total_success(
        self, guild_id: int, user_id: int, username: str, total: int
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO users (guild_id, user_id, username, total_success, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    username = excluded.username,
                    total_success = excluded.total_success,
                    last_active = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, username, total),
            )
            await conn.commit()

    async def get_total_success(self, guild_id: int, user_id: int) -> int:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT COALESCE(total_success, 0) AS total_success
                FROM users
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row["total_success"]) if row else 0

    async def set_success_streak(
        self, guild_id: int, user_id: int, username: str, streak: int
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO users (guild_id, user_id, username, success_streak, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    username = excluded.username,
                    success_streak = excluded.success_streak,
                    last_active = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, username, streak),
            )
            await conn.commit()

    async def reset_success_stats(self, guild_id: int, user_id: int) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                UPDATE users
                SET total_success = 0,
                    success_streak = 0,
                    last_success_check = NULL,
                    last_active = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            await conn.execute(
                """
                DELETE FROM command_usage
                WHERE guild_id = ? AND user_id = ? AND command_name = 'успех'
                """,
                (guild_id, user_id),
            )
            await conn.execute(
                """
                DELETE FROM command_cooldowns
                WHERE guild_id = ? AND user_id = ? AND command_name = 'успех'
                """,
                (guild_id, user_id),
            )
            await conn.execute(
                """
                DELETE FROM command_executions
                WHERE guild_id = ? AND user_id = ? AND command_name = 'успех'
                """,
                (guild_id, user_id),
            )
            await conn.commit()

    async def log_command_usage(
        self,
        guild_id: int,
        user_id: int,
        command_name: str,
        *,
        success_level: Optional[int] = None,
        roll_value: Optional[int] = None,
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO command_usage (guild_id, user_id, command_name, success_level, roll_value)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, command_name, success_level, roll_value),
            )
            await conn.commit()

    async def update_command_cooldown(
        self, guild_id: int, user_id: int, command_name: str
    ) -> None:
        timestamp = datetime.now().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO command_cooldowns (guild_id, user_id, command_name, last_used)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, command_name) DO UPDATE SET
                    last_used = excluded.last_used
                """,
                (guild_id, user_id, command_name, timestamp),
            )
            await conn.commit()

    async def get_command_cooldown(
        self, guild_id: int, user_id: int, command_name: str
    ) -> Optional[datetime]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT last_used
                FROM command_cooldowns
                WHERE guild_id = ? AND user_id = ? AND command_name = ?
                """,
                (guild_id, user_id, command_name),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["last_used"]:
                    return datetime.fromisoformat(row["last_used"])
                return None

    async def update_success_streak(
        self, guild_id: int, user_id: int
    ) -> Dict[str, Any]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT success_streak, last_success_check
                FROM users
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()

            current_time = datetime.now()
            streak_info = {
                "streak_continued": False,
                "streak_reset": False,
                "current_streak": 0,
            }

            if row and row["last_success_check"]:
                last_check = datetime.fromisoformat(row["last_success_check"])
                current_streak = int(row["success_streak"] or 0)
                delta_days = (current_time.date() - last_check.date()).days

                if delta_days == 1:
                    current_streak += 1
                    streak_info["streak_continued"] = True
                elif delta_days == 0:
                    pass
                else:
                    current_streak = 1
                    streak_info["streak_reset"] = True
            else:
                current_streak = 1

            await conn.execute(
                """
                UPDATE users
                SET success_streak = ?,
                    last_success_check = ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ?
                """,
                (current_streak, current_time.isoformat(), guild_id, user_id),
            )
            await conn.commit()

            streak_info["current_streak"] = current_streak
            return streak_info

    async def get_success_stats(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT
                    u.total_success,
                    u.success_streak,
                    u.last_success_check,
                    COUNT(DISTINCT cu.id) AS total_attempts,
                    COALESCE(MAX(cu.success_level), 0) AS highest_success,
                    COALESCE(AVG(CAST(cu.success_level AS FLOAT)), 0) AS avg_success
                FROM users u
                LEFT JOIN command_usage cu
                    ON u.guild_id = cu.guild_id
                    AND u.user_id = cu.user_id
                    AND cu.command_name = 'успех'
                WHERE u.guild_id = ? AND u.user_id = ?
                GROUP BY u.guild_id, u.user_id
                """,
                (guild_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

        return {
            "total_success": 0,
            "success_streak": 0,
            "last_success_check": None,
            "total_attempts": 0,
            "highest_success": 0,
            "avg_success": 0,
        }

    async def get_success_leaderboard(
        self, guild_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT
                    u.username,
                    COALESCE(u.total_success, 0) AS total_success,
                    COALESCE(u.success_streak, 0) AS success_streak,
                    COUNT(DISTINCT cu.id) AS total_attempts,
                    COALESCE(MAX(cu.success_level), 0) AS highest_success,
                    COALESCE(AVG(CAST(cu.success_level AS FLOAT)), 0) AS avg_success
                FROM users u
                LEFT JOIN command_usage cu
                    ON u.guild_id = cu.guild_id
                    AND u.user_id = cu.user_id
                    AND cu.command_name = 'успех'
                WHERE u.guild_id = ?
                    AND (
                        COALESCE(u.total_success, 0) > 0
                        OR EXISTS (
                            SELECT 1
                            FROM command_usage cu2
                            WHERE cu2.guild_id = u.guild_id
                              AND cu2.user_id = u.user_id
                              AND cu2.command_name = 'успех'
                        )
                    )
                GROUP BY u.guild_id, u.user_id, u.username, u.total_success, u.success_streak
                ORDER BY COALESCE(u.total_success, 0) DESC,
                         COALESCE(u.success_streak, 0) DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Word tracking
    # ------------------------------------------------------------------
    async def log_word_usage(
        self,
        guild_id: int,
        user_id: int,
        word: str,
        message_id: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO word_usage (guild_id, user_id, word, message_id, channel_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, word, message_id, channel_id),
            )
            await conn.execute(
                """
                INSERT INTO word_stats (guild_id, user_id, word, usage_count, last_used)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id, user_id, word) DO UPDATE SET
                    usage_count = usage_count + 1,
                    last_used = CURRENT_TIMESTAMP
                """,
                (guild_id, user_id, word),
            )
            await conn.commit()

    async def get_user_word_stats(
        self, guild_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT word, usage_count, last_used
                FROM word_stats
                WHERE guild_id = ? AND user_id = ?
                ORDER BY usage_count DESC
                """,
                (guild_id, user_id),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_word_leaderboard(
        self, guild_id: int, word: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        async with self._connect() as conn:
            if word:
                query = (
                    """
                    SELECT u.username,
                           ws.word,
                           ws.usage_count,
                           ws.last_used
                    FROM word_stats ws
                    JOIN users u
                        ON ws.guild_id = u.guild_id
                        AND ws.user_id = u.user_id
                    WHERE ws.guild_id = ? AND ws.word = ?
                    ORDER BY ws.usage_count DESC
                    LIMIT ?
                    """
                )
                params = (guild_id, word, limit)
            else:
                query = (
                    """
                    SELECT u.username,
                           SUM(ws.usage_count) AS total_count,
                           COUNT(DISTINCT ws.word) AS unique_words,
                           MAX(ws.last_used) AS last_used
                    FROM word_stats ws
                    JOIN users u
                        ON ws.guild_id = u.guild_id
                        AND ws.user_id = u.user_id
                    WHERE ws.guild_id = ?
                    GROUP BY ws.guild_id, ws.user_id, u.username
                    ORDER BY total_count DESC
                    LIMIT ?
                    """
                )
                params = (guild_id, limit)

            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Command execution timestamps
    # ------------------------------------------------------------------
    async def record_command_execution(
        self, guild_id: int, user_id: int, command_name: str
    ) -> datetime:
        current_time = datetime.now()
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO command_executions (guild_id, user_id, command_name, execution_time)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, command_name) DO UPDATE SET
                    execution_time = excluded.execution_time
                """,
                (guild_id, user_id, command_name, current_time.isoformat()),
            )
            await conn.commit()
        return current_time

    async def get_command_execution_time(
        self, guild_id: int, user_id: int, command_name: str
    ) -> Optional[datetime]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT execution_time
                FROM command_executions
                WHERE guild_id = ? AND user_id = ? AND command_name = ?
                """,
                (guild_id, user_id, command_name),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["execution_time"]:
                    return datetime.fromisoformat(row["execution_time"])
                return None

    # ------------------------------------------------------------------
    # LLM settings helpers
    # ------------------------------------------------------------------
    async def set_llm_active_model(
        self,
        guild_id: int,
        model_key: str,
        *,
        updated_by_user_id: Optional[int] = None,
    ) -> None:
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO llm_settings (guild_id, model_key, updated_at, updated_by_user_id)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    model_key = excluded.model_key,
                    updated_at = excluded.updated_at,
                    updated_by_user_id = excluded.updated_by_user_id
                """,
                (guild_id, model_key, updated_by_user_id),
            )
            await conn.commit()

    async def get_llm_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT model_key, updated_at, updated_by_user_id
                FROM llm_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # ------------------------------------------------------------------
    # Music history
    # ------------------------------------------------------------------
    async def log_music_play(
        self,
        guild_id: int,
        user_id: int,
        song_title: str,
        song_url: str,
        song_duration: int = 0,
    ) -> None:
        """Log a song play to music history.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            song_title: Title of the song
            song_url: URL of the song
            song_duration: Duration in seconds
        """
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO music_history (guild_id, user_id, song_title, song_url, song_duration, played_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (guild_id, user_id, song_title, song_url, song_duration),
            )
            await conn.commit()
            logger.debug(
                f"Logged music play: '{song_title}' by user {user_id} in guild {guild_id}"
            )

    async def get_user_music_stats(
        self, guild_id: int, user_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get a user's music listening statistics.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            limit: Maximum number of results

        Returns:
            List of most played songs with play counts
        """
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT song_title, song_url, COUNT(*) as play_count,
                       MAX(played_at) as last_played
                FROM music_history
                WHERE guild_id = ? AND user_id = ?
                GROUP BY song_url
                ORDER BY play_count DESC
                LIMIT ?
                """,
                (guild_id, user_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_guild_top_songs(
        self, guild_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get the most played songs in a guild.

        Args:
            guild_id: Discord guild ID
            limit: Maximum number of results

        Returns:
            List of top songs with play counts
        """
        async with self._connect() as conn:
            async with conn.execute(
                """
                SELECT song_title, song_url, COUNT(*) as play_count,
                       MAX(played_at) as last_played
                FROM music_history
                WHERE guild_id = ?
                GROUP BY song_url
                ORDER BY play_count DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


_shared_db_handler: Optional[DatabaseHandler] = None


def get_database_handler() -> DatabaseHandler:
    """Return a lazily initialised shared database handler."""
    global _shared_db_handler
    if _shared_db_handler is None:
        _shared_db_handler = DatabaseHandler()
    return _shared_db_handler
