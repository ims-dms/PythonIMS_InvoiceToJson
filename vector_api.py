"""
Vector Search API Endpoints
============================

FastAPI router for vector search management endpoints.
Add these routes to your main API application.

Endpoints:
- POST /vector/init - Initialize vector search system
- POST /vector/sync - Trigger data synchronization
- GET /vector/status - Get system status
- POST /vector/search - Perform vector search
- POST /vector/mapping - Add new OCR mapping
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Form, Body
from pydantic import BaseModel

from vector_init import (
    get_vector_system,
    initialize_vector_search_system,
    get_api_key_from_token_manager
)
from vector_sync import get_vector_sync_service
from vector_matcher import get_vector_matcher, match_ocr_products_vector
from qdrant_manager import get_qdrant_manager
from embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

# Create router
vector_router = APIRouter(prefix="/vector", tags=["Vector Search"])


class InitRequest(BaseModel):
    """Request model for vector initialization."""
    gemini_api_key: Optional[str] = None
    company_id: Optional[str] = None  # Alternative: get key from TokenManager
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    auto_sync: bool = False


class SyncRequest(BaseModel):
    """Request model for sync operations."""
    sync_type: str = "full"  # "full", "menu_items", "ocr_mappings"
    connection_params: Optional[dict] = None


class SearchRequest(BaseModel):
    """Request model for vector search."""
    query: str
    limit: int = 5
    score_cutoff: float = 0.60
    supplier_name: Optional[str] = None
    use_hybrid: bool = True


class MappingRequest(BaseModel):
    """Request model for adding OCR mapping."""
    invoice_product_name: str
    db_mcode: str
    db_desca: str
    db_menucode: Optional[str] = None
    supplier_name: Optional[str] = ""


class BatchSearchRequest(BaseModel):
    """Request model for batch search."""
    queries: List[str]
    limit: int = 3
    score_cutoff: float = 0.60
    supplier_name: Optional[str] = None


@vector_router.post("/init")
async def init_vector_system(request: InitRequest):
    """
    Initialize the vector search system.
    
    Call this once before using vector search features.
    Requires either gemini_api_key or company_id to get key from TokenManager.
    """
    try:
        # Get API key
        api_key = request.gemini_api_key
        
        if not api_key and request.company_id:
            api_key = get_api_key_from_token_manager(request.company_id)
        
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Gemini API key required. Provide gemini_api_key or valid company_id."
            )
        
        # Initialize system
        system = initialize_vector_search_system(
            gemini_api_key=api_key,
            qdrant_host=request.qdrant_host,
            qdrant_port=request.qdrant_port,
            auto_sync=request.auto_sync
        )
        
        return {
            "status": "ok",
            "message": "Vector search system initialized",
            "ready": system.is_ready,
            "auto_sync_started": request.auto_sync
        }
        
    except Exception as e:
        logger.error(f"Vector init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.get("/status")
async def get_vector_status():
    """
    Get vector search system status and statistics.
    
    Returns:
    - System readiness
    - Qdrant connection status
    - Collection statistics
    - Embedding cache stats
    - Sync history
    """
    try:
        system = get_vector_system()
        return {
            "status": "ok",
            "data": system.get_status()
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "data": {"ready": False}
        }


@vector_router.post("/sync")
async def sync_vectors(request: SyncRequest):
    """
    Trigger vector data synchronization.
    
    Syncs SQL Server data to Qdrant vector database.
    
    sync_type options:
    - "full": Sync all data (menu_items + ocr_mappings)
    - "menu_items": Sync only menu items
    - "ocr_mappings": Sync only OCR mappings
    """
    try:
        system = get_vector_system()
        
        if not system.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Vector system not initialized. Call /vector/init first."
            )
        
        result = system.sync_now(
            connection_params=request.connection_params,
            sync_type=request.sync_type
        )
        
        return {
            "status": "ok",
            "message": f"Sync completed ({request.sync_type})",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.post("/search")
async def vector_search(request: SearchRequest):
    """
    Perform vector similarity search for a product name.
    
    Uses hybrid scoring (vector + fuzzy) for optimal accuracy.
    
    Returns top matching products from the database with:
    - Match score (0-100)
    - Vector similarity score
    - Fuzzy match score
    - Product details (mcode, menucode, desca, units, etc.)
    """
    try:
        system = get_vector_system()
        
        if not system.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Vector system not initialized. Call /vector/init first."
            )
        
        matcher = get_vector_matcher()
        
        result = matcher.match_single(
            query=request.query,
            limit=request.limit,
            score_cutoff=request.score_cutoff,
            supplier_name=request.supplier_name,
            use_hybrid=request.use_hybrid
        )
        
        return {
            "status": "ok",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.post("/search/batch")
async def vector_search_batch(request: BatchSearchRequest):
    """
    Perform batch vector search for multiple product names.
    
    More efficient than calling /search multiple times.
    """
    try:
        system = get_vector_system()
        
        if not system.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Vector system not initialized. Call /vector/init first."
            )
        
        matcher = get_vector_matcher()
        
        results = matcher.match_batch(
            queries=request.queries,
            limit=request.limit,
            score_cutoff=request.score_cutoff,
            supplier_name=request.supplier_name
        )
        
        return {
            "status": "ok",
            "data": {
                "query_count": len(request.queries),
                "results": results
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.post("/mapping")
async def add_ocr_mapping(request: MappingRequest):
    """
    Add a new OCR mapping to the vector database.
    
    Call this when a user confirms a correct product mapping.
    The mapping will be used to improve future matching accuracy.
    """
    try:
        system = get_vector_system()
        
        if not system.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Vector system not initialized. Call /vector/init first."
            )
        
        sync = get_vector_sync_service()
        
        success = sync.sync_new_mapping(
            invoice_product_name=request.invoice_product_name,
            db_mcode=request.db_mcode,
            db_desca=request.db_desca,
            supplier_name=request.supplier_name or "",
            db_menucode=request.db_menucode or request.db_mcode
        )
        
        if success:
            return {
                "status": "ok",
                "message": "Mapping added to vector database"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to add mapping"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add mapping failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.post("/sync/item")
async def sync_single_item(
    mcode: str = Form(...),
    desca: str = Form(...),
    menucode: str = Form(None),
    baseunit: str = Form(None),
    confactor: float = Form(None),
    altunit: str = Form(None),
    vat: int = Form(0)
):
    """
    Sync a single menu item to vector database.
    
    Call this after inserting/updating a menu item in SQL Server.
    """
    try:
        system = get_vector_system()
        
        if not system.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Vector system not initialized."
            )
        
        sync = get_vector_sync_service()
        
        success = sync.sync_single_item(
            mcode=mcode,
            item_data={
                'mcode': mcode,
                'desca': desca,
                'menucode': menucode or mcode,
                'baseunit': baseunit or '',
                'confactor': confactor or 0,
                'altunit': altunit or '',
                'vat': vat
            }
        )
        
        if success:
            return {
                "status": "ok",
                "message": f"Item {mcode} synced to vector database"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to sync item"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Single item sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.delete("/item/{mcode}")
async def delete_vector_item(mcode: str):
    """
    Delete a menu item from vector database.
    
    Call this after deleting a menu item from SQL Server.
    """
    try:
        system = get_vector_system()
        
        if not system.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Vector system not initialized."
            )
        
        sync = get_vector_sync_service()
        success = sync.delete_item(mcode)
        
        if success:
            return {
                "status": "ok",
                "message": f"Item {mcode} deleted from vector database"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete item"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete item failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vector_router.get("/collections")
async def list_collections():
    """
    List all Qdrant collections with their statistics.
    """
    try:
        qdrant = get_qdrant_manager()
        
        if not qdrant.is_connected:
            return {
                "status": "error",
                "message": "Qdrant not connected"
            }
        
        return {
            "status": "ok",
            "data": qdrant.get_all_collections_info()
        }
        
    except Exception as e:
        logger.error(f"List collections failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@vector_router.get("/embedding/cache")
async def get_embedding_cache_stats():
    """
    Get embedding cache statistics.
    """
    try:
        embedding = get_embedding_service()
        return {
            "status": "ok",
            "data": embedding.get_cache_stats()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@vector_router.post("/embedding/clear-cache")
async def clear_embedding_cache():
    """
    Clear the embedding cache.
    
    Use this if you want to force re-generation of embeddings.
    """
    try:
        embedding = get_embedding_service()
        embedding.clear_cache()
        return {
            "status": "ok",
            "message": "Embedding cache cleared"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
