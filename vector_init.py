"""
Vector Search Initialization
=============================

Main entry point for initializing the complete vector search system.
Handles:
- Qdrant connection and collection setup
- Embedding service configuration  
- Initial data synchronization
- API endpoint registration
"""

import logging
import os
from typing import Optional, Dict, Any
from threading import Thread
import time

from vector_config import (
    get_vector_config, 
    configure_vector_search,
    QdrantConfig,
    EmbeddingConfig,
    EmbeddingModel
)
from qdrant_manager import get_qdrant_manager, initialize_qdrant
from embedding_service import get_embedding_service, configure_embedding_service
from vector_sync import get_vector_sync_service, initialize_vector_sync
from vector_matcher import get_vector_matcher

logger = logging.getLogger(__name__)


class VectorSearchSystem:
    """
    Complete vector search system manager.
    
    Provides unified interface for:
    - System initialization
    - Data synchronization
    - Search operations
    - Health monitoring
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._ready = False
        self._init_error: Optional[str] = None
        self._initialized = True
        
        logger.info("VectorSearchSystem created")
    
    def initialize(
        self,
        gemini_api_key: str,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        qdrant_api_key: str = None,
        auto_sync: bool = False,
        connection_params: Dict = None
    ) -> bool:
        """
        Initialize the complete vector search system.
        
        Args:
            gemini_api_key: API key for Gemini embeddings
            qdrant_host: Qdrant server host
            qdrant_port: Qdrant server port
            qdrant_api_key: Optional Qdrant Cloud API key
            auto_sync: If True, perform initial sync after setup
            connection_params: Optional DB connection parameters
            
        Returns:
            True if initialization successful
        """
        try:
            logger.info("=== Initializing Vector Search System ===")
            
            # Step 1: Configure global settings
            config = configure_vector_search(
                qdrant_host=qdrant_host,
                qdrant_port=qdrant_port,
                gemini_api_key=gemini_api_key
            )
            logger.info(f"Configuration loaded: {config.embedding.model.model_name}")
            
            # Step 2: Initialize Qdrant connection
            qdrant = initialize_qdrant(
                host=qdrant_host,
                port=qdrant_port,
                api_key=qdrant_api_key,
                vector_size=config.embedding.dimensions
            )
            
            if not qdrant.is_connected:
                raise ConnectionError("Failed to connect to Qdrant")
            logger.info("Qdrant connection established")
            
            # Step 3: Configure embedding service
            embedding = configure_embedding_service(
                api_key=gemini_api_key,
                config=config.embedding
            )
            logger.info(f"Embedding service ready: {embedding.dimensions}D vectors")
            
            # Step 4: Initialize sync service
            sync = initialize_vector_sync(qdrant, embedding)
            logger.info("Sync service initialized")
            
            # Step 5: Configure matcher
            matcher = get_vector_matcher()
            matcher.configure(qdrant, embedding, config)
            logger.info("Vector matcher configured")
            
            self._ready = True
            logger.info("=== Vector Search System Ready ===")
            
            # Step 6: Auto-sync if requested
            if auto_sync:
                logger.info("Starting initial data synchronization...")
                self._background_sync(connection_params)
            
            return True
            
        except Exception as e:
            self._init_error = str(e)
            self._ready = False
            logger.error(f"Vector search initialization failed: {e}")
            return False
    
    def _background_sync(self, connection_params: Dict = None):
        """Start background synchronization thread."""
        def sync_task():
            try:
                time.sleep(2)  # Wait for API to be ready
                sync = get_vector_sync_service()
                sync.full_sync(connection_params)
            except Exception as e:
                logger.error(f"Background sync failed: {e}")
        
        thread = Thread(target=sync_task, daemon=True)
        thread.start()
        logger.info("Background sync started")
    
    def sync_now(
        self,
        connection_params: Dict = None,
        sync_type: str = "full"
    ) -> Dict:
        """
        Trigger immediate synchronization.
        
        Args:
            connection_params: Optional DB connection params
            sync_type: "full", "menu_items", or "ocr_mappings"
            
        Returns:
            Sync result statistics
        """
        if not self._ready:
            return {"error": "System not initialized"}
        
        sync = get_vector_sync_service()
        
        if sync_type == "full":
            return sync.full_sync(connection_params)
        elif sync_type == "menu_items":
            return sync.sync_menu_items(connection_params)
        elif sync_type == "ocr_mappings":
            return sync.sync_ocr_mappings(connection_params)
        else:
            return {"error": f"Unknown sync type: {sync_type}"}
    
    def get_status(self) -> Dict:
        """Get system status and statistics."""
        status = {
            "ready": self._ready,
            "error": self._init_error
        }
        
        if self._ready:
            try:
                qdrant = get_qdrant_manager()
                embedding = get_embedding_service()
                sync = get_vector_sync_service()
                
                status.update({
                    "qdrant": {
                        "connected": qdrant.is_connected,
                        "collections": qdrant.get_all_collections_info()
                    },
                    "embedding": {
                        "model": embedding.model_name,
                        "dimensions": embedding.dimensions,
                        "cache": embedding.get_cache_stats()
                    },
                    "sync": sync.get_sync_stats()
                })
            except Exception as e:
                status["status_error"] = str(e)
        
        return status
    
    @property
    def is_ready(self) -> bool:
        """Check if system is ready."""
        return self._ready


# Global instance accessor
def get_vector_system() -> VectorSearchSystem:
    """Get the singleton vector search system instance."""
    return VectorSearchSystem()


def initialize_vector_search_system(
    gemini_api_key: str = None,
    qdrant_host: str = None,
    qdrant_port: int = None,
    auto_sync: bool = False,
    connection_params: Dict = None
) -> VectorSearchSystem:
    """
    Initialize the vector search system with sensible defaults.
    
    Reads configuration from environment variables if not provided:
    - GEMINI_API_KEY
    - QDRANT_HOST (default: localhost)
    - QDRANT_PORT (default: 6333)
    
    Args:
        gemini_api_key: Gemini API key
        qdrant_host: Qdrant server host
        qdrant_port: Qdrant server port
        auto_sync: Perform initial sync
        connection_params: DB connection parameters
        
    Returns:
        Initialized VectorSearchSystem
    """
    # Get API key from various sources
    api_key = gemini_api_key
    
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        # Try appSetting.txt
        try:
            with open('appSetting.txt', 'r') as f:
                for line in f:
                    if line.startswith('GEMINI_API_KEY='):
                        api_key = line.split('=', 1)[1].strip()
                        break
        except Exception:
            pass
    
    if not api_key:
        raise ValueError(
            "Gemini API key not found. Provide via parameter, "
            "GEMINI_API_KEY env var, or appSetting.txt"
        )
    
    # Get Qdrant settings
    host = qdrant_host or os.getenv("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.getenv("QDRANT_PORT", "6333"))
    
    # Initialize system
    system = get_vector_system()
    system.initialize(
        gemini_api_key=api_key,
        qdrant_host=host,
        qdrant_port=port,
        auto_sync=auto_sync,
        connection_params=connection_params
    )
    
    return system


def get_api_key_from_token_manager(company_id: str) -> Optional[str]:
    """
    Get Gemini API key from TokenManager for a specific company.
    
    Uses your existing token management system.
    """
    try:
        from token_manager import TokenManager
        token_result = TokenManager.get_active_token(company_id)
        
        if token_result.get('success'):
            return token_result.get('api_key')
        
        return None
    except Exception as e:
        logger.warning(f"Failed to get API key from TokenManager: {e}")
        return None
