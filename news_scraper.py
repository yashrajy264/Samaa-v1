import asyncio
import logging
import re
import random
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import snscrape.modules.twitter as sntwitter
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class NewsScraper:
    # Add more RSS feeds for better fallback coverage
    def __init__(self):
        # Flag to control if scraping should happen automatically
        self.auto_scrape_enabled = False
        
        # Popular Indian news handles on Twitter/X
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
                'https://www.news18.com/rss/india.xml'
            ],
            'politics': [
                'https://timesofindia.indiatimes.com/rssfeeds/1898055.cms',
                'https://www.thehindu.com/news/national/feeder/default.rss',
                'https://www.indiatoday.in/rss/1206514',
                'https://www.news18.com/rss/politics.xml'
            ],
            'technology': [
                'https://economictimes.indiatimes.com/tech/rss/feedsdefault.cms',
                'https://www.theverge.com/rss/index.xml',
                'https://www.digit.in/feed',
                'https://gadgets.ndtv.com/rss/feeds'
            ],
            'sports': [
                'https://timesofindia.indiatimes.com/rssfeeds/4719148.cms',
                'https://www.espn.in/espn/rss/cricket/news',
                'https://sports.ndtv.com/rss/all',
                'https://www.sportskeeda.com/feed'
            ],
            'finance': [
                'https://economictimes.indiatimes.com/markets/rss/rssfeeds.cms',
                'https://www.livemint.com/rss/markets',
                'https://www.moneycontrol.com/rss/latestnews.xml',
                'https://www.business-standard.com/rss/markets-106.rss'
            ],
            'entertainment': [
                'https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms',
                'https://www.filmfare.com/feed',
                'https://www.bollywoodhungama.com/rss/news',
                'https://indianexpress.com/section/entertainment/feed/'
            ],
            'health': [
                'https://timesofindia.indiatimes.com/rssfeeds/3908999.cms',
                'https://health.economictimes.indiatimes.com/rss',
                'https://www.healthline.com/nutrition/feed',
                'https://www.who.int/india/rss'
            ],
            'international': [
                'https://timesofindia.indiatimes.com/rssfeeds/296589292.cms',
                'https://www.bbc.com/news/world/asia/india/rss.xml',
                'https://rss.cnn.com/rss/edition_world.rss',
                'https://feeds.feedburner.com/ndtvnews-world-news'
            ],
            'business': [
                'https://economictimes.indiatimes.com/industry/rss/industry.cms',
                'https://www.livemint.com/rss/companies',
                'https://www.business-standard.com/rss/companies-101.rss',
                'https://www.moneycontrol.com/rss/business.xml'
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
        
        # Sort by timestamp and return most recent
        all_news.sort(key=lambda x: x.get('timestamp', datetime.now()), reverse=True)
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
        """Scrape news for a specific topic"""
        # Special handling for current affairs
        if topic == 'current_affairs':
            return await self.scrape_current_affairs(limit)
            
        news_items = []
        handles = self.news_handles.get(topic, self.news_handles['general'])
        
        # Try Twitter scraping first with retry mechanism
        twitter_success = False
        error_count = 0
        max_retries = 5
        
        for handle in handles[:3]:  # Limit to 3 handles per topic to avoid rate limiting
            if error_count >= max_retries:
                logger.warning(f"Max Twitter retry attempts ({max_retries}) reached for topic {topic}. Switching to RSS feeds.")
                break
                
            try:
                # Use snscrape to get recent tweets
                tweets = await self._get_tweets_from_handle(handle, limit // 3)
                
                if tweets:  # If we got tweets successfully
                    twitter_success = True
                    
                    for tweet in tweets:
                        if self._is_news_tweet(tweet['content']):
                            news_items.append({
                                'title': self._extract_title(tweet['content']),
                                'content': tweet['content'],
                                'source': f"@{handle}",
                                'url': tweet.get('url', ''),
                                'timestamp': tweet.get('date', datetime.now()),
                                'topic': topic
                            })
                else:
                    error_count += 1
                
            except Exception as e:
                logger.error(f"Error scraping handle @{handle}: {e}")
                error_count += 1
        
        # If Twitter scraping failed or didn't return enough results, use RSS fallback
        if not twitter_success or len(news_items) < limit:
            logger.info(f"Twitter scraping insufficient for topic {topic}. Using RSS fallback.")
            rss_news = await self._scrape_rss_feed(topic)
            news_items.extend(rss_news)
        
        return news_items
    
    async def _get_tweets_from_handle(self, handle: str, limit: int) -> List[Dict]:
        """Get recent tweets from a Twitter handle using snscrape with retry mechanism"""
        tweets = []
        max_retries = 5
        retry_count = 0
        timeout_seconds = 10
        
        while retry_count < max_retries:
            try:
                # Create search query for recent tweets from handle
                query = f"from:{handle} -filter:replies -filter:retweets"
                
                # Use snscrape to get tweets with better error handling
                scraper = sntwitter.TwitterSearchScraper(query)
                items_generator = scraper.get_items()
                
                # Add timeout protection
                start_time = datetime.now()
                tweet_count = 0
                
                for i, tweet in enumerate(items_generator):
                    # Check for timeout
                    if (datetime.now() - start_time).total_seconds() > timeout_seconds:
                        logger.warning(f"Timeout reached while scraping tweets from @{handle}")
                        break
                        
                    if i >= limit:
                        break
                    
                    # Only get tweets from last 24 hours
                    if tweet.date < datetime.now() - timedelta(days=1):
                        break
                    
                    tweets.append({
                        'content': tweet.rawContent,
                        'url': tweet.url,
                        'date': tweet.date,
                        'likes': tweet.likeCount,
                        'retweets': tweet.retweetCount
                    })
                    tweet_count += 1
                
                # If we got at least one tweet, consider it a success
                if tweet_count > 0:
                    return tweets
                
                # If we got no tweets but no error, increment retry count
                logger.warning(f"No tweets found for @{handle}, retry {retry_count+1}/{max_retries}")
                retry_count += 1
                
            except Exception as e:
                # Log error and retry
                logger.error(f"Error getting tweets from @{handle} (attempt {retry_count+1}/{max_retries}): {e}")
                logger.error(f"Error type: {type(e).__name__}")
                
                retry_count += 1
                if "404" in str(e) or "blocked" in str(e).lower():
                    logger.warning(f"Twitter API 404/blocked error for @{handle}, may be rate limited or API changed")
                    # If we get a 404/blocked error, increment retry count faster
                    retry_count += 1
                
                # Wait before retrying
                await asyncio.sleep(1)
        
        logger.error(f"Failed to get tweets from @{handle} after {max_retries} attempts")
        return []
    
    async def _search_topic_with_keywords(self, topic: str, keywords: List[str], limit: int) -> List[Dict]:
        """Search for news in a topic with specific keywords"""
        results = []
        handles = self.news_handles.get(topic, self.news_handles['general'])
        
        for handle in handles[:2]:  # Limit handles for keyword search
            try:
                # Create search query with keywords
                keyword_query = ' OR '.join(keywords)
                query = f"from:{handle} ({keyword_query}) -filter:replies -filter:retweets"
                
                for i, tweet in enumerate(sntwitter.TwitterSearchScraper(query).get_items()):
                    if i >= limit:
                        break
                    
                    # Only get tweets from last 3 days for search
                    if tweet.date < datetime.now() - timedelta(days=3):
                        break
                    
                    results.append({
                        'title': self._extract_title(tweet.rawContent),
                        'content': tweet.rawContent,
                        'source': f"@{handle}",
                        'url': tweet.url,
                        'timestamp': tweet.date,
                        'topic': topic,
                        'relevance_score': self._calculate_relevance(tweet.rawContent, keywords)
                    })
                
            except Exception as e:
                logger.error(f"Error searching @{handle} with keywords: {e}")
        
        return results
    
    async def _scrape_rss_feed(self, topic: str) -> List[Dict]:
        """Fallback RSS feed scraping when Twitter fails"""
        news_items = []
        feeds = self.rss_feeds.get(topic, [])
        
        for feed_url in feeds:
            try:
                response = requests.get(feed_url, timeout=10)
                soup = BeautifulSoup(response.content, 'xml')
                
                items = soup.find_all('item')[:5]  # Get latest 5 items
                
                for item in items:
                    title = item.find('title')
                    description = item.find('description')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    
                    if title and description:
                        news_items.append({
                            'title': title.text.strip(),
                            'content': description.text.strip(),
                            'source': 'RSS Feed',
                            'url': link.text.strip() if link else '',
                            'timestamp': self._parse_rss_date(pub_date.text) if pub_date else datetime.now(),
                            'topic': topic
                        })
                
            except Exception as e:
                logger.error(f"Error scraping RSS feed {feed_url}: {e}")
        
        return news_items
    
    def _is_news_tweet(self, content: str) -> bool:
        """Check if a tweet contains news content"""
        # Filter out promotional, personal, or non-news tweets
        news_indicators = [
            'breaking', 'update', 'report', 'announces', 'says', 'according to',
            'sources', 'confirmed', 'latest', 'news', 'today', 'yesterday'
        ]
        
        content_lower = content.lower()
        
        # Must contain at least one news indicator
        has_news_indicator = any(indicator in content_lower for indicator in news_indicators)
        
        # Should not be too short or too promotional
        is_substantial = len(content.split()) > 8
        is_not_promotional = not any(promo in content_lower for promo in ['buy now', 'subscribe', 'follow us', 'download app'])
        
        return has_news_indicator and is_substantial and is_not_promotional
    
    def _extract_title(self, content: str) -> str:
        """Extract a title from tweet content"""
        # Remove URLs, mentions, and hashtags for cleaner title
        clean_content = re.sub(r'http\S+|www\S+|@\w+|#\w+', '', content)
        clean_content = re.sub(r'\s+', ' ', clean_content).strip()
        
        # Take first sentence or first 100 characters
        sentences = clean_content.split('.')
        if sentences and len(sentences[0]) > 20:
            return sentences[0].strip() + '.'
        
        return clean_content[:100] + '...' if len(clean_content) > 100 else clean_content
    
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
        """Parse RSS date string to datetime object"""
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
                    return datetime.strptime(date_str.strip(), fmt)
                except ValueError:
                    continue
            
            return datetime.now()
        except Exception:
            return datetime.now()
    
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
                                                'timestamp': datetime.now()
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