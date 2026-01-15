"""API endpoints for narrative RAG v2 architecture.

These endpoints implement the SQL-first RAG approach where:
- SQL is the single source of truth
- Narratives are derived from SQL
- Only narratives are embedded in vector store
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.narrative_generator import NarrativeGenerator
from src.services.narrative_vectorization import NarrativeRAGService
from src.services.rag_query_handler import RAGQueryHandler

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v2", tags=["narrative-rag"])

# Initialize global services
narrative_generator = NarrativeGenerator()
narrative_rag_service = NarrativeRAGService()
query_handler = RAGQueryHandler(
    narrative_rag_service=narrative_rag_service
)

logger.info("Narrative RAG v2 services initialized")


# Request/Response Models
class GenerateNarrativesRequest(BaseModel):
    """Request model for narrative generation."""
    year: int


class GenerateNarrativesResponse(BaseModel):
    """Response model for narrative generation."""
    year: int
    documents_generated: int
    documents_embedded: int
    rejected: int
    status: str
    details: Optional[dict] = None


class ChatRequest(BaseModel):
    """Request model for RAG chat endpoint."""
    query: str
    year: Optional[int] = None
    month: Optional[int] = None
    top_k: int = 5


class ChatResponse(BaseModel):
    """Response model for RAG chat endpoint."""
    query: str
    answer: str
    sources: list
    confidence: str
    metadata: Optional[dict] = None


class NarrativeStatsResponse(BaseModel):
    """Response model for narrative stats endpoint."""
    total_documents: int
    documents_by_type: dict
    service_ready: bool
    query_handler_ready: bool


# Endpoints
@router.post("/narratives/generate", response_model=GenerateNarrativesResponse)
async def generate_narratives(request: GenerateNarrativesRequest):
    """Generate and embed narrative documents for a year.
    
    This endpoint:
    1. Computes SQL aggregates for the year
    2. Generates narrative documents from aggregates
    3. Embeds narratives in the vector store
    
    Args:
        request: Request with year
        
    Returns:
        Statistics about generated and embedded documents
    """
    try:
        logger.info(f"Generating narratives for year {request.year}")
        
        # Generate all narrative documents
        documents = narrative_generator.generate_all_documents(request.year)
        
        if not documents:
            logger.warning(f"No documents generated for year {request.year}")
            return GenerateNarrativesResponse(
                year=request.year,
                documents_generated=0,
                documents_embedded=0,
                rejected=0,
                status="no_data",
                details={"message": "No financial data found for this year"}
            )
        
        logger.info(f"Generated {len(documents)} narrative documents")
        
        # Embed documents in vector store
        embedding_result = narrative_rag_service.add_documents(documents)
        
        logger.info(f"Embedding result: {embedding_result}")
        
        return GenerateNarrativesResponse(
            year=request.year,
            documents_generated=len(documents),
            documents_embedded=embedding_result["added"],
            rejected=embedding_result["rejected"],
            status="success",
            details={
                "embedding_stats": embedding_result,
                "total_in_store": narrative_rag_service.size()
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating narratives: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error generating narratives: {str(e)}"
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a conversational query using narrative RAG.
    
    This endpoint:
    1. Performs semantic search on narrative documents
    2. Retrieves relevant context
    3. Uses LLM to answer based on narratives
    4. Returns grounded answer with sources
    
    Args:
        request: Query request with optional year/month filters
        
    Returns:
        Answer with sources and confidence
    """
    try:
        logger.info(f"Processing chat query: {request.query}")
        
        # Answer query using RAG
        result = query_handler.answer_query(
            user_query=request.query,
            year=request.year,
            month=request.month,
            top_k=request.top_k
        )
        
        return ChatResponse(
            query=result["query"],
            answer=result["answer"],
            sources=result["sources"],
            confidence=result["confidence"],
            metadata={
                "avg_similarity": result.get("avg_similarity"),
                "documents_retrieved": result.get("documents_retrieved"),
                "error": result.get("error"),
                "note": result.get("note")
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing chat query: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )


@router.get("/narratives/stats", response_model=NarrativeStatsResponse)
async def get_narrative_stats():
    """Get statistics about the narrative vector store.
    
    Returns:
        Stats including total documents, breakdown by type, and service status
    """
    try:
        stats = narrative_rag_service.get_stats()
        handler_status = query_handler.get_service_status()
        
        return NarrativeStatsResponse(
            total_documents=stats["total_documents"],
            documents_by_type=stats["by_type"],
            service_ready=stats["service_ready"],
            query_handler_ready=handler_status["query_handler_ready"]
        )
        
    except Exception as e:
        logger.error(f"Error getting narrative stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting stats: {str(e)}"
        )


@router.delete("/narratives")
async def clear_narratives():
    """Clear all narrative documents from the vector store.
    
    This is safe because narratives are derived artifacts that can be
    regenerated from SQL at any time.
    
    Returns:
        Success message
    """
    try:
        logger.info("Clearing narrative vector store")
        narrative_rag_service.clear()
        
        return {
            "status": "success",
            "message": "Narrative vector store cleared",
            "total_documents": narrative_rag_service.size()
        }
        
    except Exception as e:
        logger.error(f"Error clearing narratives: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing narratives: {str(e)}"
        )


@router.post("/narratives/regenerate")
async def regenerate_narratives(request: GenerateNarrativesRequest):
    """Regenerate narrative embeddings from scratch.
    
    This endpoint:
    1. Clears existing embeddings
    2. Generates fresh narratives from SQL
    3. Embeds new narratives
    
    Args:
        request: Request with year
        
    Returns:
        Statistics about regeneration
    """
    try:
        logger.info(f"Regenerating narratives for year {request.year}")
        
        # Generate fresh narratives
        documents = narrative_generator.generate_all_documents(request.year)
        
        if not documents:
            return {
                "status": "no_data",
                "year": request.year,
                "message": "No financial data found for this year"
            }
        
        # Regenerate vector store
        result = narrative_rag_service.regenerate_from_narratives(documents)
        
        return {
            "status": "success",
            "year": request.year,
            "documents_generated": len(documents),
            "documents_embedded": result["added"],
            "rejected": result["rejected"],
            "total_in_store": narrative_rag_service.size()
        }
        
    except Exception as e:
        logger.error(f"Error regenerating narratives: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error regenerating narratives: {str(e)}"
        )
