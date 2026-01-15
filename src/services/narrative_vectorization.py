"""Narrative-only RAG service for SQL-first architecture.

This service ONLY embeds narrative documents, never raw transactions.
It enforces the SQL-first principle where embeddings are derived artifacts.
"""

import logging
import os
from typing import List, Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# Explicitly allowed document types for embedding
ALLOWED_DOCUMENT_TYPES = {
    "monthly_summary",
    "category_summary",
    "anomaly",
    "yearly_overview",
    "note"  # User annotations
}

# Explicitly forbidden - these should NEVER be embedded
FORBIDDEN_PATTERNS = [
    "transaction",
    "raw",
    "individual"
]


class NarrativeRAGService:
    """RAG service that ONLY embeds narrative documents.
    
    This service:
    - Validates all documents before embedding
    - Rejects raw transactions or numeric data without context
    - Only accepts pre-generated narrative summaries
    - Provides semantic search over narratives
    """
    
    def __init__(self):
        """Initialize the narrative RAG service."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set. RAG functionality will be disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
        
        self.model = "text-embedding-3-small"
        
        # In-memory vector store: list of (document, embedding) tuples
        self.vector_store: List[Dict[str, Any]] = []
    
    def _validate_document(self, document: Dict[str, Any]) -> bool:
        """Validate that a document is allowed to be embedded.
        
        Args:
            document: Document to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check for required fields
        if "text" not in document or "type" not in document:
            logger.error("Document missing required fields: 'text' and 'type'")
            return False
        
        # Check document type
        doc_type = document.get("type", "").lower()
        if doc_type not in ALLOWED_DOCUMENT_TYPES:
            logger.error(
                f"Document type '{doc_type}' is not allowed. "
                f"Allowed types: {ALLOWED_DOCUMENT_TYPES}"
            )
            return False
        
        # Check for forbidden patterns in type
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in doc_type:
                logger.error(
                    f"Document type '{doc_type}' contains forbidden pattern '{pattern}'"
                )
                return False
        
        # Validate text is not empty
        if not document["text"] or len(document["text"].strip()) == 0:
            logger.error("Document text is empty")
            return False
        
        # Additional validation: narratives should be reasonably long
        if len(document["text"]) < 20:
            logger.warning(
                f"Document text is very short ({len(document['text'])} chars). "
                "This might not be a proper narrative."
            )
        
        return True
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add narrative documents to the vector store.
        
        Args:
            documents: List of narrative documents to add
            
        Returns:
            Dict with stats: total, added, rejected, reasons
        """
        if not self.client:
            logger.warning("OpenAI client not initialized. Cannot add documents to vector store.")
            return {
                "total": len(documents),
                "added": 0,
                "rejected": len(documents),
                "reason": "OpenAI client not initialized"
            }
        
        if not documents:
            return {
                "total": 0,
                "added": 0,
                "rejected": 0
            }
        
        # Validate all documents first
        valid_documents = []
        rejected_count = 0
        rejection_reasons = []
        
        for doc in documents:
            if self._validate_document(doc):
                valid_documents.append(doc)
            else:
                rejected_count += 1
                rejection_reasons.append(
                    f"Invalid document type: {doc.get('type', 'unknown')}"
                )
        
        if not valid_documents:
            logger.warning("No valid documents to add after validation")
            return {
                "total": len(documents),
                "added": 0,
                "rejected": rejected_count,
                "reasons": rejection_reasons
            }
        
        try:
            # Extract texts for embedding
            texts = [doc["text"] for doc in valid_documents]
            
            # Generate embeddings
            response = self.client.embeddings.create(
                model=self.model,
                input=texts
            )
            
            # Store documents with embeddings
            for i, document in enumerate(valid_documents):
                self.vector_store.append({
                    "document": document,
                    "text": texts[i],
                    "embedding": response.data[i].embedding,
                    "type": document["type"],
                    "metadata": document.get("metadata", {})
                })
            
            logger.info(
                f"Added {len(valid_documents)} narrative documents to vector store "
                f"(total: {len(self.vector_store)}, rejected: {rejected_count})"
            )
            
            return {
                "total": len(documents),
                "added": len(valid_documents),
                "rejected": rejected_count,
                "reasons": rejection_reasons if rejection_reasons else None
            }
            
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {str(e)}")
            return {
                "total": len(documents),
                "added": 0,
                "rejected": len(documents),
                "reason": str(e)
            }
    
    def query(
        self, 
        query_text: str, 
        top_k: int = 5, 
        doc_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query the vector store for relevant narrative documents.
        
        Args:
            query_text: Natural language query
            top_k: Number of results to return
            doc_type: Optional filter by document type
            
        Returns:
            List of most relevant documents with similarity scores
        """
        if not self.client:
            logger.warning("OpenAI client not initialized. Cannot query vector store.")
            return []
        
        if not self.vector_store:
            logger.info("Vector store is empty")
            return []
        
        try:
            # Generate query embedding
            response = self.client.embeddings.create(
                model=self.model,
                input=[query_text]
            )
            query_embedding = response.data[0].embedding
            
            # Filter by document type if specified
            candidates = self.vector_store
            if doc_type:
                candidates = [
                    item for item in self.vector_store 
                    if item["type"] == doc_type
                ]
            
            if not candidates:
                logger.info(f"No documents found with type '{doc_type}'")
                return []
            
            # Calculate cosine similarity with all stored embeddings
            similarities = []
            for item in candidates:
                similarity = self._cosine_similarity(query_embedding, item["embedding"])
                similarities.append({
                    "document": item["document"],
                    "text": item["text"],
                    "type": item["type"],
                    "metadata": item["metadata"],
                    "similarity": similarity
                })
            
            # Sort by similarity (descending) and take top k
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            results = similarities[:top_k]
            
            logger.info(
                f"Query '{query_text}' returned {len(results)} results "
                f"(filtered by type: {doc_type})" if doc_type else f"Query '{query_text}' returned {len(results)} results"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error querying vector store: {str(e)}")
            return []
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Cosine similarity score (-1 to 1, where 1 is most similar)
        """
        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # Magnitudes
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        # Cosine similarity
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def clear(self) -> None:
        """Clear the vector store."""
        self.vector_store = []
        logger.info("Narrative vector store cleared")
    
    def regenerate_from_narratives(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Clear and regenerate the vector store from narrative documents.
        
        This is safe because narratives are derived artifacts that can be
        regenerated from SQL at any time.
        
        Args:
            documents: List of narrative documents
            
        Returns:
            Stats about the regeneration
        """
        logger.info("Regenerating vector store from narratives...")
        self.clear()
        result = self.add_documents(documents)
        logger.info(f"Vector store regeneration complete: {result}")
        return result
    
    def size(self) -> int:
        """Get the number of documents in the vector store.
        
        Returns:
            Number of stored documents
        """
        return len(self.vector_store)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store.
        
        Returns:
            Dict with total count and breakdown by document type
        """
        if not self.vector_store:
            return {
                "total_documents": 0,
                "by_type": {},
                "service_ready": self.client is not None
            }
        
        # Count by type
        type_counts = {}
        for item in self.vector_store:
            doc_type = item["type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        
        return {
            "total_documents": len(self.vector_store),
            "by_type": type_counts,
            "service_ready": self.client is not None
        }
