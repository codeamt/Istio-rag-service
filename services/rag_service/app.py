from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

class QueryRequest(BaseModel):
    query: str
    max_results: int = 5

@app.post("/query")
async def query_rag(request: QueryRequest):
    """
    Query the RAG Service with a user query.
    """
    #1 Retrieve documents from Qdrant
    async with httpx.AsyncClient() as client:
        vector_response = await client.post(
            f"http://qdrant:6333/collections/posts/points/search",
            json={
                "vector": await get_embedding(request.query), 
                "limit": request.max_results,
            }
        )
        documents = [hit["payload"] for hit in vector_response.json()["result"]]
        if not documents:
            raise HTTPException(status_code=404, detail="No documents found")

    #2 Generate response using LLM
    llm_response = await client.post(
        "http://vllm:8000/generate", 
        json={
            "prompt": f"Answer this question: {request.query}\nContext: {documents}",
            "max_tokens": 500,
        }
    )
    return {"answer": llm_response.json()["text"]}

async def get_embedding(text: str) -> list[float]:
    """
    Get the embedding from the embedding service.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://embedding-service:8000/embed",
            json={"text": text}
        )
        return response.json()["embedding"]