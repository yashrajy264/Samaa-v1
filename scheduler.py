import asyncio
import logging
import schedule
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from bot import NewsBhaiBot

logger = logging.getLogger(__name__)

class NewsScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.scheduler_thread = None
        self.running = False
    
    def start(self):
        """Start the news scheduler"""
        if self.running:
            return
        
        self.running = True
        
        # Schedule different frequency updates
        schedule.every().day.at("08:00").do(self._send_daily_news)
        schedule.every().day.at("18:00").do(self._send_evening_news)
        schedule.every().monday.at("09:00").do(self._send_weekly_news)
        
        # Start scheduler in a separate thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("News scheduler started")
    
    def stop(self):
        """Stop the news scheduler"""
        self.running = False
        schedule.clear()
        logger.info("News scheduler stopped")
    
    def _run_scheduler(self):
        """Run the scheduler loop"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler: {e}")
                time.sleep(60)
    
    def _send_daily_news(self):
        """Send daily news to users"""
        try:
            users = self.bot.user_prefs.get_all_users_by_frequency('daily')
            asyncio.create_task(self._send_news_to_users(users, 'daily'))
        except Exception as e:
            logger.error(f"Error sending daily news: {e}")
    
    def _send_evening_news(self):
        """Send evening news to users with twice daily frequency"""
        try:
            users = self.bot.user_prefs.get_all_users_by_frequency('twice_daily')
            asyncio.create_task(self._send_news_to_users(users, 'evening'))
        except Exception as e:
            logger.error(f"Error sending evening news: {e}")
    
    def _send_weekly_news(self):
        """Send weekly news digest"""
        try:
            users = self.bot.user_prefs.get_all_users_by_frequency('weekly')
            asyncio.create_task(self._send_news_to_users(users, 'weekly'))
        except Exception as e:
            logger.error(f"Error sending weekly news: {e}")
    
    async def _send_news_to_users(self, user_ids: list, update_type: str):
        """Send news updates to a list of users"""
        for user_id in user_ids:
            try:
                await self._send_scheduled_news(user_id, update_type)
                # Add delay to avoid rate limiting
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error sending news to user {user_id}: {e}")
    
    async def _send_scheduled_news(self, user_id: int, update_type: str):
        """Send scheduled news to a specific user"""
        try:
            # Get user preferences
            prefs = self.bot.user_prefs.get_user_preferences(user_id)
            language = prefs.get('language', 'english')
            topics = prefs.get('topics', ['general'])
            
            # Get news based on update type
            if update_type == 'weekly':
                news_data = await self.bot.news_scraper.get_latest_news(topics, limit=15)
            else:
                news_data = await self.bot.news_scraper.get_latest_news(topics, limit=8)
            
            if not news_data:
                return
            
            # Create appropriate message based on update type
            if update_type == 'daily':
                greeting = self._get_morning_greeting(language)
            elif update_type == 'evening':
                greeting = self._get_evening_greeting(language)
            elif update_type == 'weekly':
                greeting = self._get_weekly_greeting(language)
            else:
                greeting = self._get_general_greeting(language)
            
            # Generate summary
            if update_type == 'weekly':
                summary = await self.bot.summarizer.create_news_digest(news_data, language)
            else:
                summary = await self.bot.summarizer.create_news_digest(news_data, language)
            
            # Send text message
            full_message = f"{greeting}\n\n{summary}"
            
            await self.bot.application.bot.send_message(
                chat_id=user_id,
                text=full_message,
                parse_mode='Markdown'
            )
            
            # Generate and send voice note
            voice_path = await self.bot.tts_handler.generate_voice_note(summary, language)
            if voice_path and os.path.exists(voice_path):
                with open(voice_path, 'rb') as voice_file:
                    await self.bot.application.bot.send_voice(
                        chat_id=user_id,
                        voice=voice_file
                    )
                os.remove(voice_path)
            
            logger.info(f"Sent {update_type} news to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending scheduled news to user {user_id}: {e}")
    
    def _get_morning_greeting(self, language: str) -> str:
        """Get morning greeting based on language"""
        greetings = {
            'hindi': "🌅 सुप्रभात! आज की ताज़ा खबरें:",
            'english': "🌅 Good morning! Here's your daily news update:",
            'hinglish': "🌅 Good morning bhai! Aaj ki fresh news:"
        }
        return greetings.get(language, greetings['english'])
    
    def _get_evening_greeting(self, language: str) -> str:
        """Get evening greeting based on language"""
        greetings = {
            'hindi': "🌆 शुभ संध्या! आज की शाम की खबरें:",
            'english': "🌆 Good evening! Here's your evening news update:",
            'hinglish': "🌆 Good evening bhai! Shaam ki news:"
        }
        return greetings.get(language, greetings['english'])
    
    def _get_weekly_greeting(self, language: str) -> str:
        """Get weekly greeting based on language"""
        greetings = {
            'hindi': "📅 सप्ताहिक समाचार सारांश:",
            'english': "📅 Your weekly news digest:",
            'hinglish': "📅 Weekly news digest, bhai:"
        }
        return greetings.get(language, greetings['english'])
    
    def _get_general_greeting(self, language: str) -> str:
        """Get general greeting based on language"""
        greetings = {
            'hindi': "📰 समाचार अपडेट:",
            'english': "📰 News Update:",
            'hinglish': "📰 News update, bhai:"
        }
        return greetings.get(language, greetings['english'])