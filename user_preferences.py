import sqlite3
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class UserPreferences:
    def __init__(self, db_path: str = "news_bhai.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id INTEGER PRIMARY KEY,
                        language TEXT DEFAULT 'english',
                        topics TEXT DEFAULT '[]',
                        frequency TEXT DEFAULT 'daily',
                        setup_complete INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add setup_complete column to existing tables if it doesn't exist
                cursor.execute("PRAGMA table_info(user_preferences)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'setup_complete' not in columns:
                    cursor.execute("ALTER TABLE user_preferences ADD COLUMN setup_complete INTEGER DEFAULT 0")
                
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
    
    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Get user preferences from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT language, topics, frequency FROM user_preferences WHERE user_id = ?",
                    (user_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    language, topics_json, frequency = result
                    topics = json.loads(topics_json) if topics_json else []
                    return {
                        'language': language,
                        'topics': topics,
                        'frequency': frequency
                    }
                else:
                    # Return default preferences for new users
                    return {
                        'language': 'english',
                        'topics': [],
                        'frequency': 'daily'
                    }
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return {'language': 'english', 'topics': [], 'frequency': 'daily'}
    
    def update_user_preference(self, user_id: int, key: str, value: Any) -> bool:
        """Update a specific user preference"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if user exists
                cursor.execute("SELECT user_id FROM user_preferences WHERE user_id = ?", (user_id,))
                user_exists = cursor.fetchone() is not None
                
                if key == 'topics':
                    value = json.dumps(value) if isinstance(value, list) else value
                
                if user_exists:
                    # Update existing user
                    cursor.execute(
                        f"UPDATE user_preferences SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                        (value, user_id)
                    )
                else:
                    # Insert new user with default values
                    defaults = {
                        'language': 'english',
                        'topics': '[]',
                        'frequency': 'daily'
                    }
                    defaults[key] = value
                    
                    cursor.execute(
                        "INSERT INTO user_preferences (user_id, language, topics, frequency) VALUES (?, ?, ?, ?)",
                        (user_id, defaults['language'], defaults['topics'], defaults['frequency'])
                    )
                
                conn.commit()
                logger.info(f"Updated {key} for user {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating user preference: {e}")
            return False
    
    def add_user_topic(self, user_id: int, topic: str) -> bool:
        """Add a topic to user's interests"""
        try:
            prefs = self.get_user_preferences(user_id)
            topics = prefs.get('topics', [])
            
            if topic not in topics:
                topics.append(topic)
                return self.update_user_preference(user_id, 'topics', topics)
            return True
        except Exception as e:
            logger.error(f"Error adding topic: {e}")
            return False
    
    def remove_user_topic(self, user_id: int, topic: str) -> bool:
        """Remove a topic from user's interests"""
        try:
            prefs = self.get_user_preferences(user_id)
            topics = prefs.get('topics', [])
            
            if topic in topics:
                topics.remove(topic)
                return self.update_user_preference(user_id, 'topics', topics)
            return True
        except Exception as e:
            logger.error(f"Error removing topic: {e}")
            return False
    
    def get_all_users_by_frequency(self, frequency: str) -> List[int]:
        """Get all users with a specific update frequency"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT user_id FROM user_preferences WHERE frequency = ?",
                    (frequency,)
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting users by frequency: {e}")
            return []
    def get_user_topics(self, user_id: int) -> List[str]:
        """Get user's selected topics"""
        try:
            prefs = self.get_user_preferences(user_id)
            return prefs.get('topics', [])
        except Exception as e:
            logger.error(f"Error getting user topics: {e}")
            return []    
    # Remove duplicate get_user_topics method
    
    def mark_setup_complete(self, user_id: int) -> bool:
        """Mark user as having completed setup"""
        return self.update_user_preference(user_id, 'setup_complete', 1)
    
    def get_active_users(self):
        """Get list of active user IDs"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get users who have completed setup
            cursor.execute("SELECT user_id FROM user_preferences WHERE setup_complete = 1")
            active_users = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            return active_users
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []