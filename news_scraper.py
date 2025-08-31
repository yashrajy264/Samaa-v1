import asyncio
import logging
import re
import random
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
# Remove Twitter/X scraping dependency
# import snscrape.modules.twitter as sntwitter  # REMOVED
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class NewsScraper:
    # Add more RSS feeds for better fallback coverage
    def __init__(self):
        # Flag to control if scraping should happen automatically
        self.auto_scrape_enabled = False
        
        # Popular Indian news handles on X (formerly Twitter)
        self.news_handles = {
            'general': ['ANI', 'ndtv', 'timesofindia', 'IndianExpress', 'htTweets'],
            'politics': ['ANI', 'ndtv', 'IndianExpress', 'republic', 'aajtak'],
            'technology': ['ETtech', 'YourStory', 'Inc42', 'Medianama', 'trak_in'],
            'sports': ['ESPNcricinfo', 'cricbuzz', 'KhelNow', 'IndiaToday_SPO'],
            'finance': ['ETMarkets', 'BloombergQuint', 'moneycontrolcom', 'livemint'],
            'entertainment': ['filmfare', 'BollywoodHungama', 'PinkvillaNews', 'ETimes'],
            'health': ['MoHFW_INDIA', 'WHO', 'timesofindia', 'ndtv'],
            'international': ['BBCWorld', 'Reuters', 'CNN', 'AlJazeera'],
            'business': ['ETNow', 'CNBCTV18News', 'BloombergQuint', 'BusinessLine']
        }
        
        # Expanded RSS feeds for better fallback coverage
        self.rss_feeds = {
            'general': [
                'https://feeds.feedburner.com/ndtvnews-top-stories',
                'https://timesofindia.indiatimes.com/rssfeedstopstories.cms',
                'https://www.hindustantimes.com/feeds/rss/news/latest.xml',
                'https://www.indiatoday.in/rss/home',
                'https://www.news18.com/rss/india.xml',
                'https://www.thehindu.com/news/feeder/default.rss',
                'https://indianexpress.com/feed/'
            ],
            'politics': [
                'https://timesofindia.indiatimes.com/rssfeeds/1898055.cms',
                'https://www.thehindu.com/news/national/feeder/default.rss',
                'https://www.indiatoday.in/rss/1206514',
                'https://www.news18.com/rss/politics.xml',
                'https://indianexpress.com/section/india/feed/'
            ],
            'technology': [
                'https://economictimes.indiatimes.com/tech/rss/feedsdefault.cms',
                'https://www.theverge.com/rss/index.xml',
                'https://www.digit.in/feed',
                'https://gadgets.ndtv.com/rss/feeds',
                'https://techcrunch.com/feed/',
                'https://www.wired.com/feed/rss'
            ],
            'sports': [
                'https://timesofindia.indiatimes.com/rssfeeds/4719148.cms',
                'https://www.espn.in/espn/rss/cricket/news',
                'https://sports.ndtv.com/rss/all',
                'https://www.sportskeeda.com/feed',
                'https://indianexpress.com/section/sports/feed/'
            ],
            'finance': [
                'https://economictimes.indiatimes.com/markets/rss/rssfeeds.cms',
                'https://www.livemint.com/rss/markets',
                'https://www.moneycontrol.com/rss/latestnews.xml',
                'https://www.business-standard.com/rss/markets-106.rss',
                'https://www.reuters.com/business/finance/rss'
            ],
            'entertainment': [
                'https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms',
                'https://www.bollywoodhungama.com/rss/bollywood-news.xml',
                'https://www.bollywoodhungama.com/rss/news',
                'https://indianexpress.com/section/entertainment/feed/',
                'https://www.hindustantimes.com/entertainment/feed'
            ],
            'health': [
                'https://timesofindia.indiatimes.com/rssfeeds/3908999.cms',
                'https://health.economictimes.indiatimes.com/rss',
                'https://www.healthline.com/nutrition/feed',
                'https://www.who.int/india/rss',
                'https://indianexpress.com/section/lifestyle/health/feed/'
            ],
            'international': [
                'https://timesofindia.indiatimes.com/rssfeeds/296589292.cms',
                'https://www.bbc.com/news/world/asia/india/rss.xml',
                'https://rss.cnn.com/rss/edition_world.rss',
                'https://feeds.feedburner.com/ndtvnews-world-news',
                'https://www.reuters.com/world/rss',
                'https://www.aljazeera.com/xml/rss/all.xml'
            ],
            'business': [
                'https://economictimes.indiatimes.com/industry/rss/industry.cms',
                'https://www.livemint.com/rss/companies',
                'https://www.business-standard.com/rss/companies-101.rss',
                'https://www.moneycontrol.com/rss/business.xml',
                'https://www.reuters.com/business/rss'
            ]
        }
    
    # Enable or disable auto scraping
    def set_auto_scrape(self, enabled: bool):
        self.auto_scrape_enabled = enabled
        logger.info(f"Auto scraping set to: {enabled}")
    
    async def get_latest_news(self, topics: List[str], limit: int = 10) -> List[Dict]:
        """Get latest news for specified topics"""
        all_news = []
        
        for topic in topics:
            try:
                topic_news = await self._scrape_topic_news(topic, limit // len(topics))
                all_news.extend(topic_news)
            except Exception as e:
                logger.error(f"Error scraping {topic} news: {e}")
                continue
        
        # Sort by timestamp and return most recent - fix datetime comparison
        all_news.sort(key=lambda x: x.get('timestamp', datetime.now(timezone.utc)), reverse=True)
        return all_news[:limit]
    
    async def search_news(self, query: str, topics: List[str], limit: int = 5) -> List[Dict]:
        """Search for news related to a specific query"""
        search_results = []
        
        # Extract keywords from query
        keywords = self._extract_keywords(query)
        
        for topic in topics:
            try:
                # Search in recent tweets from news handles
                topic_results = await self._search_topic_with_keywords(topic, keywords, limit)
                search_results.extend(topic_results)
            except Exception as e:
                logger.error(f"Error searching {topic} with query '{query}': {e}")
                continue
        
        # Filter and rank results by relevance
        relevant_results = self._rank_by_relevance(search_results, keywords)
        return relevant_results[:limit]
    
    async def _scrape_topic_news(self, topic: str, limit: int) -> List[Dict]:
        """Scrape news for a specific topic using RSS feeds only"""
        # Special handling for current affairs
        if topic == 'current_affairs':
            return await self.scrape_current_affairs(limit)
            
        news_items = []
        
        # Use RSS feeds directly - no more Twitter/X scraping
        logger.info(f"Scraping RSS feeds for topic: {topic}")
        rss_news = await self._scrape_rss_feed(topic)
        news_items.extend(rss_news)
        
        # Sort by timestamp and limit results - fix datetime comparison
        news_items.sort(key=lambda x: x.get('timestamp', datetime.now(timezone.utc)), reverse=True)
        return news_items[:limit]
    
    # REMOVED: _get_tweets_from_handle method - no longer needed
    
    async def _scrape_rss_feed(self, topic: str) -> List[Dict]:
        """Enhanced RSS feed scraping with better error handling"""
        news_items = []
        feeds = self.rss_feeds.get(topic, self.rss_feeds['general'])
        
        for feed_url in feeds:
            try:
                # Add user agent to avoid blocking
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(feed_url, timeout=15, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'xml')
                
                items = soup.find_all('item')[:8]  # Get more items per feed
                
                for item in items:
                    title = item.find('title')
                    description = item.find('description')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    
                    if title and description:
                        # Clean up description text
                        desc_text = description.text.strip()
                        if len(desc_text) > 300:
                            desc_text = desc_text[:300] + "..."
                        
                        # Extract domain name for source
                        source_name = self._extract_source_name(feed_url)
                        
                        news_items.append({
                            'title': title.text.strip(),
                            'content': desc_text,
                            'source': source_name,
                            'url': link.text.strip() if link else '',
                            'timestamp': self._parse_rss_date(pub_date.text) if pub_date else datetime.now(timezone.utc),
                            'topic': topic
                        })
                
                logger.info(f"Successfully scraped {len(items)} items from {source_name}")
                
            except Exception as e:
                logger.error(f"Error scraping RSS feed {feed_url}: {e}")
                continue
        
        return news_items
    
    def _extract_source_name(self, feed_url: str) -> str:
        """Extract a clean source name from RSS feed URL"""
        try:
            from urllib.parse import urlparse
            domain = urlparse(feed_url).netloc
            
            # Clean up common domain patterns
            domain = domain.replace('www.', '').replace('feeds.', '')
            
            # Map to readable names
            source_map = {
                'timesofindia.indiatimes.com': 'Times of India',
                'ndtv.com': 'NDTV',
                'hindustantimes.com': 'Hindustan Times',
                'indiatoday.in': 'India Today',
                'news18.com': 'News18',
                'thehindu.com': 'The Hindu',
                'indianexpress.com': 'Indian Express',
                'economictimes.indiatimes.com': 'Economic Times',
                'livemint.com': 'Live Mint',
                'moneycontrol.com': 'MoneyControl',
                'business-standard.com': 'Business Standard',
                'reuters.com': 'Reuters',
                'bbc.com': 'BBC',
                'cnn.com': 'CNN',
                'aljazeera.com': 'Al Jazeera'
            }
            
            return source_map.get(domain, domain.title())
        except:
            return 'RSS Feed'
    
    # Remove Twitter-specific methods
    # def _is_news_tweet(self, content: str) -> bool:  # REMOVED
    # def _extract_title(self, content: str) -> str:   # REMOVED - only needed for tweets
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from user query"""
        # Remove common words and extract meaningful keywords
        stop_words = {'what', 'how', 'when', 'where', 'why', 'who', 'is', 'are', 'was', 'were', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'about', 'kya', 'hai', 'hua', 'bhai', 'news', 'update'}
        
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords[:5]  # Limit to 5 most relevant keywords
    
    def _calculate_relevance(self, content: str, keywords: List[str]) -> float:
        """Calculate relevance score based on keyword matches"""
        content_lower = content.lower()
        score = 0
        
        for keyword in keywords:
            if keyword in content_lower:
                score += 1
                # Bonus for exact word match
                if f' {keyword} ' in f' {content_lower} ':
                    score += 0.5
        
        return score / len(keywords) if keywords else 0
    
    def _rank_by_relevance(self, results: List[Dict], keywords: List[str]) -> List[Dict]:
        """Rank results by relevance to search keywords"""
        for result in results:
            if 'relevance_score' not in result:
                result['relevance_score'] = self._calculate_relevance(result['content'], keywords)
        
        # Sort by relevance score, then by timestamp
        results.sort(key=lambda x: (x.get('relevance_score', 0), x.get('timestamp', datetime.min)), reverse=True)
        return results
    
    def _parse_rss_date(self, date_str: str) -> datetime:
        """Parse RSS date string to datetime object with timezone handling"""
        try:
            # Try common RSS date formats
            formats = [
                '%a, %d %b %Y %H:%M:%S %z',
                '%a, %d %b %Y %H:%M:%S GMT',
                '%Y-%m-%dT%H:%M:%S%z',
                '%Y-%m-%d %H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str.strip(), fmt)
                    # If the datetime is naive (no timezone), make it timezone-aware
                    if parsed_date.tzinfo is None:
                        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                    return parsed_date
                except ValueError:
                    continue
            
            # Return timezone-aware datetime for consistency
            return datetime.now(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)
    
    async def scrape_current_affairs(self, limit: int = 5) -> List[Dict]:
        """Scrape current affairs news from reliable sources"""
        # Make sure to use async libraries for HTTP requests
        # For example, use aiohttp instead of requests
        
        # Example modification:
        import aiohttp
        
        news_items = []
        
        # List of reliable current affairs sources
        current_affairs_sources = [
            'https://www.indiatoday.in/india',
            'https://timesofindia.indiatimes.com/india',
            'https://www.hindustantimes.com/india-news'
        ]
        
        async with aiohttp.ClientSession() as session:
            for source_url in current_affairs_sources:
                try:
                    # Fetch the webpage content
                    async with session.get(source_url, timeout=10, 
                                      headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}) as response:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Extract headlines based on common patterns in news websites
                        headlines = []
                        
                        # Look for article elements with headlines
                        for article in soup.find_all(['article', 'div'], class_=re.compile(r'(story|news-item|article|headline)', re.I)):
                            # Find headline element
                            headline_elem = article.find(['h1', 'h2', 'h3', 'a'], class_=re.compile(r'(headline|title)', re.I))
                            if not headline_elem:
                                headline_elem = article.find(['h1', 'h2', 'h3', 'a'])
                            
                            if headline_elem:
                                # Extract title and link
                                title = headline_elem.get_text().strip()
                                link = ''
                                
                                # Get the article URL
                                if headline_elem.name == 'a' and headline_elem.has_attr('href'):
                                    link = headline_elem['href']
                                    if not link.startswith('http'):
                                        # Handle relative URLs
                                        if link.startswith('/'):
                                            base_url = '/'.join(source_url.split('/')[:3])
                                            link = base_url + link
                                        else:
                                            link = source_url + '/' + link
                                else:
                                    link_elem = article.find('a')
                                    if link_elem and link_elem.has_attr('href'):
                                        link = link_elem['href']
                                        if not link.startswith('http'):
                                            # Handle relative URLs
                                            if link.startswith('/'):
                                                base_url = '/'.join(source_url.split('/')[:3])
                                                link = base_url + link
                                            else:
                                                link = source_url + '/' + link
                                        
                                        # Extract content snippet if available
                                        content = ''
                                        content_elem = article.find(['p', 'div'], class_=re.compile(r'(summary|content|description)', re.I))
                                        if content_elem:
                                            content = content_elem.get_text().strip()
                                        
                                        if title and len(title) > 10 and not any(h['title'] == title for h in headlines):
                                            headlines.append({
                                                'title': title,
                                                'content': content if content else title,
                                                'url': link,
                                                'source': source_url.split('/')[2],
                                                'timestamp': datetime.now(timezone.utc)
                                            })
                                            
                                            if len(headlines) >= limit:
                                                break
                                    
                                news_items.extend(headlines)
                                
                                # If we have enough news items, stop scraping more sources
                                if len(news_items) >= limit:
                                    break
                                    
                except Exception as e:
                    logger.error(f"Error scraping current affairs from {source_url}: {e}")
        
        # Format the news items to match the expected structure
        formatted_news = []
        for item in news_items[:limit]:
            formatted_news.append({
                'title': item['title'],
                'content': item['content'],
                'source': item['source'],
                'url': item['url'],
                'timestamp': item['timestamp'],
                'topic': 'current_affairs'
            })
        
        return formatted_news