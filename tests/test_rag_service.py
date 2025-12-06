import pytest
from fastapi.testclient import TestClient
from services.rag_service.app import app, QueryRequest

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "rag"}

def test_query_request_validation():
    # Test valid request
    request_data = {
        "query": "What is the weather today?",
        "max_results": 5
    }
    response = client.post("/query", json=request_data)
    # Should fail because we don't have the actual services running
    # but the validation should pass
    assert response.status_code != 422

def test_query_request_invalid_max_results():
    # Test invalid max_results (too high)
    request_data = {
        "query": "What is the weather today?",
        "max_results": 100
    }
    response = client.post("/query", json=request_data)
    # Should fail validation
    assert response.status_code == 422

def test_query_request_empty_query():
    # Test empty query
    request_data = {
        "query": "",
        "max_results": 5
    }
    response = client.post("/query", json=request_data)
    # Should fail validation
    assert response.status_code == 422

def test_query_request_missing_query():
    # Test missing query
    request_data = {
        "max_results": 5
    }
    response = client.post("/query", json=request_data)
    # Should fail validation
    assert response.status_code == 422

def test_query_request_query_too_long():
    # Test query too long
    request_data = {
        "query": "A" * 1001,  # Longer than max_length of 1000
        "max_results": 5
    }
    response = client.post("/query", json=request_data)
    # Should fail validation
    assert response.status_code == 422
