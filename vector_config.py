"""
Vector Search Configuration
============================

Central configuration for Qdrant vector database and embedding settings.
Supports both local Docker deployment and cloud Qdrant instances.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class EmbeddingModel(Enum):
    """Supported embedding models with their dimensions."""
    # Google/Gemini models (use your existing Gemini API key)
    # text-embedding-004 is the current stable embedding model
    GEMINI_EMBEDDING_004 = ("text-embedding-004", 768)
    
    # For future expansion when newer models become available
    # GEMINI_EMBEDDING_005 = ("text-embedding-005", 1024)

    @property
    def model_name(self) -> str:
        return self.value[0]
    
    @property
    def dimensions(self) -> int:
        return self.value[1]


@dataclass
class QdrantConfig:
    """Qdrant vector database configuration."""
    
    # Connection settings
    host: str = field(default_factory=lambda: os.getenv("QDRANT_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333")))
    grpc_port: int = field(default_factory=lambda: int(os.getenv("QDRANT_GRPC_PORT", "6334")))
    
    # API key for Qdrant Cloud (optional for local)
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    
    # Use HTTPS for cloud deployments
    https: bool = field(default_factory=lambda: os.getenv("QDRANT_HTTPS", "false").lower() == "true")
    
    # Collection names
    menu_items_collection: str = "menu_items"
    ocr_mappings_collection: str = "ocr_mappings"
    suppliers_collection: str = "suppliers"
    
    # Search settings
    default_top_k: int = 5
    score_threshold: float = 0.70  # Cosine similarity threshold (0.7 = 70% match)
    
    # Batch processing
    batch_size: int = 100  # For bulk upserts
    
    @property
    def url(self) -> str:
        """Get Qdrant URL."""
        protocol = "https" if self.https else "http"
        return f"{protocol}://{self.host}:{self.port}"


@dataclass 
class EmbeddingConfig:
    """Embedding model configuration."""
    
    # Model selection - using text-embedding-004 (768 dimensions)
    model: EmbeddingModel = EmbeddingModel.GEMINI_EMBEDDING_004
    
    # API settings (uses same Gemini API key from token management)
    api_key: Optional[str] = None  # Will be populated from TokenManager or appSetting.txt
    
    # Request settings
    batch_size: int = 100  # Max texts per embedding request
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Text preprocessing
    max_text_length: int = 2048  # Truncate longer texts
    normalize_text: bool = True  # Lowercase, remove special chars
    
    @property
    def dimensions(self) -> int:
        return self.model.dimensions


@dataclass
class VectorSearchConfig:
    """Main vector search configuration combining Qdrant and Embedding settings."""
    
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    
    # Vector-only search (no fuzzy hybrid)
    vector_weight: float = 1.0  # Full vector similarity
    fuzzy_weight: float = 0.0  # No fuzzy matching
    
    # Use pure vector mode (no fuzzy fallback)
    use_vector_only: bool = True
    
    # Cache settings
    embedding_cache_ttl: int = 3600  # 1 hour cache for embeddings
    
    # Sync settings
    auto_sync_on_change: bool = True  # Auto-sync vectors when data changes
    sync_batch_size: int = 500  # Records per sync batch
    
    # Logging
    log_searches: bool = True
    log_sync_operations: bool = True


# Global configuration instance
_config: Optional[VectorSearchConfig] = None


def get_vector_config() -> VectorSearchConfig:
    """Get or create global vector search configuration."""
    global _config
    if _config is None:
        _config = VectorSearchConfig()
    return _config


def configure_vector_search(
    qdrant_host: str = None,
    qdrant_port: int = None,
    embedding_model: EmbeddingModel = None,
    gemini_api_key: str = None,
    **kwargs
) -> VectorSearchConfig:
    """
    Configure vector search settings.
    
    Args:
        qdrant_host: Qdrant server hostname
        qdrant_port: Qdrant server port
        embedding_model: Which embedding model to use
        gemini_api_key: API key for Gemini embeddings
        **kwargs: Additional settings
    
    Returns:
        Configured VectorSearchConfig instance
    """
    global _config
    
    qdrant_config = QdrantConfig(
        host=qdrant_host or os.getenv("QDRANT_HOST", "localhost"),
        port=qdrant_port or int(os.getenv("QDRANT_PORT", "6333"))
    )
    
    embedding_config = EmbeddingConfig(
        model=embedding_model or EmbeddingModel.GEMINI_EMBEDDING_004,
        api_key=gemini_api_key
    )
    
    _config = VectorSearchConfig(
        qdrant=qdrant_config,
        embedding=embedding_config,
        **{k: v for k, v in kwargs.items() if hasattr(VectorSearchConfig, k)}
    )
    
    return _config


# Collection schemas for reference
MENU_ITEMS_SCHEMA = {
    "collection_name": "menu_items",
    "vector_size": 768,  # text-embedding-004
    "distance": "Cosine",
    "payload_fields": {
        "mcode": "keyword",        # Primary key
        "menucode": "keyword",     # Menu code
        "desca": "text",           # Original description
        "desca_normalized": "text", # Preprocessed description
        "baseunit": "keyword",     # Base unit of measurement
        "confactor": "float",      # Conversion factor
        "altunit": "keyword",      # Alternate unit
        "vat": "integer",          # VAT flag (0/1)
        "type": "keyword",         # Item type
        "isactive": "integer",     # Active flag
        "category": "keyword",     # Product category (if available)
        "brand": "keyword",        # Brand name extracted from description
        # Supplier information (from menuitem.SUPCODE JOIN rmd_aclist)
        "supplier_code": "keyword",  # SUPCODE from menuitem
        "supplier_name": "keyword",  # acname from rmd_aclist
        "updated_at": "datetime",  # Last sync timestamp
    }
}

OCR_MAPPINGS_SCHEMA = {
    "collection_name": "ocr_mappings",
    "vector_size": 768,  # text-embedding-004
    "distance": "Cosine", 
    "payload_fields": {
        "invoice_product_name": "text",  # OCR-extracted name
        "invoice_product_code": "keyword",
        "db_mcode": "keyword",           # Mapped database mcode
        "db_desca": "text",              # Mapped database description
        "db_menucode": "keyword",
        "supplier_name": "keyword",      # Invoice supplier
        "confidence_score": "float",     # Match confidence
        "created_at": "datetime",
        "usage_count": "integer",        # How often this mapping is used
    }
}

SUPPLIERS_SCHEMA = {
    "collection_name": "suppliers",
    "vector_size": 768,  # text-embedding-004
    "distance": "Cosine",
    "payload_fields": {
        "supplier_name": "text",
        "supplier_name_normalized": "text",
        "supplier_code": "keyword",
        "common_products": "keyword[]",  # Array of common mcode values
        "updated_at": "datetime",
    }
}
