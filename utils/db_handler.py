# utils/db_handler.py
import sqlite3
from datetime import datetime
import json
from typing import Optional, Dict, Any, List
import os

class DatabaseHandler:
    def __init__(self, db_path: str = "data/bot.db"):
        """Initialize database connection and create tables if they don't exist"""
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create command_usage table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    command_name TEXT,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success_level INTEGER,
                    roll_value INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Create command_cooldowns table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_cooldowns (
                    user_id INTEGER,
                    command_name TEXT,
                    last_used TIMESTAMP,
                    PRIMARY KEY (user_id, command_name),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Create word_usage table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS word_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    word TEXT,
                    message_id INTEGER,
                    channel_id INTEGER,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Create word_stats table for quick access to totals
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS word_stats (
                    user_id INTEGER,
                    word TEXT,
                    usage_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP,
                    PRIMARY KEY (user_id, word),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            conn.commit()

    def update_user(self, user_id: int, username: str) -> None:
        """Update or create user record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (user_id, username, last_active)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = ?,
                    last_active = CURRENT_TIMESTAMP
            ''', (user_id, username, username))
            conn.commit()

    def log_command_usage(self, user_id: int, command_name: str, 
                         success_level: Optional[int] = None,
                         roll_value: Optional[int] = None) -> None:
        """Log command usage with optional success level and roll value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO command_usage 
                (user_id, command_name, success_level, roll_value)
                VALUES (?, ?, ?, ?)
            ''', (user_id, command_name, success_level, roll_value))
            conn.commit()

    def log_word_usage(self, user_id: int, word: str, 
                    message_id: Optional[int] = None,
                    channel_id: Optional[int] = None) -> None:
        """Log usage of a tracked word"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Log individual usage
            cursor.execute('''
                INSERT INTO word_usage (user_id, word, message_id, channel_id)
                VALUES (?, ?, ?, ?)
            ''', (user_id, word, message_id, channel_id))

            # Update stats
            cursor.execute('''
                INSERT INTO word_stats (user_id, word, usage_count, last_used)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, word) DO UPDATE SET
                    usage_count = usage_count + 1,
                    last_used = CURRENT_TIMESTAMP
            ''', (user_id, word))
            
            conn.commit()

    def update_command_cooldown(self, user_id: int, command_name: str) -> None:
        """Update command cooldown timestamp"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO command_cooldowns (user_id, command_name, last_used)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, command_name) DO UPDATE SET
                    last_used = CURRENT_TIMESTAMP
            ''', (user_id, command_name))
            conn.commit()

    def get_command_cooldown(self, user_id: int, command_name: str) -> Optional[datetime]:
        """Get last usage time for a command"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT last_used FROM command_cooldowns
                WHERE user_id = ? AND command_name = ?
            ''', (user_id, command_name))
            result = cursor.fetchone()
            if result:
                return datetime.fromisoformat(result['last_used'])
            return None

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive stats for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get command usage counts
            cursor.execute('''
                SELECT command_name, COUNT(*) as count
                FROM command_usage
                WHERE user_id = ?
                GROUP BY command_name
            ''', (user_id,))
            command_counts = {row['command_name']: row['count'] 
                            for row in cursor.fetchall()}

            # Get success command stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_successes,
                    AVG(success_level) as avg_success,
                    MAX(success_level) as max_success
                FROM command_usage
                WHERE user_id = ? AND command_name = 'успех'
            ''', (user_id,))
            success_stats = dict(cursor.fetchone())

            # Get roll command stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_rolls,
                    AVG(roll_value) as avg_roll,
                    MAX(roll_value) as max_roll
                FROM command_usage
                WHERE user_id = ? AND command_name = 'roll'
            ''', (user_id,))
            roll_stats = dict(cursor.fetchone())

            return {
                'command_counts': command_counts,
                'success_stats': success_stats,
                'roll_stats': roll_stats
            }

    def get_success_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard for успех command"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.username,
                    COUNT(*) as total_attempts,
                    MAX(cu.success_level) as highest_success,
                    AVG(cu.success_level) as avg_success
                FROM command_usage cu
                JOIN users u ON cu.user_id = u.user_id
                WHERE command_name = 'успех'
                GROUP BY cu.user_id, u.username
                ORDER BY avg_success DESC, total_attempts ASC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_word_stats(self, user_id: int) -> List[Dict[str, Any]]:
        """Get word usage statistics for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    word,
                    usage_count,
                    last_used
                FROM word_stats
                WHERE user_id = ?
                ORDER BY usage_count DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_word_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent word usage history for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    word,
                    used_at,
                    message_id,
                    channel_id
                FROM word_usage
                WHERE user_id = ?
                ORDER BY used_at DESC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_word_leaderboard(self, word: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard for word usage"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if word:
                # Leaderboard for specific word
                cursor.execute('''
                    SELECT 
                        u.username,
                        ws.word,
                        ws.usage_count,
                        ws.last_used
                    FROM word_stats ws
                    JOIN users u ON ws.user_id = u.user_id
                    WHERE ws.word = ?
                    ORDER BY ws.usage_count DESC
                    LIMIT ?
                ''', (word, limit))
            else:
                # Overall leaderboard
                cursor.execute('''
                    SELECT 
                        u.username,
                        SUM(ws.usage_count) as total_count,
                        COUNT(DISTINCT ws.word) as unique_words,
                        MAX(ws.last_used) as last_used
                    FROM word_stats ws
                    JOIN users u ON ws.user_id = u.user_id
                    GROUP BY ws.user_id, u.username
                    ORDER BY total_count DESC
                    LIMIT ?
                ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]