from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, BaseSettings
import httpx
import hashlib
import os
import logging
from typing import List, Optional
import asyncio
import time
from collections import deque
from threading import Lock

# Configuration management
class Settings(BaseSettings):
    # API Tokens
    twitter_token: Optional[str] = None
    
    # Rate Limiting
    twitter_max_requests: int = 300
    twitter_time_window: int = 900
    threads_max_requests: int = 100
    threads_time_window: int = 3600
    bluesky_max_requests: int = 3000
    bluesky_time_window: int = 300
    embedding_max_requests: int = 1000
    embedding_time_window: int = 60
    qdrant_max_requests: int = 1000
    qdrant_time_window: int = 60
    
    # Service URLs
    twitter_api_url: str = "http://api.twitter.com/2/tweets/search/recent"
    threads_api_url: str = "https://www.threads.net/api/graphql"
    bluesky_api_url: str = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
    embedding_service_url: str = "http://embedding-service:8004/embed"
    qdrant_url: str = "http://qdrant:6333/collections/posts/points"
    
    # Processing
    batch_size: int = 10
    http_timeout: int = 30
    max_results_per_platform: int = 100
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Set up logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def deduplicate_posts(posts: List[dict]) -> List[dict]:
    """
    Remove duplicate posts using SHA checksums of post content.
    
    Args:
        posts: List of post dictionaries
    
    Returns:
        List of unique posts
    """
    seen_checksums = set()
    unique_posts = []
    
    logger.info(f"Starting deduplication of {len(posts)} posts")
    
    for post in posts:
        # Create a checksum of the post content
        content = f"{post.get('text', '')}".strip()
        if content:  # Only process posts with content
            checksum = hashlib.sha256(content.encode('utf-8')).hexdigest()
            
            # If we haven't seen this checksum before, add the post
            if checksum not in seen_checksums:
                seen_checksums.add(checksum)
                unique_posts.append(post)
            else:
                logger.debug(f"Duplicate post found and removed: {post.get('id', 'unknown')} - Content: {content[:50]}...")
        else:
            # Even posts without content should be tracked by ID
            post_id = post.get('id', '')
            if post_id and post_id not in seen_checksums:
                seen_checksums.add(post_id)
                unique_posts.append(post)
    
    logger.info(f"Deduplication complete. {len(unique_posts)} unique posts remaining (removed {len(posts) - len(unique_posts)} duplicates)")
    return unique_posts

# Rate limiting configuration
class RateLimiter:
    def __init__(self, max_requests: int, time_window: float):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
        self.lock = Lock()
    
    async def acquire(self):
        async with asyncio.Lock():
            now = time.time()
            # Remove old requests outside the time window
            while self.requests and self.requests[0] <= now - self.time_window:
                self.requests.popleft()
            
            # If we're at capacity, wait until we can make a request
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached ({self.max_requests} requests per {self.time_window}s), sleeping for {sleep_time:.2f} seconds")
                    await asyncio.sleep(sleep_time)
                    # Remove old requests again after sleeping
                    now = time.time()
                    while self.requests and self.requests[0] <= now - self.time_window:
                        self.requests.popleft()
            
            # Add current request
            self.requests.append(now)

# Rate limiters for different APIs
TWITTER_RATE_LIMITER = RateLimiter(max_requests=settings.twitter_max_requests, time_window=settings.twitter_time_window)
THREADS_RATE_LIMITER = RateLimiter(max_requests=settings.threads_max_requests, time_window=settings.threads_time_window)
BLUESKY_RATE_LIMITER = RateLimiter(max_requests=settings.bluesky_max_requests, time_window=settings.bluesky_time_window)
EMBEDDING_RATE_LIMITER = RateLimiter(max_requests=settings.embedding_max_requests, time_window=settings.embedding_time_window)
QDRANT_RATE_LIMITER = RateLimiter(max_requests=settings.qdrant_max_requests, time_window=settings.qdrant_time_window)

# Pydantic models for API response validation
class TwitterTweet(BaseModel):
    id: str
    text: str
    
class TwitterResponse(BaseModel):
    data: Optional[List[TwitterTweet]] = None
    
class ThreadsPostNode(BaseModel):
    id: str
    text: str
    
class ThreadsPostEdge(BaseModel):
    node: ThreadsPostNode
    
class ThreadsSearchData(BaseModel):
    edges: List[ThreadsPostEdge]
    
class ThreadsSearchResult(BaseModel):
    search: ThreadsSearchData
    
class ThreadsResponse(BaseModel):
    data: Optional[ThreadsSearchResult] = None
    
class BlueskyRecord(BaseModel):
    text: str
    
class BlueskyPost(BaseModel):
    uri: str
    record: BlueskyRecord
    
class BlueskyResponse(BaseModel):
    posts: Optional[List[BlueskyPost]] = None
    
class EmbeddingResponse(BaseModel):
    embedding: List[float]
    
class QdrantSearchResultHit(BaseModel):
    payload: dict
    
class QdrantSearchResult(BaseModel):
    result: List[QdrantSearchResultHit]
    
class LLMResponse(BaseModel):
    text: str

app = FastAPI()

class ScrapeRequest(BaseModel):
    query: str
    platforms: list[str] = ["twitter", "bluesky", "threads"]

@app.post("/scrape")
async def scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Scrapes data from specified platforms based on the query.
    """
    background_tasks.add_task(run_scrapers, request)
    return {"status": "Scraping started"}

async def run_scrapers(request: ScrapeRequest):
    """
    Scrapes posts from requested microblogging platforms concurrently.
    """
    logger.info(f"Starting scraping for query: '{request.query}' on platforms: {request.platforms}")
    posts = []
    try:
        # Create tasks for concurrent scraping
        tasks = []
        
        if "twitter" in request.platforms:
            tasks.append(scrape_twitter(request.query))
        
        if "threads" in request.platforms:
            tasks.append(scrape_threads(request.query))
        
        if "bluesky" in request.platforms:
            tasks.append(scrape_bluesky(request.query))
        
        # Execute all scraping tasks concurrently
        if tasks:
            logger.info(f"Executing {len(tasks)} scraping tasks concurrently")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                platform = request.platforms[i] if i < len(request.platforms) else f"platform_{i}"
                if isinstance(result, Exception):
                    logger.error(f"Error scraping {platform}: {result}")
                else:
                    logger.info(f"Successfully scraped {len(result)} posts from {platform}")
                    posts.extend(result)
        
        logger.info(f"Scraping complete. Total posts collected: {len(posts)}")
        
        # Deduplicate posts using SHA checksums
        unique_posts = deduplicate_posts(posts)
        
        await index_to_qdrant(unique_posts)
    except Exception as e:
        logger.error(f"Error in run_scrapers: {e}", exc_info=True)

# Twitter API v2
async def scrape_twitter(query: str) -> list[dict]:
    try:
        logger.info(f"Scraping Twitter for query: '{query}'")
        # Apply rate limiting
        await TWITTER_RATE_LIMITER.acquire()
        
        headers = {"Authorization": f"Bearer {settings.twitter_token}"}
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.get(
                settings.twitter_api_url, 
                params={"query": f"{query} lang:en", "max_results": settings.max_results_per_platform}, 
                headers=headers
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            logger.info(f"Twitter API response status: {response.status_code}")
            
            # Validate response structure
            twitter_response = TwitterResponse(**response.json())
            if twitter_response.data is None:
                logger.warning("No data found in Twitter response")
                return []
            
            logger.info(f"Successfully scraped {len(twitter_response.data)} tweets from Twitter")
            return [{
                "id": f"tw_{tweet.id}",
                "text": tweet.text, 
                "source": "twitter"
            } for tweet in twitter_response.data]
    except httpx.RequestError as e:
        logger.error(f"HTTP error while scraping Twitter: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping Twitter: {e}", exc_info=True)
        return []

# Threads Unofficial API (Could Break)
async def scrape_threads(query: str) -> list[dict]:
    try:
        logger.info(f"Scraping Threads for query: '{query}'")
        # Apply rate limiting
        await THREADS_RATE_LIMITER.acquire()
        
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.get(
                settings.threads_api_url,
                params={"query": query, "count": settings.max_results_per_platform}, 
                headers=headers
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            logger.info(f"Threads API response status: {response.status_code}")
            
            # Validate response structure
            threads_response = ThreadsResponse(**response.json())
            if threads_response.data is None or threads_response.data.search.edges is None:
                logger.warning("Unexpected data structure in Threads response")
                return []
            
            logger.info(f"Successfully scraped {len(threads_response.data.search.edges)} posts from Threads")
            return [{
                "id": f"threads_{post.node.id}",
                "text": post.node.text, 
                "source": "threads"
            } for post in threads_response.data.search.edges]
    except httpx.RequestError as e:
        logger.error(f"HTTP error while scraping Threads: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping Threads: {e}", exc_info=True)
        return []

# Bluesky
async def scrape_bluesky(query: str) -> list[dict]:
    try:
        logger.info(f"Scraping Bluesky for query: '{query}'")
        # Apply rate limiting
        await BLUESKY_RATE_LIMITER.acquire()
        
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.get(
                settings.bluesky_api_url, 
                params={"q": query, "limit": settings.max_results_per_platform}
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            logger.info(f"Bluesky API response status: {response.status_code}")
            
            # Validate response structure
            bluesky_response = BlueskyResponse(**response.json())
            if bluesky_response.posts is None:
                logger.warning("No posts found in Bluesky response")
                return []
            
            logger.info(f"Successfully scraped {len(bluesky_response.posts)} posts from Bluesky")
            return [{
                "id": f"bsky_{post.uri.split('/')[-1]}",
                "text": post.record.text, 
                "source": "bluesky"
            } for post in bluesky_response.posts]
    except httpx.RequestError as e:
        logger.error(f"HTTP error while scraping Bluesky: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping Bluesky: {e}", exc_info=True)
        return []

async def index_to_qdrant(posts: list[dict]):
    """
    Generate embeddings and store in Qdrant for a list of scraped posts in batches.
    """
    if not posts:
        logger.info("No posts to index")
        return
    
    logger.info(f"Starting indexing process for {len(posts)} posts")
    batch_size = settings.batch_size  # Process posts in batches
    total_indexed = 0
    
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            # Process posts in batches
            total_batches = (len(posts) + batch_size - 1) // batch_size
            for i in range(0, len(posts), batch_size):
                batch_num = i//batch_size + 1
                batch = posts[i:i + batch_size]
                logger.info(f"Processing batch {batch_num}/{total_batches} with {len(batch)} posts")
                
                # Get embeddings for all posts in the batch
                batch_points = []
                
                for j, post in enumerate(batch):
                    try:
                        logger.debug(f"Getting embedding for post {j+1}/{len(batch)} in batch {batch_num}")
                        # Apply rate limiting for embedding service
                        await EMBEDDING_RATE_LIMITER.acquire()
                        
                        # Get embedding
                        embedding_response = await client.post(
                            settings.embedding_service_url, 
                            json={"text": post["text"]}
                        )
                        embedding_response.raise_for_status()
                        # Validate embedding response
                        embedding_data = EmbeddingResponse(**embedding_response.json())
                        
                        # Prepare Qdrant point
                        point = {
                            "id": hashlib.sha256(post["id"].encode()).hexdigest(),
                            "vector": embedding_data.embedding,
                            "payload": post
                        }
                        batch_points.append(point)
                        
                    except httpx.RequestError as e:
                        logger.error(f"HTTP error while getting embedding for post {post['id']}: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"Error while getting embedding for post {post['id']}: {e}", exc_info=True)
                        continue
                
                # Store batch in Qdrant
                if batch_points:
                    try:
                        logger.debug(f"Storing batch {batch_num} with {len(batch_points)} points in Qdrant")
                        # Apply rate limiting for Qdrant (once per batch)
                        await QDRANT_RATE_LIMITER.acquire()
                        
                        # Store all points in Qdrant
                        qdrant_response = await client.put(
                            settings.qdrant_url,
                            json={
                                "points": batch_points
                            }
                        )
                        qdrant_response.raise_for_status()
                        total_indexed += len(batch_points)
                        logger.info(f"Successfully indexed batch {batch_num}/{total_batches} with {len(batch_points)} posts")
                    except httpx.RequestError as e:
                        logger.error(f"HTTP error while indexing batch {batch_num}: {e}")
                    except Exception as e:
                        logger.error(f"Error while indexing batch {batch_num}: {e}", exc_info=True)
                else:
                    logger.warning(f"No valid points to index in batch {batch_num}")
            
            logger.info(f"Indexing process complete. Successfully indexed {total_indexed} posts out of {len(posts)} total posts")
                    
    except Exception as e:
        logger.error(f"Error in index_to_qdrant: {e}", exc_info=True)