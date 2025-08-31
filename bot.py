import os
import json
import sqlite3
import logging
import asyncio
import schedule
import time
import fcntl  # Add this import
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv

# Import our custom modules
from news_scraper import NewsScraper
from news_summarizer import NewsSummarizer
from tts_handler import TTSHandler
from stt_handler import STTHandler
from user_preferences import UserPreferences
from scheduler import NewsScheduler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class NewsBhaiBot:
    # In the NewsBhaiBot class, modify the __init__ method
    def __init__(self, token=None):
        self.token = token or os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("Please set TELEGRAM_BOT_TOKEN in your .env file or provide it as a parameter")
        
        # Initialize components
        self.user_prefs = UserPreferences()
        self.news_scraper = NewsScraper()
        # Disable auto scraping on startup
        self.news_scraper.set_auto_scrape(False)
        self.summarizer = NewsSummarizer()
        self.tts_handler = TTSHandler()
        self.stt_handler = STTHandler()
        self.scheduler = NewsScheduler(self)
        
        # Flag to track if test message has been sent
        self.test_message_sent = False
        
        # Create application
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        
        # Start cache cleaning scheduler
        self.cache_cleaning_task = None
    
    def setup_handlers(self):
        """Set up all command and message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("news", self.news_command))
        self.application.add_handler(CommandHandler("topics", self.topics_command))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        
        welcome_message = f"""🙏 Namaste {user_name}! Welcome to News Bhai!

I'm your personal news buddy who will keep you updated with current affairs in your preferred language and style.

🔹 What I can do:
• Get personalized news updates
• Send news as voice notes
• Answer your questions about current events
• Support Hindi, English, and Hinglish

🔹 Get started:
/settings - Set your preferences
/news - Get latest news
/topics - Choose your interests
/help - Show all commands

Let's set up your preferences first! 👇"""
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Set Preferences", callback_data="setup_preferences")],
            [InlineKeyboardButton("📰 Get Sample News", callback_data="sample_news")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """🤖 News Bhai Commands:

📰 News Commands:
/news - Get latest personalized news
/topics - Choose your news topics

⚙️ Settings:
/settings - Manage your preferences

💬 Chat Features:
• Send text: Ask about any news topic
• Send voice: Ask questions via voice note
• I'll respond with both text and voice!

🔹 Supported Languages:
• Hindi (हिंदी)
• English
• Hinglish (Mix of both)

🔹 Available Topics:
• Politics • Technology • Sports
• Finance • Entertainment • Health
• International • Business

Just type your question or send a voice note! 🎤"""
        
        await update.message.reply_text(help_text)
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user_id = update.effective_user.id
        prefs = self.user_prefs.get_user_preferences(user_id)
        
        settings_text = f"""⚙️ Your Current Settings:

🌐 Language: {prefs.get('language', 'Not set')}
📊 Topics: {', '.join(prefs.get('topics', ['Not set']))}
⏰ Frequency: {prefs.get('frequency', 'Not set')}

What would you like to change?"""
        
        keyboard = [
            [InlineKeyboardButton("🌐 Language", callback_data="set_language")],
            [InlineKeyboardButton("📊 Topics", callback_data="set_topics")],
            [InlineKeyboardButton("⏰ Frequency", callback_data="set_frequency")],
            [InlineKeyboardButton("🔄 Reset All", callback_data="reset_settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(settings_text, reply_markup=reply_markup)
    
    async def news_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /news command"""
        user_id = update.effective_user.id
        await self.send_personalized_news(user_id, update)
    
    async def topics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /topics command"""
        topics_text = """📊 Available News Topics:

Choose the topics you're interested in:"""
        
        keyboard = [
            [InlineKeyboardButton("🏛️ Politics", callback_data="topic_politics"),
             InlineKeyboardButton("💻 Technology", callback_data="topic_technology")],
            [InlineKeyboardButton("⚽ Sports", callback_data="topic_sports"),
             InlineKeyboardButton("💰 Finance", callback_data="topic_finance")],
            [InlineKeyboardButton("🎬 Entertainment", callback_data="topic_entertainment"),
             InlineKeyboardButton("🏥 Health", callback_data="topic_health")],
            [InlineKeyboardButton("🌍 International", callback_data="topic_international"),
             InlineKeyboardButton("🏢 Business", callback_data="topic_business")],
            [InlineKeyboardButton("✅ Done", callback_data="topics_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(topics_text, reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks with improved logging"""
        query = update.callback_query
        
        try:
            await query.answer()
        except telegram.error.BadRequest as e:
            # Handle "Query is too old" errors gracefully
            logger.warning(f"Could not answer callback query: {e}")
            # Continue processing the callback anyway
        
        callback_data = query.data
        user_id = query.from_user.id
        
        # Add detailed logging
        logger.info(f"Button callback received: {callback_data} from user {user_id}")
        
        try:
            # Handle topic selection
            if callback_data.startswith("topic_"):
                logger.info(f"Processing topic selection: {callback_data}")
                topic = callback_data.replace("topic_", "")
                current_topics = self.user_prefs.get_user_topics(user_id)
                
                if topic in current_topics:
                    # Remove topic if already selected
                    logger.info(f"Removing topic {topic} for user {user_id}")
                    self.user_prefs.remove_user_topic(user_id, topic)
                else:
                    # Add topic if not selected
                    logger.info(f"Adding topic {topic} for user {user_id}")
                    self.user_prefs.add_user_topic(user_id, topic)
                
                # Show updated topic options
                await self.show_topic_options(query)
                return
            
            # Handle other callbacks with detailed logging
            if callback_data == "setup_preferences":
                logger.info(f"Starting preferences setup for user {user_id}")
                await self.setup_preferences_flow(query)
            elif callback_data == "set_topics":
                logger.info(f"Showing topic options for user {user_id}")
                await self.show_topic_options(query)
            elif callback_data == "sample_news":
                logger.info(f"Sending sample news for user {user_id}")
                await self.send_sample_news(query)
            elif callback_data == "set_language":
                logger.info(f"Showing language options for user {user_id}")
                await self.show_language_options(query)
            elif callback_data == "set_frequency":
                logger.info(f"Showing frequency options for user {user_id}")
                await self.show_frequency_options(query)
            elif callback_data.startswith("lang_"):
                language = callback_data.split("_")[1]
                logger.info(f"Setting language to {language} for user {user_id}")
                await self.set_user_language(user_id, language, query)
            elif callback_data.startswith("freq_"):
                frequency = callback_data.split("_")[1]
                logger.info(f"Setting frequency to {frequency} for user {user_id}")
                await self.set_user_frequency(user_id, frequency, query)
            elif callback_data == "topics_done":
                logger.info(f"Topics selection completed for user {user_id}")
                # Handle the Done button after topic selection
                await self.show_frequency_options(query)
            else:
                logger.warning(f"Unknown callback data received: {callback_data} from user {user_id}")
        except Exception as e:
            logger.error(f"Error in button_callback: {e}")
            # Provide feedback to user when an error occurs
            try:
                await query.edit_message_text("Sorry, an error occurred. Please try again or use /start to restart.")
            except Exception:
                # If we can't edit the message, try to send a new one
                try:
                    await query.message.reply_text("Sorry, an error occurred. Please try again or use /start to restart.")
                except Exception as e2:
                    logger.error(f"Failed to notify user of error: {e2}")
    
    async def setup_preferences_flow(self, query):
        """Start the preferences setup flow"""
        text = """🌐 Let's set up your language preference first!

Choose your preferred language:"""
        
        keyboard = [
            [InlineKeyboardButton("🇮🇳 Hindi (हिंदी)", callback_data="lang_hindi")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")],
            [InlineKeyboardButton("🔄 Hinglish (Mix)", callback_data="lang_hinglish")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def show_language_options(self, query):
        """Show language selection options"""
        text = "🌐 Choose your preferred language:"
        
        keyboard = [
            [InlineKeyboardButton("🇮🇳 Hindi (हिंदी)", callback_data="lang_hindi")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")],
            [InlineKeyboardButton("🔄 Hinglish (Mix)", callback_data="lang_hinglish")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def show_topic_options(self, query):
        """Show topic selection options"""
        user_id = query.from_user.id
        current_topics = self.user_prefs.get_user_topics(user_id)
        
        all_topics = {
            'politics': '🏛️ Politics',
            'business': '🏢 Business',
            'technology': '💻 Technology',
            'sports': '⚽ Sports',
            'entertainment': '🎬 Entertainment',
            'health': '🏥 Health',
            'international': '🌍 International',
            'current_affairs': '📰 Current Affairs'
        }
        
        topics_text = "📚 Select your news topics of interest:\n"
        topics_text += "(You can select multiple topics)"
        
        keyboard = [
            [InlineKeyboardButton(f"{all_topics['politics']} {'✅' if 'politics' in current_topics else ''}", callback_data="topic_politics"),
             InlineKeyboardButton(f"{all_topics['technology']} {'✅' if 'technology' in current_topics else ''}", callback_data="topic_technology")],
            [InlineKeyboardButton(f"{all_topics['sports']} {'✅' if 'sports' in current_topics else ''}", callback_data="topic_sports"),
             InlineKeyboardButton(f"{all_topics['entertainment']} {'✅' if 'entertainment' in current_topics else ''}", callback_data="topic_entertainment")],
            [InlineKeyboardButton(f"{all_topics['health']} {'✅' if 'health' in current_topics else ''}", callback_data="topic_health"),
             InlineKeyboardButton(f"{all_topics['international']} {'✅' if 'international' in current_topics else ''}", callback_data="topic_international")],
            [InlineKeyboardButton(f"{all_topics['business']} {'✅' if 'business' in current_topics else ''}", callback_data="topic_business"),
             InlineKeyboardButton(f"{all_topics['current_affairs']} {'✅' if 'current_affairs' in current_topics else ''}", callback_data="topic_current_affairs")],
            [InlineKeyboardButton("✅ Done", callback_data="topics_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(topics_text, reply_markup=reply_markup)
    
    async def show_frequency_options(self, query):
        """Show frequency selection options"""
        text = "⏰ How often would you like to receive news updates?"
        
        keyboard = [
            [InlineKeyboardButton("📅 Once a day", callback_data="freq_daily")],
            [InlineKeyboardButton("📅 Twice a day", callback_data="freq_twice_daily")],
            [InlineKeyboardButton("📅 Weekly", callback_data="freq_weekly")],
            [InlineKeyboardButton("🔔 On request only", callback_data="freq_on_request")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def set_user_language(self, user_id: int, language: str, query):
        """Set user's language preference"""
        self.user_prefs.update_user_preference(user_id, 'language', language)
        
        lang_names = {
            'hindi': 'Hindi (हिंदी)',
            'english': 'English',
            'hinglish': 'Hinglish (Mix)'
        }
        
        await query.edit_message_text(
            f"✅ Language set to {lang_names[language]}!\n\nNow let's choose your topics of interest.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Choose Topics", callback_data="set_topics")]
            ])
        )
    
    async def set_user_frequency(self, user_id: int, frequency: str, query):
        """Set user's update frequency preference"""
        self.user_prefs.update_user_preference(user_id, 'frequency', frequency)
        
        freq_names = {
            'daily': 'Once a day',
            'twice_daily': 'Twice a day',
            'weekly': 'Weekly',
            'on_request': 'On request only'
        }
        
        await query.edit_message_text(
            f"✅ Update frequency set to {freq_names[frequency]}!\n\n🎉 Setup complete! You can now use /news to get your personalized updates."
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages from users"""
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Check if it's a news-related query
        if any(keyword in user_message.lower() for keyword in ['news', 'kya hua', 'what happened', 'update', 'bhai']):
            await self.handle_news_query(user_id, user_message, update)
        else:
            await update.message.reply_text(
                "🤔 I'm specialized in news updates! Try asking about current events or use /news for latest updates."
            )
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages from users"""
        user_id = update.effective_user.id
        
        try:
            # Download voice file
            voice_file = await update.message.voice.get_file()
            voice_path = f"temp_voice_{user_id}.ogg"
            await voice_file.download_to_drive(voice_path)
            
            # Transcribe voice to text
            transcribed_text = await self.stt_handler.transcribe_audio(voice_path)
            
            # Clean up temp file
            os.remove(voice_path)
            
            if transcribed_text:
                await update.message.reply_text(f"🎤 I heard: \"{transcribed_text}\"\n\nLet me get that news for you...")
                await self.handle_news_query(user_id, transcribed_text, update)
            else:
                await update.message.reply_text("😅 Sorry, I couldn't understand the audio. Please try again or send a text message.")
                
        except Exception as e:
            logger.error(f"Error handling voice message: {e}")
            await update.message.reply_text("😅 Sorry, there was an error processing your voice message. Please try again.")
    
    async def handle_news_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle news query and send news"""
        user_id = update.effective_user.id
        prefs = self.user_prefs.get_user_preferences(user_id)
        language = prefs.get('language', 'english')
        topics = prefs.get('topics', [])
        
        if not topics:
            # If no topics selected, prompt user to set preferences
            keyboard = [[InlineKeyboardButton("⚙️ Set My Preferences", callback_data="setup_preferences")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "You haven't set your news preferences yet. Set them up to get personalized news!",
                reply_markup=reply_markup
            )
            return
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # Get news based on user preferences
            news_items = []
            for topic in topics:
                # Add current affairs special handling
                if topic == 'current_affairs':
                    current_news = await self.news_scraper.scrape_current_affairs()
                    news_items.extend(current_news)
                else:
                    topic_news = await self.news_scraper.get_latest_news([topic])
                    news_items.extend(topic_news)
            
            if not news_items:
                await update.message.reply_text("Sorry, couldn't find any news matching your preferences right now.")
                return
            
            # Summarize news
            summary = await self.summarizer.create_news_digest(news_items, language)
            
            # Send text summary
            await update.message.reply_text(f"📰 **Your News Update**\n\n{summary}")
            
            # Generate and send voice note
            voice_path = await self.tts_handler.generate_voice_note(summary, language)
            if voice_path and os.path.exists(voice_path):
                with open(voice_path, 'rb') as voice_file:
                    await update.message.reply_voice(voice_file)
                os.remove(voice_path)
                
        except Exception as e:
            logger.error(f"Error handling news query: {e}")
            await update.message.reply_text("😅 Sorry, couldn't fetch news right now. Try again later!")
    
    # Add this method to the NewsBhaiBot class
    async def send_personalized_news(self, user_id: int, update: Update):
        """Send personalized news to user with proper error handling"""
        try:
            # Show typing indicator immediately
            await update.message.reply_text("🔍 Fetching your personalized news... Please wait a moment.")
            await update.effective_chat.send_chat_action(action="typing")
            
            prefs = self.user_prefs.get_user_preferences(user_id)
            language = prefs.get('language', 'english')
            topics = prefs.get('topics', ['general'])
            
            # Enable auto scraping only when explicitly requested
            self.news_scraper.set_auto_scrape(True)
            
            try:
                # Get latest news with retry mechanism
                news_data = await self.news_scraper.get_latest_news(topics, limit=15)
                
                # Disable auto scraping after fetching
                self.news_scraper.set_auto_scrape(False)
                
                if not news_data:
                    await update.message.reply_text("😅 No news available right now, bhai! Try again later.")
                    return
                
                # Summarize news for 30-second voice note
                summary = await self.summarizer.create_news_digest(news_data, language, max_length=200)
                
                # Send text summary first
                await update.message.reply_text(f"📰 **Your News Update**\n\n{summary}")
                
                # Generate and send 30-second voice note
                voice_path = await self.tts_handler.generate_voice_note(summary, language, max_duration=30)
                if voice_path and os.path.exists(voice_path):
                    with open(voice_path, 'rb') as voice_file:
                        await update.message.reply_voice(voice_file, caption="🎧 Your 30-second news summary")
                    os.remove(voice_path)
                else:
                    await update.message.reply_text("📝 Voice note generation failed, but here's your text summary above!")
                    
            except Exception as e:
                logger.error(f"Error in news fetching: {e}")
                await update.message.reply_text("😅 Sorry bhai, couldn't fetch news right now. Try again later!")
                # Make sure to disable auto scraping in case of error
                self.news_scraper.set_auto_scrape(False)
            
        except Exception as e:
            logger.error(f"Error setting up news fetch: {e}")
            await update.message.reply_text("😅 Sorry bhai, couldn't start fetching news. Try again later!")
    
    async def send_sample_news(self, query):
        """Send a sample news update"""
        sample_news = """📰 **Sample News Update**

🏛️ **Politics**: Bhai, aaj Parliament mein kuch important bills discuss hue hain. Opposition ne kuch points raise kiye hain budget ke baare mein.

💻 **Technology**: Tech world mein ek naya AI model launch hua hai jo kaafi promising lag raha hai. Indian startups bhi is field mein aage badh rahe hain.

⚽ **Sports**: Cricket team ki practice chal rahi hai upcoming series ke liye. Players ka form achha dikh raha hai.

Yeh tha aaj ka quick update! Set up your preferences to get personalized news like this! 🎯"""
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Set My Preferences", callback_data="setup_preferences")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # First send as text
        await query.edit_message_text(sample_news, reply_markup=reply_markup)
        
        # Then send as voice note
        try:
            # Get chat ID from the query
            chat_id = query.message.chat_id
            
            # Generate voice note (using hinglish as it's a mix)
            voice_path = await self.tts_handler.generate_voice_note(sample_news, 'hinglish')
            
            if voice_path and os.path.exists(voice_path):
                # Send voice note
                with open(voice_path, 'rb') as voice_file:
                    await query.bot.send_voice(chat_id=chat_id, voice=voice_file, caption="🎧 Here's your audio news update!")
                # Clean up the file
                os.remove(voice_path)
        except Exception as e:
            logger.error(f"Error sending sample news voice note: {e}")
    
    def run(self):
        """Start the bot"""
        logger.info("Starting News Bhai Bot...")
        
        # Start the scheduler
        self.scheduler.start()
        logger.info("Scheduler started")
        
        # Run the application with proper async handling
        self.application.run_polling()
    
    async def send_startup_test_message(self):
        """Send a test message to active users on startup"""
        try:
            logger.info("Sending startup test message...")
            
            # Get active users
            active_users = self.user_prefs.get_active_users()
            
            if not active_users:
                logger.info("No active users found to send test message")
                return
            
            # Create a sample news for testing
            sample_news = {
                'title': '🚀 News Bhai Bot is Online!',
                'content': 'Your personal news assistant is ready to deliver the latest updates. Use /news to get started!',
                'source': 'System',
                'timestamp': datetime.now().isoformat()
            }
            
            for user_id in active_users[:5]:  # Limit to first 5 users
                try:
                    # Get user preferences
                    prefs = self.user_prefs.get_user_preferences(user_id)
                    language = prefs.get('language', 'english')
                    
                    # Send text message
                    message = f"🎉 **{sample_news['title']}**\n\n{sample_news['content']}"
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                    
                    # Generate and send voice note
                    voice_path = self.tts_handler.text_to_speech(
                        sample_news['content'], 
                        language
                    )
                    
                    if voice_path and os.path.exists(voice_path):
                        with open(voice_path, 'rb') as voice_file:
                            await self.application.bot.send_voice(
                                chat_id=user_id, 
                                voice=voice_file, 
                                caption="🎧 Here's your audio news update!"
                            )
                        # Clean up the file
                        os.remove(voice_path)
                        
                    logger.info(f"Sent startup message to user {user_id}")
                    
                except Exception as e:
                    logger.error(f"Error sending startup message to user {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in send_startup_test_message: {e}")
    
    async def clean_cache(self):
        """Clean temporary files created by the bot"""
        try:
            import tempfile
            import glob
            
            temp_dir = tempfile.gettempdir()
            logger.info(f"Cleaning cache in {temp_dir}")
            
            # Clean voice note files
            voice_patterns = [
                os.path.join(temp_dir, "voice_note_*.ogg"),
                os.path.join(temp_dir, "voice_note_*.wav")
            ]
            
            files_removed = 0
            for pattern in voice_patterns:
                for file_path in glob.glob(pattern):
                    try:
                        # Check if file is older than 5 minutes to avoid deleting files in use
                        file_age = time.time() - os.path.getmtime(file_path)
                        if file_age > 300:  # 5 minutes in seconds
                            os.remove(file_path)
                            files_removed += 1
                    except Exception as e:
                        logger.warning(f"Could not remove cache file {file_path}: {e}")
            
            if files_removed > 0:
                logger.info(f"Removed {files_removed} cache files")
                
        except Exception as e:
            logger.error(f"Error cleaning cache: {e}")
    
    async def start_cache_cleaning(self):
        """Start periodic cache cleaning"""
        try:
            # Cancel any existing task
            if hasattr(self, 'cache_cleaning_task') and self.cache_cleaning_task and not self.cache_cleaning_task.done():
                self.cache_cleaning_task.cancel()
            
            # Run initial cleanup
            await self.clean_cache()
            
            # Schedule periodic cleanup
            async def periodic_cleanup():
                while True:
                    try:
                        await asyncio.sleep(120)  # 2 minutes
                        await self.clean_cache()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Error in periodic cache cleaning: {e}")
                        await asyncio.sleep(60)  # Wait a bit before retrying
            
            # Start the periodic task
            self.cache_cleaning_task = asyncio.create_task(periodic_cleanup())
            logger.info("Started periodic cache cleaning every 2 minutes")
            
        except Exception as e:
            logger.error(f"Failed to start cache cleaning: {e}")

# Remove all duplicate code and fix the main execution block
if __name__ == '__main__':
    # Check if bot is already running
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'python.*bot.py'], capture_output=True, text=True)
        if result.stdout.strip():
            print("Bot is already running! Please stop the existing instance first.")
            print("Use: pkill -f 'python.*bot.py' to stop it.")
            exit(1)
    except:
        pass  # pgrep might not be available on all systems
    
    # Main bot execution with proper try-except structure
    try:
        import sys
        token = sys.argv[1] if len(sys.argv) > 1 else None
        bot = NewsBhaiBot(token)
        
        async def start_bot():
            """Async startup function"""
            try:
                # Run startup tasks
                await bot.send_startup_test_message()
                await bot.start_cache_cleaning()
                
                logger.info("Bot startup tasks completed")
                
            except Exception as e:
                logger.error(f"Error in startup tasks: {e}")
        
        # Create event loop and run startup tasks
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Schedule startup tasks
        loop.create_task(start_bot())
        
        # Start the bot (this will block)
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"Error: {e}")
        print("\nMake sure you have:")
        print("1. Created a .env file with TELEGRAM_BOT_TOKEN")
        print("2. Installed all dependencies: pip install -r requirements.txt")
        print("3. Set up your database properly")
    finally:
        # Clean up lock file
        try:
            os.unlink(lock_file)
        except:
            pass