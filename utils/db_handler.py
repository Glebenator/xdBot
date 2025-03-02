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
        """Initialize database tables and add new columns if needed"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # First create the users table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Check for and add new columns if they don't exist
            cursor.execute('PRAGMA table_info(users)')
            existing_columns = {row['name'] for row in cursor.fetchall()}

            # Add new columns if they don't exist
            new_columns = {
                'total_success': 'INTEGER DEFAULT 0',
                'success_streak': 'INTEGER DEFAULT 0',
                'last_success_check': 'TIMESTAMP',
                'has_reroll_ability': 'BOOLEAN DEFAULT 0'
            }

            for column, data_type in new_columns.items():
                if column not in existing_columns:
                    try:
                        cursor.execute(f'ALTER TABLE users ADD COLUMN {column} {data_type}')
                    except Exception as e:
                        print(f"Error adding column {column}: {e}")

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

            # Create word_stats table
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

             # Create command_rerolls table to track reroll usage
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_rerolls (
                    user_id INTEGER,
                    command_time TIMESTAMP,
                    rerolled BOOLEAN DEFAULT 0,
                    PRIMARY KEY (user_id, command_time),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            # Create prompts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prompts (
                    model_name TEXT PRIMARY KEY,
                    system_prompt TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER,
                    FOREIGN KEY (updated_by) REFERENCES users (user_id)
                )
            ''')

            # Create command_executions table to track exact execution times
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_executions (
                    user_id INTEGER,
                    command_name TEXT,
                    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, command_name),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            conn.commit()


    def get_prompt(self, model_name: str) -> Optional[str]:
        """Get the system prompt for a specific model"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT system_prompt
                FROM prompts
                WHERE model_name = ?
            ''', (model_name,))
            result = cursor.fetchone()
            return result['system_prompt'] if result else None
        
    def set_prompt(self, model_name: str, system_prompt: str, updated_by: int) -> None:
        """Set or update the system prompt for a model"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO prompts (model_name, system_prompt, updated_by, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(model_name) DO UPDATE SET
                    system_prompt = ?,
                    updated_by = ?,
                    last_updated = CURRENT_TIMESTAMP
            ''', (model_name, system_prompt, updated_by, system_prompt, updated_by))
            conn.commit()

    def get_prompt_history(self, model_name: str) -> List[Dict[str, Any]]:
        """Get prompt update history for a model"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, u.username as updated_by_name
                FROM prompts p
                LEFT JOIN users u ON p.updated_by = u.user_id
                WHERE p.model_name = ?
                ORDER BY p.last_updated DESC
            ''', (model_name,))
            return [dict(row) for row in cursor.fetchall()]
        
    def add_reroll_usage(self, user_id: int, command_time: datetime) -> None:
        """Track that a user has used their reroll for a specific успех command"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO command_rerolls (user_id, command_time, rerolled)
                VALUES (?, ?, 1)
            ''', (user_id, command_time))
            conn.commit()

    def has_rerolled(self, user_id: int, command_time: datetime) -> bool:
        """Check if user has already rerolled for a specific успех command"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT rerolled FROM command_rerolls
                WHERE user_id = ? AND command_time = ?
            ''', (user_id, command_time))
            result = cursor.fetchone()
            return bool(result and result['rerolled'])
    
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

    def unlock_reroll_ability(self, user_id: int) -> None:
        """Unlock the reroll ability for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET has_reroll_ability = 1
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()

    def has_reroll_ability(self, user_id: int) -> bool:
        """Check if user has unlocked the reroll ability"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT has_reroll_ability
                FROM users
                WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            return bool(result and result['has_reroll_ability'])

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

    def update_total_success(self, user_id: int, success_level: int) -> None:
        """Update user's total success score"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET total_success = COALESCE(total_success, 0) + ?
                WHERE user_id = ?
            ''', (success_level, user_id))
            conn.commit()

    def update_success_streak(self, user_id: int) -> Dict[str, Any]:
        """Update user's success streak and return streak info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get user's last success check
            cursor.execute('''
                SELECT last_success_check, success_streak
                FROM users
                WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            
            current_time = datetime.now()
            streak_info = {
                'streak_continued': False,
                'streak_reset': False,
                'current_streak': 0
            }
            
            if result and result['last_success_check']:
                last_check = datetime.fromisoformat(result['last_success_check'])
                current_streak = result['success_streak'] or 0  # Handle NULL value
                
                # Calculate days between checks
                days_diff = (current_time.date() - last_check.date()).days
                
                if days_diff == 1:
                    # Streak continues
                    current_streak += 1
                    streak_info['streak_continued'] = True
                elif days_diff == 0:
                    # Already checked today, maintain streak
                    pass
                else:
                    # Streak broken
                    current_streak = 1
                    streak_info['streak_reset'] = True
            else:
                # First time checking
                current_streak = 1
            
            # Update user's streak and last check time
            cursor.execute('''
                UPDATE users
                SET success_streak = ?,
                    last_success_check = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (current_streak, user_id))
            
            streak_info['current_streak'] = current_streak
            conn.commit()
            return streak_info

    def get_success_stats(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive success stats for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.total_success,
                    u.success_streak,
                    u.has_reroll_ability,
                    u.last_success_check,
                    COUNT(DISTINCT cu.id) as total_attempts,
                    MAX(cu.success_level) as highest_success,
                    AVG(CAST(cu.success_level AS FLOAT)) as avg_success
                FROM users u
                LEFT JOIN command_usage cu 
                    ON u.user_id = cu.user_id 
                    AND cu.command_name = 'успех'
                WHERE u.user_id = ?
                GROUP BY u.user_id
            ''', (user_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return {
                'total_success': 0,
                'success_streak': 0,
                'has_reroll_ability': False,
                'last_success_check': None,
                'total_attempts': 0,
                'highest_success': 0,
                'avg_success': 0
            }

    def get_success_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard for успех command"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.username,
                    COALESCE(u.total_success, 0) as total_success,
                    COALESCE(u.success_streak, 0) as success_streak,
                    COALESCE(u.has_reroll_ability, 0) as has_reroll_ability,
                    COUNT(DISTINCT cu.id) as total_attempts,
                    COALESCE(MAX(cu.success_level), 0) as highest_success,
                    COALESCE(AVG(CAST(cu.success_level AS FLOAT)), 0) as avg_success
                FROM users u
                LEFT JOIN command_usage cu 
                    ON u.user_id = cu.user_id 
                    AND cu.command_name = 'успех'
                WHERE COALESCE(u.total_success, 0) > 0 
                    OR EXISTS (
                        SELECT 1 
                        FROM command_usage cu2 
                        WHERE cu2.user_id = u.user_id 
                        AND cu2.command_name = 'успех'
                    )
                GROUP BY u.user_id, u.username, u.total_success, u.success_streak, u.has_reroll_ability
                ORDER BY COALESCE(u.total_success, 0) DESC, COALESCE(u.success_streak, 0) DESC
                LIMIT ?
            ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]

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

    def record_command_execution(self, user_id: int, command_name: str) -> datetime:
        """Record the exact time a command was executed and return the timestamp"""
        current_time = datetime.now()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO command_executions (user_id, command_name, execution_time)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, command_name) DO UPDATE SET
                    execution_time = ?
            ''', (user_id, command_name, current_time, current_time))
            conn.commit()
        return current_time

    def get_command_execution_time(self, user_id: int, command_name: str) -> Optional[datetime]:
        """Get the exact time a command was last executed"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT execution_time FROM command_executions
                WHERE user_id = ? AND command_name = ?
            ''', (user_id, command_name))
            result = cursor.fetchone()
            if result:
                return datetime.fromisoformat(result['execution_time'])
            return None