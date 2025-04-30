from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import httpx
import hashlib
import os

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
    if "twitter" in request.platforms:
        posts += await scrape_twitter(request.query)
    if "threads" in request.platforms:
        posts += await scrape_threads(request.query)
    if "bluesky" in request.platforms:
        posts += await scrape_bluesky(request.query)

    await index_to_qdrant(posts)

# Twitter API v2
async def scrape_twitter(query: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {os.getenv('TWITTER_TOKEN')}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://api.twitter.com/2/tweets/search/recent", 
            params={"query": f"{query} lang:en", "max_results": 100}, 
            headers=headers
        )
        return [{
            "id": f"tw_{tweet['id']}",
            "text": tweet["text"], 
            "source": "twitter"
        } for tweet in response.json().get("data", [])]

# Threads Unofficial API (Could Break)
async def scrape_threads(query: str) -> list[dict]:
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.threads.net/api/qraphql",
            params={"query": query, "count": 100}, 
            headers=headers
        )
        return [{
            "id": f"threads_{post['node']['id']}",
            "text": post['node']['text'], 
            "source": "threads"
        } for post in response.json()['data']['search']['edges']]

# Bluesky
async def scrape_bluesky(query: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://bsky.social/xrpc/app.bsky.feed.searchPosts", 
            json={"q": query, "limit": 100}
        )
        return [{
            "id": f"bsky_{post['uri'].split('/')[-1]}",
            "text": post["record"]["text"], 
            "source": "bluesky"
        } for post in response.json().get("posts", [])]

async def index_to_qdrant(posts: list[dict]):
    """
    Generate embeddings and store in Qdrant for a list of scraped posts.
    """
    async with httpx.AsyncClient() as client:
        for post in posts: 
            embedding = await client.post(
                "http://embedding-service:8004/embed", 
                json={"text": post["text"]}
            )
            await client.put(
                "http://qdrant:6333/collections/posts/points",
                json={
                    "points": [{
                        "id": hashlib.sha256(post["id"].encode()).hexdigest(),
                        "vector": embedding.json()["embedding"],
                        "payload": post
                                             
                    }]
                }
            )