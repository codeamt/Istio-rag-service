from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os
import logging
from typing import List, Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for API response validation
class EmbeddingResponse(BaseModel):
    embedding: List[float]
    
class QdrantSearchResultHit(BaseModel):
    payload: Dict[str, Any]
    
class QdrantSearchResult(BaseModel):
    result: List[QdrantSearchResultHit]
    
class LLMResponse(BaseModel):
    text: str

app = FastAPI()

class QueryRequest(BaseModel):
    query: str
    max_results: int = 5

@app.post("/query")
async def query_rag(request: QueryRequest):
    """
    Query the RAG Service with a user query.
    """
    try:
        #1 Retrieve documents from Qdrant
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                embedding = await get_embedding(request.query)
            except Exception as e:
                logger.error(f"Error getting embedding: {e}")
                raise HTTPException(status_code=500, detail="Error processing query embedding")
            
            try:
                vector_response = await client.post(
                    "http://qdrant:6333/collections/posts/points/search",
                    json={
                        "vector": embedding, 
                        "limit": request.max_results,
                    }
                )
                vector_response.raise_for_status()
                # Validate response structure
                qdrant_response = QdrantSearchResult(**vector_response.json())
                documents = [hit.payload for hit in qdrant_response.result]
                if not documents:
                    raise HTTPException(status_code=404, detail="No documents found")
            except httpx.RequestError as e:
                logger.error(f"Error connecting to Qdrant: {e}")
                raise HTTPException(status_code=500, detail="Error retrieving documents")
            except Exception as e:
                logger.error(f"Error retrieving documents: {e}")
                raise HTTPException(status_code=500, detail="Error retrieving documents")

        #2 Generate response using LLM
        try:
            llm_response = await client.post(
                "http://vllm:8000/generate", 
                json={
                    "prompt": f"Answer this question: {request.query}\nContext: {documents}",
                    "max_tokens": 500,
                }
            )
            llm_response.raise_for_status()
            # Validate response structure
            llm_data = LLMResponse(**llm_response.json())
            return {"answer": llm_data.text}
        except httpx.RequestError as e:
            logger.error(f"Error connecting to vLLM: {e}")
            raise HTTPException(status_code=500, detail="Error generating response")
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise HTTPException(status_code=500, detail="Error generating response")
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in query_rag: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def get_embedding(text: str) -> list[float]:
    """
    Get the embedding from the embedding service.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://embedding-service:8000/embed",
                json={"text": text}
            )
            response.raise_for_status()
            # Validate response structure
            embedding_data = EmbeddingResponse(**response.json())
            return embedding_data.embedding
    except httpx.RequestError as e:
        logger.error(f"HTTP error while getting embedding: {e}")
        raise Exception(f"Error connecting to embedding service: {e}")
    except Exception as e:
        logger.error(f"Error while getting embedding: {e}")
        raise Exception(f"Error processing embedding: {e}")