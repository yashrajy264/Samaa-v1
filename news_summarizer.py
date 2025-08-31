import logging
import re
import random
from typing import List, Dict, Optional
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
import torch

logger = logging.getLogger(__name__)

class NewsSummarizer:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.summarizer = None
        self.tokenizer = None
        self.model = None
        self._load_models()
        
        # Casual phrases for different languages
        self.casual_intros = {
            'hindi': [
                "अरे भाई, आज की खबर सुनो -",
                "भाई पता है आज क्या हुआ?",
                "सुनो भाई, ये हुआ है आज -",
                "अरे यार, आज की बड़ी खबर ये है -"
            ],
            'english': [
                "Hey bro, here's what happened today -",
                "Bhai, you know what's going on?",
                "Listen up, here's the latest -",
                "Yo, big news today -"
            ],
            'hinglish': [
                "Arre bhai, aaj ki news sun -",
                "Bhai pata hai aaj kya hua?",
                "Sun yaar, aaj ka update -",
                "Arre, aaj ki badi news ye hai -"
            ]
        }
        
        self.casual_connectors = {
            'hindi': ["और फिर", "इसके बाद", "अब बात ये है", "और सुनो"],
            'english': ["And then", "Also", "Plus", "Oh and"],
            'hinglish': ["Aur phir", "Aur sun", "Plus yaar", "Arre aur"]
        }
    
    def _load_models(self):
        """Load summarization models"""
        try:
            # Try to load multilingual model first
            model_name = "facebook/mbart-large-50-many-to-many-mmt"
            
            logger.info(f"Loading summarization model: {model_name}")
            
            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            
            # Create pipeline
            self.summarizer = pipeline(
                "summarization",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if self.device == "cuda" else -1,
                max_length=150,
                min_length=30,
                do_sample=True,
                temperature=0.7
            )
            
            logger.info("Summarization model loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading multilingual model, trying fallback: {e}")
            try:
                # Fallback to English-only model
                model_name = "facebook/bart-large-cnn"
                self.summarizer = pipeline(
                    "summarization",
                    model=model_name,
                    device=0 if self.device == "cuda" else -1,
                    max_length=150,
                    min_length=30,
                    do_sample=True,
                    temperature=0.7
                )
                logger.info("Fallback summarization model loaded")
            except Exception as e2:
                logger.error(f"Failed to load any summarization model: {e2}")
                self.summarizer = None
    
    async def summarize_news(self, news_data: List[Dict], language: str, query: str = "") -> str:
        """Summarize news data into a casual, friend-like response"""
        if not news_data:
            return self._get_no_news_message(language)
        
        try:
            # Combine and clean news content
            combined_text = self._prepare_text_for_summarization(news_data)
            
            # Generate summary
            if self.summarizer:
                summary = await self._generate_ai_summary(combined_text, language)
            else:
                summary = self._generate_fallback_summary(news_data, language)
            
            # Make it casual and friend-like
            casual_summary = self._make_casual(summary, language, query)
            
            return casual_summary
            
        except Exception as e:
            logger.error(f"Error summarizing news: {e}")
            return self._generate_fallback_summary(news_data, language)
    
    async def create_news_digest(self, news_data: List[Dict], language: str) -> str:
        """Create a comprehensive news digest"""
        if not news_data:
            return self._get_no_news_message(language)
        
        try:
            # Group news by topics
            topic_groups = self._group_by_topics(news_data)
            
            digest_parts = []
            intro = random.choice(self.casual_intros.get(language, self.casual_intros['english']))
            digest_parts.append(intro)
            
            for topic, items in topic_groups.items():
                if items:
                    topic_summary = await self._summarize_topic_group(items, language, topic)
                    if topic_summary:
                        digest_parts.append(topic_summary)
            
            # Add casual ending
            ending = self._get_casual_ending(language)
            digest_parts.append(ending)
            
            return "\n\n".join(digest_parts)
            
        except Exception as e:
            logger.error(f"Error creating news digest: {e}")
            return self._generate_fallback_summary(news_data, language)
    
    def _prepare_text_for_summarization(self, news_data: List[Dict]) -> str:
        """Prepare and clean text for summarization"""
        texts = []
        
        for item in news_data[:5]:  # Limit to 5 items to avoid token limits
            content = item.get('content', '')
            # Clean the text
            clean_content = re.sub(r'http\S+|www\S+|@\w+|#\w+', '', content)
            clean_content = re.sub(r'\s+', ' ', clean_content).strip()
            
            if len(clean_content) > 50:  # Only include substantial content
                texts.append(clean_content)
        
        combined = ' '.join(texts)
        
        # Truncate if too long (BART has token limits)
        if len(combined) > 1000:
            combined = combined[:1000] + "..."
        
        return combined
    
    async def _generate_ai_summary(self, text: str, language: str) -> str:
        """Generate AI-powered summary"""
        try:
            # Generate summary using the model
            result = self.summarizer(text, max_length=130, min_length=30, do_sample=True)
            summary = result[0]['summary_text']
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating AI summary: {e}")
            # Return first few sentences as fallback
            sentences = text.split('.')[:3]
            return '. '.join(sentences) + '.'
    
    def _generate_fallback_summary(self, news_data: List[Dict], language: str) -> str:
        """Generate a simple summary when AI models fail"""
        summaries = []
        
        for item in news_data[:3]:  # Take top 3 items
            title = item.get('title', '')
            content = item.get('content', '')
            
            # Extract first sentence or use title
            if title:
                summary_text = title
            else:
                sentences = content.split('.')
                summary_text = sentences[0] if sentences else content[:100]
            
            summaries.append(summary_text.strip())
        
        # Combine with casual language
        intro = random.choice(self.casual_intros.get(language, self.casual_intros['english']))
        connector = random.choice(self.casual_connectors.get(language, self.casual_connectors['english']))
        
        result = f"{intro}\n\n"
        result += f"\n\n{connector} ".join(summaries)
        
        return result
    
    def _make_casual(self, summary: str, language: str, query: str = "") -> str:
        """Make the summary more casual and friend-like"""
        # Add casual intro
        intro = random.choice(self.casual_intros.get(language, self.casual_intros['english']))
        
        # Add context if it's a response to a query
        if query:
            if language == 'hindi':
                context = f"तुमने पूछा था '{query}' के बारे में, तो सुनो -"
            elif language == 'hinglish':
                context = f"Tumne pucha tha '{query}' ke baare mein, toh sun -"
            else:
                context = f"You asked about '{query}', so here's what I found -"
            
            intro = context
        
        # Add casual ending based on language
        ending = self._get_casual_ending(language)
        
        # Combine everything
        casual_summary = f"{intro}\n\n{summary}\n\n{ending}"
        
        return casual_summary
    
    def _group_by_topics(self, news_data: List[Dict]) -> Dict[str, List[Dict]]:
        """Group news items by topics"""
        groups = {}
        
        for item in news_data:
            topic = item.get('topic', 'general')
            if topic not in groups:
                groups[topic] = []
            groups[topic].append(item)
        
        return groups
    
    async def _summarize_topic_group(self, items: List[Dict], language: str, topic: str) -> str:
        """Summarize a group of news items from the same topic"""
        if not items:
            return ""
        
        # Get topic emoji and name
        topic_info = self._get_topic_info(topic, language)
        
        # Combine content from this topic
        topic_content = self._prepare_text_for_summarization(items)
        
        # Generate summary for this topic
        if self.summarizer and len(topic_content) > 100:
            try:
                result = self.summarizer(topic_content, max_length=80, min_length=20)
                topic_summary = result[0]['summary_text']
            except:
                # Fallback to first item's content
                topic_summary = items[0].get('title', items[0].get('content', '')[:100])
        else:
            topic_summary = items[0].get('title', items[0].get('content', '')[:100])
        
        return f"{topic_info['emoji']} **{topic_info['name']}**: {topic_summary}"
    
    def _get_topic_info(self, topic: str, language: str) -> Dict[str, str]:
        """Get topic emoji and localized name"""
        topic_map = {
            'politics': {'emoji': '🏛️', 'hindi': 'राजनीति', 'english': 'Politics', 'hinglish': 'Politics'},
            'technology': {'emoji': '💻', 'hindi': 'तकनीक', 'english': 'Technology', 'hinglish': 'Technology'},
            'sports': {'emoji': '⚽', 'hindi': 'खेल', 'english': 'Sports', 'hinglish': 'Sports'},
            'finance': {'emoji': '💰', 'hindi': 'वित्त', 'english': 'Finance', 'hinglish': 'Finance'},
            'entertainment': {'emoji': '🎬', 'hindi': 'मनोरंजन', 'english': 'Entertainment', 'hinglish': 'Entertainment'},
            'health': {'emoji': '🏥', 'hindi': 'स्वास्थ्य', 'english': 'Health', 'hinglish': 'Health'},
            'international': {'emoji': '🌍', 'hindi': 'अंतर्राष्ट्रीय', 'english': 'International', 'hinglish': 'International'},
            'business': {'emoji': '🏢', 'hindi': 'व्यापार', 'english': 'Business', 'hinglish': 'Business'},
            'general': {'emoji': '📰', 'hindi': 'सामान्य', 'english': 'General', 'hinglish': 'General'}
        }
        
        info = topic_map.get(topic, topic_map['general'])
        return {
            'emoji': info['emoji'],
            'name': info.get(language, info['english'])
        }
    
    def _get_casual_ending(self, language: str) -> str:
        """Get a casual ending for the summary"""
        endings = {
            'hindi': [
                "बस यही था आज का अपडेट! 👍",
                "और कुछ चाहिए तो बताना भाई! 😊",
                "हो गया आज का न्यूज़! 📰"
            ],
            'english': [
                "That's your update for today! 👍",
                "Let me know if you need anything else, bro! 😊",
                "That's all for now! 📰"
            ],
            'hinglish': [
                "Bass yahi tha aaj ka update! 👍",
                "Aur kuch chahiye toh batana bhai! 😊",
                "Ho gaya aaj ka news! 📰"
            ]
        }
        
        return random.choice(endings.get(language, endings['english']))
    
    def _get_no_news_message(self, language: str) -> str:
        """Get message when no news is available"""
        messages = {
            'hindi': "अरे भाई, अभी कोई खास खबर नहीं मिली। थोड़ी देर बाद ट्राई करना! 😅",
            'english': "Hey bro, couldn't find any news right now. Try again later! 😅",
            'hinglish': "Arre bhai, abhi koi khaas news nahi mili. Thodi der baad try karna! 😅"
        }
        
        return messages.get(language, messages['english'])