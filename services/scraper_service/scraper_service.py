from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import httpx
import hashlib
import os
import logging
from typing import List, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    Scrapes posts from requested microblogging platforms.
    """
    posts = []
    try:
        if "twitter" in request.platforms:
            try:
                posts += await scrape_twitter(request.query)
            except Exception as e:
                logger.error(f"Error scraping Twitter: {e}")
        
        if "threads" in request.platforms:
            try:
                posts += await scrape_threads(request.query)
            except Exception as e:
                logger.error(f"Error scraping Threads: {e}")
        
        if "bluesky" in request.platforms:
            try:
                posts += await scrape_bluesky(request.query)
            except Exception as e:
                logger.error(f"Error scraping Bluesky: {e}")
        
        await index_to_qdrant(posts)
    except Exception as e:
        logger.error(f"Error in run_scrapers: {e}")

# Twitter API v2
async def scrape_twitter(query: str) -> list[dict]:
    try:
        headers = {"Authorization": f"Bearer {os.getenv('TWITTER_TOKEN')}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "http://api.twitter.com/2/tweets/search/recent", 
                params={"query": f"{query} lang:en", "max_results": 100}, 
                headers=headers
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            # Validate response structure
            twitter_response = TwitterResponse(**response.json())
            if twitter_response.data is None:
                logger.warning("No data found in Twitter response")
                return []
            return [{
                "id": f"tw_{tweet.id}",
                "text": tweet.text, 
                "source": "twitter"
            } for tweet in twitter_response.data]
    except httpx.RequestError as e:
        logger.error(f"HTTP error while scraping Twitter: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping Twitter: {e}")
        return []

# Threads Unofficial API (Could Break)
async def scrape_threads(query: str) -> list[dict]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://www.threads.net/api/graphql",  # Fixed URL
                params={"query": query, "count": 100}, 
                headers=headers
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            # Validate response structure
            threads_response = ThreadsResponse(**response.json())
            if threads_response.data is None or threads_response.data.search.edges is None:
                logger.warning("Unexpected data structure in Threads response")
                return []
            return [{
                "id": f"threads_{post.node.id}",
                "text": post.node.text, 
                "source": "threads"
            } for post in threads_response.data.search.edges]
    except httpx.RequestError as e:
        logger.error(f"HTTP error while scraping Threads: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping Threads: {e}")
        return []

# Bluesky
async def scrape_bluesky(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://bsky.social/xrpc/app.bsky.feed.searchPosts", 
                params={"q": query, "limit": 100}  # Use params instead of json for GET requests
            )
            response.raise_for_status()  # Raise an exception for bad status codes
            # Validate response structure
            bluesky_response = BlueskyResponse(**response.json())
            if bluesky_response.posts is None:
                logger.warning("No posts found in Bluesky response")
                return []
            return [{
                "id": f"bsky_{post.uri.split('/')[-1]}",
                "text": post.record.text, 
                "source": "bluesky"
            } for post in bluesky_response.posts]
    except httpx.RequestError as e:
        logger.error(f"HTTP error while scraping Bluesky: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping Bluesky: {e}")
        return []

async def index_to_qdrant(posts: list[dict]):
    """
    Generate embeddings and store in Qdrant for a list of scraped posts.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for post in posts:
                try:
                    # Get embedding
                    embedding_response = await client.post(
                        "http://embedding-service:8004/embed", 
                        json={"text": post["text"]}
                    )
                    embedding_response.raise_for_status()
                    # Validate embedding response
                    embedding_data = EmbeddingResponse(**embedding_response.json())
                    
                    # Store in Qdrant
                    qdrant_response = await client.put(
                        "http://qdrant:6333/collections/posts/points",
                        json={
                            "points": [{
                                "id": hashlib.sha256(post["id"].encode()).hexdigest(),
                                "vector": embedding_data.embedding,
                                "payload": post
                            }]
                        }
                    )
                    qdrant_response.raise_for_status()
                    logger.info(f"Successfully indexed post {post['id']}")
                except httpx.RequestError as e:
                    logger.error(f"HTTP error while indexing post {post['id']}: {e}")
                except Exception as e:
                    logger.error(f"Error while indexing post {post['id']}: {e}")
    except Exception as e:
        logger.error(f"Error in index_to_qdrant: {e}")