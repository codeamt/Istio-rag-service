from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, BaseSettings
import httpx
import os
import logging
from typing import List, Dict, Any

# Configuration management
class Settings(BaseSettings):
    # Service URLs
    embedding_service_url: str = "http://embedding-service:8000/embed"
    qdrant_search_url: str = "http://qdrant:6333/collections/posts/points/search"
    vllm_generate_url: str = "http://vllm:8000/generate"
    
    # Processing
    http_timeout: int = 30
    max_tokens: int = 500
    
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
    logger.info(f"Processing RAG query: '{request.query}' with max_results={request.max_results}")
    try:
        #1 Retrieve documents from Qdrant
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            try:
                logger.info("Getting embedding for query")
                embedding = await get_embedding(request.query)
                logger.info(f"Successfully obtained embedding with {len(embedding)} dimensions")
            except Exception as e:
                logger.error(f"Error getting embedding: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Error processing query embedding")
            
            try:
                logger.info(f"Searching Qdrant for similar documents (limit: {request.max_results})")
                vector_response = await client.post(
                    settings.qdrant_search_url,
                    json={
                        "vector": embedding, 
                        "limit": request.max_results,
                    }
                )
                vector_response.raise_for_status()
                logger.info(f"Qdrant search response status: {vector_response.status_code}")
                
                # Validate response structure
                qdrant_response = QdrantSearchResult(**vector_response.json())
                documents = [hit.payload for hit in qdrant_response.result]
                logger.info(f"Retrieved {len(documents)} documents from Qdrant")
                
                if not documents:
                    logger.warning("No documents found for query")
                    raise HTTPException(status_code=404, detail="No documents found")
            except httpx.RequestError as e:
                logger.error(f"Error connecting to Qdrant: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Error retrieving documents")
            except Exception as e:
                logger.error(f"Error retrieving documents: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Error retrieving documents")

        #2 Generate response using LLM
        try:
            logger.info(f"Generating response using LLM with {len(documents)} context documents")
            llm_response = await client.post(
                settings.vllm_generate_url, 
                json={
                    "prompt": f"Answer this question: {request.query}\nContext: {documents}",
                    "max_tokens": settings.max_tokens,
                }
            )
            llm_response.raise_for_status()
            logger.info(f"LLM response status: {llm_response.status_code}")
            
            # Validate response structure
            llm_data = LLMResponse(**llm_response.json())
            logger.info("Successfully generated response from LLM")
            return {"answer": llm_data.text}
        except httpx.RequestError as e:
            logger.error(f"Error connecting to vLLM: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error generating response")
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error generating response")
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in query_rag: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

async def get_embedding(text: str) -> list[float]:
    """
    Get the embedding from the embedding service.
    """
    logger.debug(f"Getting embedding for text: {text[:50]}...")
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            response = await client.post(
                settings.embedding_service_url,
                json={"text": text}
            )
            response.raise_for_status()
            logger.debug(f"Embedding service response status: {response.status_code}")
            
            # Validate response structure
            embedding_data = EmbeddingResponse(**response.json())
            logger.debug(f"Successfully obtained embedding with {len(embedding_data.embedding)} dimensions")
            return embedding_data.embedding
    except httpx.RequestError as e:
        logger.error(f"HTTP error while getting embedding: {e}", exc_info=True)
        raise Exception(f"Error connecting to embedding service: {e}")
    except Exception as e:
        logger.error(f"Error while getting embedding: {e}", exc_info=True)
        raise Exception(f"Error processing embedding: {e}")