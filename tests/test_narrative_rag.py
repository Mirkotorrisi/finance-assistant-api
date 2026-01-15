"""Tests for NarrativeRAGService."""

import pytest
from unittest.mock import MagicMock, patch

from src.services.narrative_vectorization import NarrativeRAGService, ALLOWED_DOCUMENT_TYPES


@pytest.fixture
def narrative_rag_service():
    """Create a NarrativeRAGService for testing."""
    service = NarrativeRAGService()
    yield service
    service.clear()


def test_narrative_rag_service_initialization():
    """Test NarrativeRAGService initialization."""
    service = NarrativeRAGService()
    assert service.size() == 0


def test_validate_document_valid(narrative_rag_service):
    """Test document validation with valid document."""
    valid_doc = {
        "text": "In March 2026, total expenses were €3000 and income was €5000.",
        "type": "monthly_summary",
        "metadata": {"year": 2026, "month": 3}
    }
    
    assert narrative_rag_service._validate_document(valid_doc) is True


def test_validate_document_missing_text(narrative_rag_service):
    """Test document validation with missing text."""
    invalid_doc = {
        "type": "monthly_summary",
        "metadata": {"year": 2026}
    }
    
    assert narrative_rag_service._validate_document(invalid_doc) is False


def test_validate_document_missing_type(narrative_rag_service):
    """Test document validation with missing type."""
    invalid_doc = {
        "text": "Some text here",
        "metadata": {"year": 2026}
    }
    
    assert narrative_rag_service._validate_document(invalid_doc) is False


def test_validate_document_invalid_type(narrative_rag_service):
    """Test document validation with invalid type."""
    invalid_doc = {
        "text": "Some text here",
        "type": "transaction",  # Forbidden type
        "metadata": {}
    }
    
    assert narrative_rag_service._validate_document(invalid_doc) is False


def test_validate_document_forbidden_pattern(narrative_rag_service):
    """Test document validation with forbidden pattern in type."""
    invalid_doc = {
        "text": "Some text here",
        "type": "raw_transaction",  # Contains forbidden pattern
        "metadata": {}
    }
    
    assert narrative_rag_service._validate_document(invalid_doc) is False


def test_validate_document_empty_text(narrative_rag_service):
    """Test document validation with empty text."""
    invalid_doc = {
        "text": "",
        "type": "monthly_summary",
        "metadata": {}
    }
    
    assert narrative_rag_service._validate_document(invalid_doc) is False


def test_add_documents_no_client(narrative_rag_service):
    """Test add_documents when OpenAI client is not initialized."""
    # Mock client as None
    narrative_rag_service.client = None
    
    documents = [
        {
            "text": "Test narrative",
            "type": "monthly_summary",
            "metadata": {}
        }
    ]
    
    result = narrative_rag_service.add_documents(documents)
    
    assert result["added"] == 0
    assert result["rejected"] == 1


def test_add_documents_with_client(narrative_rag_service):
    """Test add_documents with mocked OpenAI client."""
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    mock_client.embeddings.create.return_value = mock_response
    narrative_rag_service.client = mock_client
    
    documents = [
        {
            "text": "In March 2026, expenses were €3000.",
            "type": "monthly_summary",
            "metadata": {"year": 2026, "month": 3}
        }
    ]
    
    result = narrative_rag_service.add_documents(documents)
    
    assert result["added"] == 1
    assert result["rejected"] == 0
    assert narrative_rag_service.size() == 1


def test_add_documents_mixed_valid_invalid(narrative_rag_service):
    """Test add_documents with mix of valid and invalid documents."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    mock_client.embeddings.create.return_value = mock_response
    narrative_rag_service.client = mock_client
    
    documents = [
        {
            "text": "Valid narrative",
            "type": "monthly_summary",
            "metadata": {}
        },
        {
            "text": "Invalid",
            "type": "transaction",  # Forbidden
            "metadata": {}
        }
    ]
    
    result = narrative_rag_service.add_documents(documents)
    
    assert result["added"] == 1
    assert result["rejected"] == 1


def test_query_empty_store(narrative_rag_service):
    """Test query on empty vector store."""
    results = narrative_rag_service.query("test query")
    assert results == []


def test_query_no_client(narrative_rag_service):
    """Test query when OpenAI client is not initialized."""
    narrative_rag_service.client = None
    results = narrative_rag_service.query("test query")
    assert results == []


def test_query_with_results(narrative_rag_service):
    """Test query with mocked results."""
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_embedding_response = MagicMock()
    mock_embedding_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    mock_client.embeddings.create.return_value = mock_embedding_response
    narrative_rag_service.client = mock_client
    
    # Add a document
    narrative_rag_service.vector_store.append({
        "document": {
            "text": "Test narrative",
            "type": "monthly_summary",
            "metadata": {}
        },
        "text": "Test narrative",
        "embedding": [0.1, 0.2, 0.3],
        "type": "monthly_summary",
        "metadata": {}
    })
    
    results = narrative_rag_service.query("test query", top_k=1)
    
    assert len(results) == 1
    assert results[0]["type"] == "monthly_summary"
    assert "similarity" in results[0]


def test_query_with_type_filter(narrative_rag_service):
    """Test query with document type filter."""
    mock_client = MagicMock()
    mock_embedding_response = MagicMock()
    mock_embedding_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    mock_client.embeddings.create.return_value = mock_embedding_response
    narrative_rag_service.client = mock_client
    
    # Add documents of different types
    narrative_rag_service.vector_store.extend([
        {
            "document": {"text": "Monthly", "type": "monthly_summary", "metadata": {}},
            "text": "Monthly",
            "embedding": [0.1, 0.2, 0.3],
            "type": "monthly_summary",
            "metadata": {}
        },
        {
            "document": {"text": "Category", "type": "category_summary", "metadata": {}},
            "text": "Category",
            "embedding": [0.1, 0.2, 0.3],
            "type": "category_summary",
            "metadata": {}
        }
    ])
    
    results = narrative_rag_service.query("test", doc_type="monthly_summary")
    
    assert len(results) == 1
    assert results[0]["type"] == "monthly_summary"


def test_clear(narrative_rag_service):
    """Test clearing the vector store."""
    # Add a document
    narrative_rag_service.vector_store.append({
        "document": {"text": "Test", "type": "monthly_summary", "metadata": {}},
        "text": "Test",
        "embedding": [0.1, 0.2, 0.3],
        "type": "monthly_summary",
        "metadata": {}
    })
    
    assert narrative_rag_service.size() == 1
    
    narrative_rag_service.clear()
    
    assert narrative_rag_service.size() == 0


def test_regenerate_from_narratives(narrative_rag_service):
    """Test regenerate_from_narratives."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    mock_client.embeddings.create.return_value = mock_response
    narrative_rag_service.client = mock_client
    
    # Add some initial documents
    narrative_rag_service.vector_store.append({
        "document": {"text": "Old", "type": "monthly_summary", "metadata": {}},
        "text": "Old",
        "embedding": [0.0, 0.0, 0.0],
        "type": "monthly_summary",
        "metadata": {}
    })
    
    # Regenerate with new documents
    new_documents = [
        {
            "text": "New narrative",
            "type": "monthly_summary",
            "metadata": {}
        }
    ]
    
    result = narrative_rag_service.regenerate_from_narratives(new_documents)
    
    assert result["added"] == 1
    assert narrative_rag_service.size() == 1


def test_get_stats(narrative_rag_service):
    """Test get_stats."""
    # Add documents of different types
    narrative_rag_service.vector_store.extend([
        {
            "document": {"text": "M1", "type": "monthly_summary", "metadata": {}},
            "text": "M1",
            "embedding": [0.1],
            "type": "monthly_summary",
            "metadata": {}
        },
        {
            "document": {"text": "M2", "type": "monthly_summary", "metadata": {}},
            "text": "M2",
            "embedding": [0.2],
            "type": "monthly_summary",
            "metadata": {}
        },
        {
            "document": {"text": "C1", "type": "category_summary", "metadata": {}},
            "text": "C1",
            "embedding": [0.3],
            "type": "category_summary",
            "metadata": {}
        }
    ])
    
    stats = narrative_rag_service.get_stats()
    
    assert stats["total_documents"] == 3
    assert stats["by_type"]["monthly_summary"] == 2
    assert stats["by_type"]["category_summary"] == 1


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    
    similarity = NarrativeRAGService._cosine_similarity(vec1, vec2)
    
    assert similarity == 1.0
    
    vec3 = [0.0, 1.0, 0.0]
    similarity2 = NarrativeRAGService._cosine_similarity(vec1, vec3)
    
    assert similarity2 == 0.0
