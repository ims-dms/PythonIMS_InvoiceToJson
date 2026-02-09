"""
Qdrant Client Manager
======================

Manages connections to Qdrant vector database and provides
collection management utilities.

Features:
- Connection pooling and health checks
- Automatic collection creation with proper schemas
- Batch upsert operations for efficiency
- Search utilities with filtering
"""

import logging
import time
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchParams,
    OptimizersConfigDiff,
    HnswConfigDiff,
)

from vector_config import (
    get_vector_config,
    QdrantConfig,
    MENU_ITEMS_SCHEMA,
    OCR_MAPPINGS_SCHEMA,
    SUPPLIERS_SCHEMA,
)

logger = logging.getLogger(__name__)


class QdrantManager:
    """
    Manages Qdrant vector database connections and operations.
    
    Provides:
    - Connection management with automatic reconnection
    - Collection creation and schema management
    - Efficient batch upsert operations
    - Optimized vector search
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
        
        self._client: Optional[QdrantClient] = None
        self._config: Optional[QdrantConfig] = None
        self._connected = False
        self._initialized = True
        
        logger.info("QdrantManager initialized (singleton)")
    
    def connect(self, config: QdrantConfig = None) -> bool:
        """
        Establish connection to Qdrant server.
        
        Args:
            config: Optional QdrantConfig override
            
        Returns:
            True if connection successful
        """
        self._config = config or get_vector_config().qdrant
        
        try:
            # Create client
            if self._config.api_key:
                # Cloud deployment with API key
                self._client = QdrantClient(
                    url=self._config.url,
                    api_key=self._config.api_key,
                    timeout=30
                )
            else:
                # Local Docker deployment
                self._client = QdrantClient(
                    host=self._config.host,
                    port=self._config.port,
                    timeout=30
                )
            
            # Test connection
            collections = self._client.get_collections()
            self._connected = True
            
            logger.info(
                f"Connected to Qdrant at {self._config.url} - "
                f"{len(collections.collections)} collections found"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            self._connected = False
            return False
    
    def ensure_connected(self) -> bool:
        """Ensure connection is active, reconnect if needed."""
        if self._connected and self._client:
            try:
                # Quick health check
                self._client.get_collections()
                return True
            except Exception:
                self._connected = False
        
        return self.connect(self._config)
    
    def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
        on_disk: bool = False
    ) -> bool:
        """
        Create a new collection with optimized settings.
        
        Args:
            collection_name: Name of the collection
            vector_size: Dimension of vectors (e.g., 1024)
            distance: Distance metric (COSINE, EUCLID, DOT)
            on_disk: Store vectors on disk (for large collections)
            
        Returns:
            True if created or already exists
        """
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        try:
            # Check if exists
            collections = self._client.get_collections()
            existing = [c.name for c in collections.collections]
            
            if collection_name in existing:
                logger.info(f"Collection '{collection_name}' already exists")
                return True
            
            # Create with optimized settings for 700k+ items
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance,
                    on_disk=on_disk
                ),
                # Optimize for large datasets
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,  # Build index after 20k points
                    memmap_threshold=50000,    # Use memory mapping after 50k
                ),
                # HNSW index settings for fast search
                hnsw_config=HnswConfigDiff(
                    m=16,                      # Connections per node
                    ef_construct=100,          # Build quality
                    full_scan_threshold=10000, # Use index above this
                    on_disk=on_disk
                )
            )
            
            logger.info(
                f"Created collection '{collection_name}' with {vector_size}D vectors"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection '{collection_name}': {e}")
            raise
    
    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_type: str = "keyword"
    ) -> bool:
        """
        Create payload index for efficient filtering.
        
        Args:
            collection_name: Target collection
            field_name: Field to index
            field_type: "keyword", "integer", "float", "text"
            
        Returns:
            True if successful
        """
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        type_map = {
            "keyword": models.PayloadSchemaType.KEYWORD,
            "integer": models.PayloadSchemaType.INTEGER,
            "float": models.PayloadSchemaType.FLOAT,
            "text": models.PayloadSchemaType.TEXT,
        }
        
        try:
            self._client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=type_map.get(field_type, models.PayloadSchemaType.KEYWORD)
            )
            logger.debug(f"Created index on {collection_name}.{field_name}")
            return True
        except Exception as e:
            # Index might already exist
            logger.debug(f"Index creation note for {field_name}: {e}")
            return True
    
    def initialize_collections(self, vector_size: int = 768) -> bool:
        """
        Initialize all required collections with proper schemas.
        
        Args:
            vector_size: Vector dimensions (default 768 for text-embedding-004)
            
        Returns:
            True if all collections initialized
        """
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        try:
            # Create menu_items collection
            self.create_collection(
                self._config.menu_items_collection,
                vector_size=vector_size,
                distance=Distance.COSINE,
                on_disk=True  # Use disk for 700k+ items
            )
            
            # Create indexes for menu_items
            for field, ftype in [
                ("mcode", "keyword"),
                ("menucode", "keyword"),
                ("baseunit", "keyword"),
                ("vat", "integer"),
                ("isactive", "integer"),
                # Supplier indexes for supplier-based filtering
                ("supplier_code", "keyword"),
                ("supplier_name", "keyword"),
            ]:
                self.create_payload_index(
                    self._config.menu_items_collection, field, ftype
                )
            
            # Create ocr_mappings collection
            self.create_collection(
                self._config.ocr_mappings_collection,
                vector_size=vector_size,
                distance=Distance.COSINE
            )
            
            # Create indexes for ocr_mappings
            for field, ftype in [
                ("db_mcode", "keyword"),
                ("supplier_name", "keyword"),
                ("usage_count", "integer"),
            ]:
                self.create_payload_index(
                    self._config.ocr_mappings_collection, field, ftype
                )
            
            # Create suppliers collection
            self.create_collection(
                self._config.suppliers_collection,
                vector_size=vector_size,
                distance=Distance.COSINE
            )
            
            logger.info("All vector collections initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize collections: {e}")
            raise
    
    def upsert_points(
        self,
        collection_name: str,
        points: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Upsert points to collection in batches.
        
        Args:
            collection_name: Target collection
            points: List of point dicts with 'id', 'vector', 'payload'
            batch_size: Points per batch
            
        Returns:
            Number of points upserted
        """
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        if not points:
            return 0
        
        total = 0
        num_batches = (len(points) + batch_size - 1) // batch_size
        
        for i in range(num_batches):
            start = i * batch_size
            end = min(start + batch_size, len(points))
            batch = points[start:end]
            
            point_structs = [
                PointStruct(
                    id=p['id'],
                    vector=p['vector'],
                    payload=p.get('payload', {})
                )
                for p in batch
            ]
            
            try:
                self._client.upsert(
                    collection_name=collection_name,
                    points=point_structs,
                    wait=True
                )
                total += len(batch)
                
                if (i + 1) % 10 == 0:
                    logger.info(
                        f"Upserted {total}/{len(points)} points to {collection_name}"
                    )
                    
            except Exception as e:
                logger.error(f"Batch upsert failed at batch {i}: {e}")
                raise
        
        logger.info(f"Completed upserting {total} points to {collection_name}")
        return total
    
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        score_threshold: float = 0.0,
        filters: Dict[str, Any] = None
    ) -> List[Dict]:
        """
        Search for similar vectors.
        
        Args:
            collection_name: Collection to search
            query_vector: Query embedding
            limit: Max results to return
            score_threshold: Minimum similarity score (0-1 for cosine)
            filters: Optional payload filters
            
        Returns:
            List of results with id, score, and payload
        """
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        # Build filter if provided
        search_filter = None
        if filters:
            conditions = []
            for field, value in filters.items():
                if value is not None:
                    conditions.append(
                        FieldCondition(
                            key=field,
                            match=MatchValue(value=value)
                        )
                    )
            if conditions:
                search_filter = Filter(must=conditions)
        
        try:
            results = self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter,
                with_payload=True,
                search_params=SearchParams(
                    hnsw_ef=128,  # Search quality
                    exact=False   # Use HNSW index
                )
            )
            
            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload
                }
                for r in results
            ]
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    def delete_points(
        self,
        collection_name: str,
        point_ids: List[str]
    ) -> bool:
        """
        Delete points by ID.
        
        Args:
            collection_name: Target collection
            point_ids: List of point IDs to delete
            
        Returns:
            True if successful
        """
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        try:
            self._client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=point_ids)
            )
            logger.debug(f"Deleted {len(point_ids)} points from {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False
    
    def get_collection_info(self, collection_name: str) -> Dict:
        """Get collection statistics."""
        if not self.ensure_connected():
            raise ConnectionError("Not connected to Qdrant")
        
        try:
            info = self._client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status.value,
                "optimizer_status": info.optimizer_status.status.value,
                "vectors_config": {
                    "size": info.config.params.vectors.size,
                    "distance": info.config.params.vectors.distance.value
                }
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}
    
    def get_all_collections_info(self) -> List[Dict]:
        """Get info for all collections."""
        if not self.ensure_connected():
            return []
        
        try:
            collections = self._client.get_collections()
            return [
                self.get_collection_info(c.name)
                for c in collections.collections
            ]
        except Exception:
            return []
    
    def count_points(self, collection_name: str) -> int:
        """Get number of points in collection."""
        info = self.get_collection_info(collection_name)
        return info.get("points_count", 0)
    
    @property
    def client(self) -> Optional[QdrantClient]:
        """Get underlying Qdrant client."""
        return self._client
    
    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected


# Global instance accessor
def get_qdrant_manager() -> QdrantManager:
    """Get the singleton Qdrant manager instance."""
    return QdrantManager()


def initialize_qdrant(
    host: str = "localhost",
    port: int = 6333,
    api_key: str = None,
    vector_size: int = 768
) -> QdrantManager:
    """
    Initialize Qdrant connection and collections.
    
    Args:
        host: Qdrant server host
        port: Qdrant server port
        api_key: Optional API key for Qdrant Cloud
        vector_size: Vector dimensions (default 768 for text-embedding-004)
        
    Returns:
        Configured QdrantManager instance
    """
    from vector_config import QdrantConfig
    
    config = QdrantConfig(host=host, port=port, api_key=api_key)
    
    manager = get_qdrant_manager()
    if manager.connect(config):
        manager.initialize_collections(vector_size)
    
    return manager
