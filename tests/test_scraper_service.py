import pytest
from fastapi.testclient import TestClient
from services.scraper_service.scraper_service import app, ScrapeRequest, deduplicate_posts

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "scraper"}

def test_scrape_request_validation():
    # Test valid request
    request_data = {
        "query": "test query",
        "platforms": ["twitter", "bluesky"]
    }
    response = client.post("/scrape", json=request_data)
    assert response.status_code == 200
    assert "status" in response.json()

def test_scrape_request_invalid_platform():
    # Test invalid platform
    request_data = {
        "query": "test query",
        "platforms": ["invalid_platform"]
    }
    response = client.post("/scrape", json=request_data)
    # Should fail validation
    assert response.status_code == 422

def test_scrape_request_empty_query():
    # Test empty query
    request_data = {
        "query": "",
        "platforms": ["twitter"]
    }
    response = client.post("/scrape", json=request_data)
    # Should fail validation
    assert response.status_code == 422

def test_deduplicate_posts():
    # Test deduplication function
    posts = [
        {"id": "1", "text": "Hello world", "source": "twitter"},
        {"id": "2", "text": "Hello world", "source": "bluesky"},  # Duplicate content
        {"id": "3", "text": "Different post", "source": "threads"}
    ]
    
    unique_posts = deduplicate_posts(posts)
    assert len(unique_posts) == 2  # Should remove one duplicate
    
    # Check that the first occurrence is kept
    assert unique_posts[0]["id"] == "1"
    assert unique_posts[1]["id"] == "3"

def test_deduplicate_posts_empty():
    # Test deduplication with empty list
    posts = []
    unique_posts = deduplicate_posts(posts)
    assert len(unique_posts) == 0

def test_deduplicate_posts_no_duplicates():
    # Test deduplication with no duplicates
    posts = [
        {"id": "1", "text": "Post one", "source": "twitter"},
        {"id": "2", "text": "Post two", "source": "bluesky"},
        {"id": "3", "text": "Post three", "source": "threads"}
    ]
    
    unique_posts = deduplicate_posts(posts)
    assert len(unique_posts) == 3  # Should keep all posts
