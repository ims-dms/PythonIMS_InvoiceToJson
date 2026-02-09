"""
Vector-Only Product Matcher
============================

Uses Qdrant vector search exclusively for optimal OCR product matching accuracy.
This provides pure semantic matching using 1024-dimensional embeddings.

Strategy:
1. Search vector database for semantic matches
2. Use pure vector similarity scores (cosine similarity)
3. No fuzzy matching - vector search handles semantic variations

This vector-only approach captures:
- Semantic similarity (same meaning, different words)
- Contextual understanding (related products)
- Better handling of OCR errors through semantic matching
"""

import logging
import time
from typing import List, Dict, Optional, Tuple, Any
from decimal import Decimal

from qdrant_manager import get_qdrant_manager, QdrantManager
from embedding_service import get_embedding_service, EmbeddingService
from vector_config import get_vector_config, VectorSearchConfig

logger = logging.getLogger(__name__)


class VectorMatcher:
    """
    High-accuracy product matcher using pure vector search.
    
    Provides significantly better matching than fuzzy matching by:
    1. Using 1024-dimensional semantic embeddings
    2. Cosine similarity for semantic relevance
    3. Leveraging pre-trained language model understanding
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
        
        self._qdrant: Optional[QdrantManager] = None
        self._embedding: Optional[EmbeddingService] = None
        self._config: Optional[VectorSearchConfig] = None
        self._vector_only_mode = True  # Pure vector matching
        self._initialized = True
        
        logger.info("VectorMatcher initialized (vector-only mode)")
    
    def configure(
        self,
        qdrant_manager: QdrantManager = None,
        embedding_service: EmbeddingService = None,
        config: VectorSearchConfig = None
    ):
        """
        Configure the vector matcher.
        
        Args:
            qdrant_manager: Initialized Qdrant manager
            embedding_service: Configured embedding service
            config: Vector search configuration
        """
        self._qdrant = qdrant_manager or get_qdrant_manager()
        self._embedding = embedding_service or get_embedding_service()
        self._config = config or get_vector_config()
        
        # Vector-only mode - no fuzzy fallback
        self._vector_only_mode = getattr(self._config, 'use_vector_only', True)
        
        if not self._qdrant.is_connected:
            logger.warning("Qdrant not connected - vector search unavailable")
        else:
            logger.info(f"VectorMatcher configured (vector_only={self._vector_only_mode})")
    
    def match_single(
        self,
        query: str,
        limit: int = 5,
        score_cutoff: float = 0.60,
        supplier_name: str = None,
        supplier_code: str = None,
        use_hybrid: bool = False,  # Default to vector-only
        company_id: str = None
    ) -> Dict[str, Any]:
        """
        Match a single OCR-extracted product name using vector search.
        
        Supports supplier-based filtering for more accurate matching.
        
        Args:
            query: OCR-extracted product description
            limit: Maximum number of matches to return
            score_cutoff: Minimum match score (0-1)
            supplier_name: Optional supplier name filter for context
            supplier_code: Optional supplier code filter (SUPCODE)
            use_hybrid: Ignored - always uses vector-only mode
            company_id: Optional company ID for multi-tenant setup
            
        Returns:
            Match result dictionary:
            {
                "query": str,
                "matches": List[Dict],
                "best_match": Dict or None,
                "match_method": "vector",
                "search_time_ms": float,
                "supplier_filtered": bool
            }
        """
        start_time = time.time()
        
        if not query or not query.strip():
            return {
                "query": query,
                "matches": [],
                "best_match": None,
                "match_method": "none",
                "search_time_ms": 0,
                "supplier_filtered": False
            }
        
        query = query.strip()
        
        # Vector-only mode - requires Qdrant connection
        if not self._qdrant or not self._qdrant.is_connected:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning("Vector search unavailable - Qdrant not connected")
            return {
                "query": query,
                "matches": [],
                "best_match": None,
                "match_method": "vector_unavailable",
                "search_time_ms": round(elapsed_ms, 2),
                "error": "Qdrant vector database not connected",
                "supplier_filtered": False
            }
        
        try:
            # Strategy: Try supplier-filtered search first, then fall back to general search
            supplier_filtered = False
            vector_results = None
            
            # If supplier info provided, try filtered search first
            if supplier_name or supplier_code:
                vector_results = self._vector_search(
                    query,
                    limit=limit,
                    supplier_name=supplier_name,
                    supplier_code=supplier_code,
                    company_id=company_id
                )
                if vector_results:
                    supplier_filtered = True
                    logger.debug(f"Found {len(vector_results)} supplier-filtered results for '{query}'")
            
            # Fall back to general search if no supplier results
            if not vector_results:
                vector_results = self._vector_search(
                    query,
                    limit=limit,
                    supplier_name=None,
                    supplier_code=None,
                    company_id=company_id
                )
            
            if not vector_results:
                elapsed_ms = (time.time() - start_time) * 1000
                return {
                    "query": query,
                    "matches": [],
                    "best_match": None,
                    "match_method": "vector",
                    "search_time_ms": round(elapsed_ms, 2),
                    "supplier_filtered": supplier_filtered
                }
            
            # Format vector results (pure vector scoring)
            matches = self._format_vector_results(vector_results, limit, score_cutoff)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return {
                "query": query,
                "matches": matches,
                "best_match": matches[0] if matches else None,
                "match_method": "vector",
                "search_time_ms": round(elapsed_ms, 2),
                "supplier_filtered": supplier_filtered
            }
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "query": query,
                "matches": [],
                "best_match": None,
                "match_method": "vector_error",
                "search_time_ms": round(elapsed_ms, 2),
                "error": str(e),
                "supplier_filtered": False
            }
    
    def _vector_search(
        self,
        query: str,
        limit: int = 10,
        supplier_name: str = None,
        supplier_code: str = None,
        company_id: str = None
    ) -> List[Dict]:
        """
        Perform vector similarity search in Qdrant with optional supplier filtering.
        
        Args:
            query: Search query
            limit: Max results
            supplier_name: Optional supplier name filter (acname from rmd_aclist)
            supplier_code: Optional supplier code filter (SUPCODE from menuitem)
            company_id: Optional company ID for multi-tenant collections
            
        Returns:
            List of search results from Qdrant
        """
        # First, check OCR mappings for exact matches
        ocr_results = self._search_ocr_mappings(query, supplier_name)
        if ocr_results:
            # Found existing mapping - return as high-confidence result
            logger.debug(f"Found existing OCR mapping for '{query}'")
            return ocr_results
        
        # Generate query embedding
        query_embedding = self._embedding.embed_text(query)
        
        # Get collection name (company-specific if needed)
        collection = self._config.qdrant.menu_items_collection
        if company_id:
            import re
            safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', str(company_id))[:30]
            collection = f"{safe_id}_{collection}"
        
        # Build filters for supplier-based search
        filters = {}
        if supplier_code:
            filters['supplier_code'] = supplier_code
        elif supplier_name:
            # Use supplier_name for filtering
            filters['supplier_name'] = supplier_name
        
        results = self._qdrant.search(
            collection_name=collection,
            query_vector=query_embedding,
            limit=limit,
            score_threshold=self._config.qdrant.score_threshold,
            filters=filters if filters else None
        )
        
        return results
    
    def _search_ocr_mappings(
        self,
        query: str,
        supplier_name: str = None
    ) -> List[Dict]:
        """
        Search OCR mappings collection for existing matches.
        
        This leverages previously successful mappings for better accuracy.
        """
        try:
            collection = self._config.qdrant.ocr_mappings_collection
            
            # Generate query embedding
            query_embedding = self._embedding.embed_text(query)
            
            # Build filter
            filters = {}
            if supplier_name:
                filters['supplier_name'] = supplier_name
            
            results = self._qdrant.search(
                collection_name=collection,
                query_vector=query_embedding,
                limit=1,
                score_threshold=0.95,  # High threshold for OCR mappings
                filters=filters if filters else None
            )
            
            if results and results[0]['score'] >= 0.95:
                # Convert OCR mapping to menu item format
                mapping = results[0]['payload']
                return [{
                    'id': results[0]['id'],
                    'score': results[0]['score'],
                    'payload': {
                        'mcode': mapping.get('db_mcode'),
                        'menucode': mapping.get('db_menucode', mapping.get('db_mcode')),
                        'desca': mapping.get('db_desca'),
                        'baseunit': '',
                        'confactor': 0,
                        'altunit': '',
                        'vat': 0,
                        '_source': 'ocr_mapping',
                        '_original_mapping': mapping
                    }
                }]
            
            return []
            
        except Exception as e:
            logger.debug(f"OCR mapping search failed: {e}")
            return []
    
    def _format_vector_results(
        self,
        results: List[Dict],
        limit: int,
        score_cutoff: float
    ) -> List[Dict]:
        """Format raw vector results for output (pure vector scoring)."""
        formatted = []
        
        for i, result in enumerate(results[:limit], 1):
            payload = result.get('payload', {})
            score = result.get('score', 0) * 100  # Convert to 0-100 scale
            
            if score >= score_cutoff * 100:
                formatted.append({
                    'desca': payload.get('desca', ''),
                    'mcode': payload.get('mcode', ''),
                    'menucode': payload.get('menucode', payload.get('mcode', '')),
                    'baseunit': payload.get('baseunit', ''),
                    'confactor': payload.get('confactor', 0),
                    'altunit': payload.get('altunit', ''),
                    'vat': payload.get('vat', 0),
                    'score': round(score, 2),
                    'rank': i,
                    # Supplier information
                    'supplier_code': payload.get('supplier_code', ''),
                    'supplier_name': payload.get('supplier_name', ''),
                    '_source': 'vector'
                })
        
        return formatted
    
    def match_batch(
        self,
        queries: List[str],
        limit: int = 3,
        score_cutoff: float = 0.60,
        supplier_name: str = None,
        supplier_code: str = None,
        company_id: str = None
    ) -> Dict[str, Dict]:
        """
        Match multiple queries using vector search with optional supplier filtering.
        
        Args:
            queries: List of OCR-extracted product names
            limit: Max matches per query
            score_cutoff: Minimum match score
            supplier_name: Optional supplier name filter
            supplier_code: Optional supplier code filter
            company_id: Optional company ID for multi-tenant setup
            
        Returns:
            Dictionary mapping queries to their match results
        """
        results = {}
        
        for query in queries:
            if query and query.strip():
                results[query] = self.match_single(
                    query,
                    limit=limit,
                    score_cutoff=score_cutoff,
                    supplier_name=supplier_name,
                    supplier_code=supplier_code,
                    company_id=company_id
                )
            else:
                results[query] = {
                    "query": query,
                    "matches": [],
                    "best_match": None,
                    "match_method": "none",
                    "supplier_filtered": False
                }
        
        return results
    
    @property
    def is_vector_enabled(self) -> bool:
        """Check if vector search is enabled and connected."""
        return self._qdrant is not None and self._qdrant.is_connected


# Global instance accessor
def get_vector_matcher() -> VectorMatcher:
    """Get the singleton vector matcher instance."""
    return VectorMatcher()


def match_ocr_products_vector(
    ocr_products: List[Dict[str, Any]],
    menu_items: List[Tuple[str, str, str, str, Any, str, Any]],
    top_k: int = 3,
    score_cutoff: float = 0.60,
    connection = None,
    supplier_name: str = "",
    supplier_code: str = "",
    company_id: str = None,
    use_vector: bool = True
) -> List[Dict[str, Any]]:
    """
    Match OCR-extracted products using pure vector search with supplier filtering.
    
    Uses 768-dimensional embeddings for semantic matching.
    Supports supplier-based filtering for more accurate matching.
    
    Args:
        ocr_products: List of product dicts with 'sku' key
        menu_items: Not used in vector-only mode
        top_k: Number of suggestions per product
        score_cutoff: Minimum match score (0-1)
        connection: Optional DB connection for OCR mapping lookup
        supplier_name: Supplier name for filtering (from invoice)
        supplier_code: Supplier code for filtering (SUPCODE)
        company_id: Optional company ID for multi-tenant setup
        use_vector: Always True - vector-only mode
        
    Returns:
        Enhanced product list with vector match suggestions.
        Matches are filtered by supplier first, then falls back to general search.
    """
    matcher = get_vector_matcher()
    
    enhanced_products = []
    
    for product in ocr_products:
        sku_query = product.get('sku', '').strip()
        
        if not sku_query:
            product['fuzzy_matches'] = []
            product['best_match'] = None
            product['match_confidence'] = 'none'
            product['mapped_nature'] = 'Not Matched'
            product['match_method'] = 'none'
            product['supplier_filtered'] = False
            enhanced_products.append(product)
            continue
        
        # First check SQL Server OCRMappedData (existing mappings take priority)
        mapped_match = _check_sql_mapping(sku_query, supplier_name, connection)
        
        if mapped_match:
            product['best_match'] = mapped_match
            product['fuzzy_matches'] = [mapped_match]
            product['match_confidence'] = 'high'
            product['mapped_nature'] = 'Existing'
            product['match_method'] = 'sql_mapping'
            product['supplier_filtered'] = False
            # Set VAT info
            _set_vat_info(product, mapped_match)
        else:
            # Pure vector search with supplier filtering
            result = matcher.match_single(
                sku_query,
                limit=top_k,
                score_cutoff=score_cutoff,
                supplier_name=supplier_name,
                supplier_code=supplier_code,
                company_id=company_id,
                use_hybrid=False  # Vector-only
            )
            
            matches = result.get('matches', [])
            best = result.get('best_match')
            method = result.get('match_method', 'vector')
            
            product['fuzzy_matches'] = matches  # Keep key name for compatibility
            product['best_match'] = best
            product['match_method'] = method
            product['supplier_filtered'] = result.get('supplier_filtered', False)
            
            # Classify confidence based on vector scores
            if matches and matches[0].get('score', 0) >= 85:
                product['match_confidence'] = 'high'
            elif matches and matches[0].get('score', 0) >= 70:
                product['match_confidence'] = 'medium'
            elif matches and matches[0].get('score', 0) >= 60:
                product['match_confidence'] = 'low'
            else:
                product['match_confidence'] = 'none'
            
            # Set mapped nature
            if matches:
                product['mapped_nature'] = 'New Mapped'
            else:
                product['mapped_nature'] = 'Not Matched'
            
            # Set VAT info
            if best:
                _set_vat_info(product, best)
            else:
                product['menuitem_vat'] = ''
                product['isVAT'] = 0
        
        enhanced_products.append(product)
    
    return enhanced_products


def _check_sql_mapping(
    sku_query: str,
    supplier_name: str,
    connection
) -> Optional[Dict]:
    """
    Check SQL Server OCRMappedData for existing mapping.
    
    Reuses logic from fuzzy_matcher.py for compatibility.
    """
    if not connection or not supplier_name:
        return None
    
    try:
        cursor = connection.cursor()
        
        # Try with supplier first
        cursor.execute("""
            SELECT o.DbMcode,
                   o.DbDesca,
                   o.DbMenuCode,
                   mu.BASEUOM as baseunit,
                   mu.CONFACTOR,
                   mu.altunit,
                   m.VAT as vat,
                   m.desca as menu_desca
            FROM [docUpload].[OCRMappedData] o
            LEFT JOIN menuitem m ON o.DbMcode = m.mcode
            LEFT JOIN MULTIALTUNIT mu ON mu.mcode = o.DbMcode
            WHERE o.InvoiceProductName = ? 
            AND (o.InvoiceSupplierName = ? OR o.InvoiceSupplierName = 'supplier')
        """, (sku_query, supplier_name))
        row = cursor.fetchone()
        
        if not row:
            # Try without supplier
            cursor.execute("""
                SELECT TOP 1 o.DbMcode,
                             o.DbDesca,
                             o.DbMenuCode,
                             mu.BASEUOM as baseunit,
                             mu.CONFACTOR,
                             mu.altunit,
                             m.VAT as vat,
                             m.desca as menu_desca
                FROM [docUpload].[OCRMappedData] o
                LEFT JOIN menuitem m ON o.DbMcode = m.mcode
                LEFT JOIN MULTIALTUNIT mu ON mu.mcode = o.DbMcode
                WHERE o.InvoiceProductName = ?
            """, (sku_query,))
            row = cursor.fetchone()
        
        cursor.close()
        
        if row:
            # Handle Decimal type for confactor
            confactor_value = ''
            if len(row) > 4 and row[4] is not None:
                confactor_value = float(row[4]) if isinstance(row[4], (int, float, Decimal)) else row[4]
            
            fallback_desca = row[7] if len(row) > 7 and row[7] else ''
            
            return {
                'desca': row[1] if row[1] else fallback_desca,
                'mcode': row[0],
                'menucode': row[2] if row[2] else row[0],
                'baseunit': row[3] if (len(row) > 3 and row[3]) else '',
                'confactor': confactor_value,
                'altunit': row[5] if (len(row) > 5 and row[5]) else '',
                'vat': row[6] if (len(row) > 6 and row[6] is not None) else '',
                'score': 100.0,
                'rank': 1
            }
        
        return None
        
    except Exception as e:
        logger.warning(f"SQL mapping lookup failed: {e}")
        return None


def _set_vat_info(product: Dict, match: Dict):
    """Set VAT information on product from match."""
    db_vat = match.get('vat', '')
    product['menuitem_vat'] = db_vat
    try:
        product['isVAT'] = 1 if str(int(db_vat)) == '1' else 0
    except Exception:
        product['isVAT'] = 1 if str(db_vat).strip() in ('1', 'Y', 'y', 'true', 'True') else 0
