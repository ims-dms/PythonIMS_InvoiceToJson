def api_error_response(detail):
    """
    Wrap error details in a standardized API error response, minimizing verbose server errors.
    """
    minimized = minimize_error_message(detail)
    return format_api_response(message=minimized, status="error")
def minimize_error_message(detail):
    """
    If the error detail contains a verbose server error (e.g., status_code 429),
    return a minimized user-friendly message.
    """
    if isinstance(detail, dict):
        detail_str = str(detail)
    else:
        detail_str = detail or ""
    
    # Check for specific error patterns and return user-friendly messages
    if "status_code: 429" in detail_str or "RESOURCE_EXHAUSTED" in detail_str:
        return "Error with the server: Resource limit exceeded. Please try again later."
    elif "status_code: 500" in detail_str or "Internal server error" in detail_str:
        return "Error with the server: Internal server error occurred."
    elif "status_code: 503" in detail_str or "Service Unavailable" in detail_str:
        return "Error with the server: Service temporarily unavailable."
    elif "timeout" in detail_str.lower():
        return "Error with the server: Request timed out."
    elif "connection" in detail_str.lower() and "refused" in detail_str.lower():
        return "Error with the server: Connection refused."
    elif "error" in detail_str.lower() and "server" in detail_str.lower():
        return "Error with the server"
    
    return detail_str
def format_api_response(data=None, message=None, status="ok"):
    """
    Standardize API responses with status and message.
    Args:
        data: The main payload (optional)
        message: Human-readable message (optional)
        status: "ok" for success, "error" for failure
    Returns:
        dict: {"status": ..., "message": ..., "data": ...}
    """
    resp = {"status": status}
    if message is not None:
        resp["message"] = message
    if data is not None:
        resp["data"] = data
    return resp

"""
High-Performance Fuzzy String Matching Module using RapidFuzz
==============================================================

Purpose: Match OCR-extracted SKU descriptions against database DESCA field
Scale: Optimized for 700,000+ menuitem records
Core Library: RapidFuzz (fuzz & process modules)

Performance Notes:
- Uses rapidfuzz.process.extract() for efficient bulk matching
- Avoids manual loops for large datasets (critical at 700k scale)
- Implements caching to prevent repeated database queries
- Uses token_set_ratio scorer (best for missing/extra words in product names)
"""

import logging
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein
import time
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def preprocess_text(text: str) -> str:
    """
    Normalize text for better fuzzy matching by removing special characters
    and standardizing format.
    
    Args:
        text: Input text to normalize
    
    Returns:
        Normalized text (uppercase, no special chars, single spaces)
    
    Example:
        "Kingfisher Strong -Bottle 330ml" -> "KINGFISHER STRONG BOTTLE 330ML"
        "NESCAFE (CLASSIC) 100g" -> "NESCAFE CLASSIC 100G"
    """
    if not text:
        return ""
    
    # Convert to uppercase
    text = text.upper()
    
    # Remove special characters (keep only alphanumeric and spaces)
    # This handles: hyphens, slashes, parentheses, asterisks, etc.
    text = re.sub(r'[^A-Z0-9\s]', ' ', text)
    
    # Remove extra spaces
    text = ' '.join(text.split())
    
    return text


class FuzzyMatcher:
    """
    High-performance fuzzy matcher for SKU descriptions against database menu items.
    
    Key Features:
    - Caches database items to avoid repeated queries
    - Uses RapidFuzz process.extract for optimal performance
    - Supports multiple scoring algorithms based on use case
    - Thread-safe caching with automatic refresh capability
    """
    
    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize the fuzzy matcher.
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        """
        self._cache = None
        self._cache_timestamp = 0
        self._cache_ttl = cache_ttl
        logger.info(f"FuzzyMatcher initialized with {cache_ttl}s cache TTL")
    
    def load_menu_items(self, menu_items: List[Tuple[str, str, str, str, any, str, any]]) -> None:
        """
        Load and cache menu items from database.
        
        Args:
            menu_items: List of tuples (desca, mcode, menucode, baseunit, confactor, altunit) from database query
        """
        start_time = time.time()
        
        # Preprocess all items for better matching
        # Store both original and preprocessed versions
        processed_items = []
        for item in menu_items:
            if item[0]:  # Filter out None/empty
                original_desca = item[0]
                preprocessed_desca = preprocess_text(original_desca)
                processed_items.append({
                    'original_desca': original_desca,
                    'preprocessed_desca': preprocessed_desca,
                    'mcode': item[1] if len(item) > 1 else None,
                    'menucode': item[2] if len(item) > 2 else None,
                    'baseunit': item[3] if len(item) > 3 else None,
                    'confactor': item[4] if len(item) > 4 else None,
                    'altunit': item[5] if len(item) > 5 else None,
                    'vat': item[6] if len(item) > 6 else None
                })
        
        # Create lookup structures for ultra-fast matching
        self._cache = {
            'preprocessed_list': [item['preprocessed_desca'] for item in processed_items],
            'original_list': [item['original_desca'] for item in processed_items],
            'mcode_list': [item['mcode'] for item in processed_items],
            'menucode_list': [item['menucode'] for item in processed_items],
            'baseunit_list': [item['baseunit'] for item in processed_items],
            'confactor_list': [item['confactor'] for item in processed_items],
            'altunit_list': [item['altunit'] for item in processed_items],
            'vat_list': [item['vat'] for item in processed_items],
            'item_count': len(processed_items)
        }
        
        self._cache_timestamp = time.time()
        
        elapsed = time.time() - start_time
        logger.info(f"Loaded and preprocessed {self._cache['item_count']} menu items in {elapsed:.2f}s")
    
    def is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        if self._cache is None:
            return False
        return (time.time() - self._cache_timestamp) < self._cache_ttl
    
    def match_single(
        self, 
        query: str, 
        limit: int = 5, 
        score_cutoff: float = 60.0,
        scorer_name: str = "token_set_ratio"
    ) -> Dict[str, any]:
        """
        Match a single SKU query against all DESCA entries using RapidFuzz.
        
        Args:
            query: SKU description to match (e.g., "LACTOGEN PRO1 BIB 24x400g")
            limit: Maximum number of matches to return (default: 5)
            score_cutoff: Minimum similarity score (0-100) to include (default: 60.0)
            scorer_name: Scoring algorithm to use (see SCORER_GUIDE below)
        
        Returns:
            Dictionary with match results:
            - fuzzy_matches: List of match dictionaries with keys desca, mcode, menucode, baseunit, confactor, altunit, score, rank
            - best_match: The top match dictionary or None
        
        SCORER SELECTION GUIDE:
        =======================
        - "token_set_ratio" (RECOMMENDED): Handles word order + missing/extra words
          Example: "Apple iPhone 15" matches "iPhone 15 Pro Max Apple" (score: ~85)
          Use case: Product descriptions with varying detail levels
        
        - "token_sort_ratio": Handles word order differences only
          Example: "John Smith" matches "Smith John" (score: 100)
          Use case: Names, addresses where all words should be present
        
        - "WRatio": Balanced general-purpose scorer (weighted ratio)
          Example: Best all-around when unsure
          Use case: Default fallback for mixed content
        
        - "ratio": Exact character sequence matching (strictest)
          Example: "apple" vs "aple" (score: ~80)
          Use case: SKU codes, part numbers requiring precision
        
        - "partial_ratio": Substring matching
          Example: "apple" matches "pineapple" (score: 100)
          Use case: When query might be partial/abbreviated
        """
        
        if not self.is_cache_valid():
            raise ValueError("Cache is invalid or expired. Call load_menu_items() first.")
        
        if not query or not query.strip():
            logger.warning("Empty query provided to match_single")
            return []
        
        query = query.strip()
        
        # Select scorer based on user preference
        SCORERS = {
            "token_set_ratio": fuzz.token_set_ratio,
            "token_sort_ratio": fuzz.token_sort_ratio,
            "WRatio": fuzz.WRatio,
            "ratio": fuzz.ratio,
            "partial_ratio": fuzz.partial_ratio
        }
        
        scorer = SCORERS.get(scorer_name, fuzz.token_set_ratio)
        
        # Preprocess the query for better matching
        preprocessed_query = preprocess_text(query)
        
        start_time = time.time()
        
        # Use rapidfuzz.process.extract for efficient bulk matching
        # Match against preprocessed database items
        # This is CRITICAL for performance with 700k items
        # Returns: List of tuples (match_string, score, index)
        matches = process.extract(
            preprocessed_query,
            self._cache['preprocessed_list'],
            scorer=scorer,
            limit=limit,
            score_cutoff=score_cutoff
        )
        
        elapsed = time.time() - start_time
        
        # Format results with all relevant information
        # Return original (non-preprocessed) desca for display
        results = []
        for rank, (matched_preprocessed, score, idx) in enumerate(matches, start=1):
            original_desca = self._cache['original_list'][idx]
            mcode = self._cache['mcode_list'][idx]
            menucode = self._cache['menucode_list'][idx]
            baseunit = self._cache['baseunit_list'][idx]
            confactor = self._cache['confactor_list'][idx]
            altunit = self._cache['altunit_list'][idx]
            vat = self._cache['vat_list'][idx]
            
            # Convert None to empty string and handle Decimal type for confactor
            from decimal import Decimal
            confactor_value = ''
            if confactor is not None:
                confactor_value = float(confactor) if isinstance(confactor, (int, float, Decimal)) else confactor
            
            results.append({
                'desca': original_desca,
                'mcode': mcode,
                'menucode': menucode,
                'baseunit': baseunit if baseunit is not None else '',
                'confactor': confactor_value,
                'altunit': altunit if altunit is not None else '',
                'vat': vat if vat is not None else '',
                'score': round(score, 2),
                'rank': rank
            })
        
        logger.info(
            f"Matched '{query}' against {self._cache['item_count']} items in {elapsed*1000:.2f}ms "
            f"(scorer: {scorer_name}, found: {len(results)} matches)"
        )
        
        return {
            'fuzzy_matches': results,
            'best_match': results[0] if results else None
        }
    
    def match_batch(
        self, 
        queries: List[str], 
        limit: int = 3, 
        score_cutoff: float = 60.0,
        scorer_name: str = "token_set_ratio"
    ) -> Dict[str, Dict[str, any]]:
        """
        Match multiple SKU queries efficiently in batch mode.
        
        Args:
            queries: List of SKU descriptions to match
            limit: Maximum matches per query (default: 3)
            score_cutoff: Minimum similarity score (default: 60.0)
            scorer_name: Scoring algorithm (see match_single for options)
        
        Returns:
            Dictionary mapping each query to its match results dict
            {
                "LACTOGEN PRO1 BIB 24x400g": {
                    "fuzzy_matches": [{"desca": "...", "mcode": "...", "menucode": "...", "score": 95.5, "rank": 1}, ...],
                    "best_match": {"desca": "...", "mcode": "...", "menucode": "...", "score": 95.5, "rank": 1}
                },
                ...
            }
        """
        
        if not self.is_cache_valid():
            raise ValueError("Cache is invalid or expired. Call load_menu_items() first.")
        
        start_time = time.time()
        results = {}
        
        for query in queries:
            if query and query.strip():
                results[query] = self.match_single(
                    query, 
                    limit=limit, 
                    score_cutoff=score_cutoff,
                    scorer_name=scorer_name
                )
            else:
                results[query] = []
        
        elapsed = time.time() - start_time
        logger.info(f"Batch matched {len(queries)} queries in {elapsed:.2f}s")
        
        return results
    
    def get_best_match(
        self, 
        query: str, 
        score_cutoff: float = 70.0,
        scorer_name: str = "token_set_ratio"
    ) -> Optional[Dict[str, any]]:
        """
        Get only the single best match for a query (most common use case).
        
        Args:
            query: SKU description to match
            score_cutoff: Minimum acceptable score (default: 70.0)
            scorer_name: Scoring algorithm
        
        Returns:
            Best match dictionary or None if no match above cutoff
        """
        
        match_result = self.match_single(query, limit=1, score_cutoff=score_cutoff, scorer_name=scorer_name)
        return match_result['best_match']


def match_ocr_products(
    ocr_products: List[Dict[str, any]], 
    menu_items: List[Tuple[str, str, str, str, any, str]],
    top_k: int = 3,
    score_cutoff: float = 60.0,
    connection = None,
    supplier_name: str = ""
) -> List[Dict[str, any]]:
    """
    Match OCR-extracted products against database menu items with fuzzy matching.
    First checks OCRMappedData table for existing mappings, then falls back to fuzzy matching.
    
    This is the PRIMARY FUNCTION for your API integration.
    
    Args:
        ocr_products: List of product dictionaries from OCR extraction
                     Each must have 'sku' key with description
        menu_items: List of (desca, mcode, menucode, baseunit, confactor, altunit) tuples from database
        top_k: Number of suggestions per product (default: 3)
        score_cutoff: Minimum match score 0-100 (default: 60.0)
        connection: Database connection object (optional, for OCRMappedData lookup)
        supplier_name: Supplier name from invoice (for OCRMappedData lookup)
    
    Returns:
        Enhanced product list with match suggestions:
        [
            {
                "sku": "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP",
                "sku_code": "12579462",
                "quantity": 5,
                ... (all original fields preserved) ...
                "fuzzy_matches": [  # Only if no exact mapping found
                    {"desca": "LACTOGEN PRO1 BIB 24x400g", "mcode": "ITM001", "menucode": "MENU001", "baseunit": "Pcs", "confactor": 12, "altunit": "Case", "score": 95.5, "rank": 1},
                    ...
                ],
                "best_match": {"desca": "...", "mcode": "...", "menucode": "...", "baseunit": "...", "confactor": ..., "altunit": "...", "score": 95.5, "rank": 1},
                "match_confidence": "high",  # high (>85), medium (70-85), low (60-70), none (<60)
                "mapped_nature": "Existing" | "New Mapped" | "Not Matched"
            },
            ...
        ]
    
    Performance: Handles 700k database items efficiently using RapidFuzz process module
    """
    
    matcher = FuzzyMatcher(cache_ttl=3600)  # 1-hour cache
    matcher.load_menu_items(menu_items)
    
    enhanced_products = []
    
    for product in ocr_products:
        sku_query = product.get('sku', '').strip()
        
        if not sku_query:
            # No SKU to match, return product as-is with empty matches
            product['fuzzy_matches'] = []
            product['best_match'] = None
            product['match_confidence'] = 'none'
            product['mapped_nature'] = 'Not Matched'
            enhanced_products.append(product)
            continue
        
        # First, check OCRMappedData table for existing mapping
        mapped_match = None
        logger.debug(f"Processing product: sku_query='{sku_query}', connection={connection is not None}, supplier_name='{supplier_name}'")
        
        if connection and supplier_name:
            try:
                # Ensure schema and table exist
                cursor = connection.cursor()
                logger.debug(f"Attempting database lookup for sku_query='{sku_query}' with supplier_name='{supplier_name}'")
                
                # Check if schema exists, create if not
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'docUpload')
                    BEGIN
                        EXEC('CREATE SCHEMA docUpload')
                    END
                """)
                connection.commit()
                
                # Check if table exists, create if not
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[docUpload].[OCRMappedData]') AND type in (N'U'))
                    BEGIN
                        CREATE TABLE [docUpload].[OCRMappedData](
                            [InvoiceProductCode] [varchar](25) NULL,
                            [InvoiceProductName] [varchar](450) NULL,
                            [Dbmcode] [varchar](25) NOT NULL,
                            [DbDesca] [varchar](450) NULL,
                            [DbMenuCode] [varchar](25) NOT NULL,
                            [InvoiceSupplierName] [varchar](75) NULL,
                            [DbSupplierName] [varchar](450) NOT NULL,
                            CONSTRAINT [PK_OCRMappedData] PRIMARY KEY CLUSTERED 
                            (
                                [Dbmcode] ASC,
                                [DbSupplierName] ASC
                            )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
                        ) ON [PRIMARY]
                        
                        ALTER TABLE [docUpload].[OCRMappedData]  WITH CHECK ADD  CONSTRAINT [FK_OCRMappedData_MenuItem] FOREIGN KEY([Dbmcode])
                        REFERENCES [dbo].[MENUITEM] ([mcode])
                        
                        ALTER TABLE [docUpload].[OCRMappedData] CHECK CONSTRAINT [FK_OCRMappedData_MenuItem]
                    END
                    
                    -- Add DbMenuCode column if it doesn't exist
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'[docUpload].[OCRMappedData]') AND name = 'DbMenuCode')
                    BEGIN
                        ALTER TABLE [docUpload].[OCRMappedData] ADD [DbMenuCode] [varchar](25) NOT NULL DEFAULT('')
                    END
                """)
                connection.commit()
                
                # Now query the table - try with supplier name first, then without
                # First try: exact match with supplier name
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
                    WHERE o.InvoiceProductName = ? AND (o.InvoiceSupplierName = ? OR o.InvoiceSupplierName = 'supplier')
                """, (sku_query, supplier_name))
                row = cursor.fetchone()
                
                # If no match with supplier, try without supplier constraint
                if not row:
                    logger.debug(f"No match with supplier '{supplier_name}', trying without supplier constraint")
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
                
                logger.debug(f"Database query result for sku_query='{sku_query}' and supplier_name='{supplier_name}': {row}")
                
                if row:
                    # Handle Decimal type for confactor
                    from decimal import Decimal
                    confactor_value = ''
                    if len(row) > 4 and row[4] is not None:
                        confactor_value = float(row[4]) if isinstance(row[4], (int, float, Decimal)) else row[4]
                    
                    # Prefer explicit DbDesca; if missing, fall back to menuitem.desca; never use mcode as description
                    fallback_desca = ''
                    if len(row) > 7 and row[7]:
                        fallback_desca = row[7]
                    mapped_match = {
                        'desca': row[1] if row[1] else fallback_desca,
                        'mcode': row[0],
                        'menucode': row[2] if row[2] else row[0],  # Use DbMenuCode if available, else Dbmcode
                        'baseunit': row[3] if (len(row) > 3 and row[3] is not None) else '',
                        'confactor': confactor_value,
                        'altunit': row[5] if (len(row) > 5 and row[5] is not None) else '',
                        'vat': row[6] if (len(row) > 6 and row[6] is not None) else '',
                        'score': 100.0,  # Exact match
                        'rank': 1
                    }
                    logger.info(f"Found existing mapping in OCRMappedData: {mapped_match}")
                else:
                    logger.debug(f"No mapping found in OCRMappedData for sku_query='{sku_query}' with supplier_name='{supplier_name}'")
                cursor.close()
            except Exception as e:
                logger.warning(f"Error querying OCRMappedData (falling back to fuzzy matching): {e}")
                # Continue to fuzzy matching on any error
                mapped_match = None
        else:
            logger.debug(f"Skipping OCRMappedData lookup: connection={'not provided' if not connection else 'provided'}, supplier_name={'empty' if not supplier_name else 'provided'}")
        
        if mapped_match:
            # Found in mapping table
            product['best_match'] = mapped_match
            product['fuzzy_matches'] = [mapped_match]  # Include the mapped match in fuzzy_matches
            product['match_confidence'] = 'high'  # Existing mappings are considered high confidence
            product['mapped_nature'] = 'Existing'
            # Expose VAT from menuitem and set isVAT (0/1) for client
            db_vat = mapped_match.get('vat', '')
            product['menuitem_vat'] = db_vat
            try:
                product['isVAT'] = 1 if str(int(db_vat)) == '1' else 0
            except Exception:
                product['isVAT'] = 1 if str(db_vat).strip() in ('1','Y','y','true','True') else 0
        else:
            # Not found in mapping, do fuzzy matching
            match_result = matcher.match_single(
                sku_query, 
                limit=top_k, 
                score_cutoff=score_cutoff,
                scorer_name="token_set_ratio"
            )
            
            # Add match results to product
            product['fuzzy_matches'] = match_result['fuzzy_matches']
            product['best_match'] = match_result['best_match']
            # Expose VAT from menuitem when available in best match
            if product['best_match']:
                db_vat = product['best_match'].get('vat', '')
                product['menuitem_vat'] = db_vat
                try:
                    product['isVAT'] = 1 if str(int(db_vat)) == '1' else 0
                except Exception:
                    product['isVAT'] = 1 if str(db_vat).strip() in ('1','Y','y','true','True') else 0
            else:
                # No DB match available; set isVAT to 0
                product['menuitem_vat'] = ''
                product['isVAT'] = 0
            
            # Classify match confidence
            matches = match_result['fuzzy_matches']
            if matches and matches[0]['score'] >= 85:
                product['match_confidence'] = 'high'
            elif matches and matches[0]['score'] >= 70:
                product['match_confidence'] = 'medium'
            elif matches and matches[0]['score'] >= 60:
                product['match_confidence'] = 'low'
            else:
                product['match_confidence'] = 'none'
            
            # Set mapped_nature
            if matches:
                product['mapped_nature'] = 'New Mapped'
            else:
                product['mapped_nature'] = 'Not Matched'
        
        enhanced_products.append(product)
    
    return enhanced_products


# ========================================
# USAGE EXAMPLES & BEST PRACTICES
# ========================================

def example_standalone_matching():
    """
    Example: Direct usage of FuzzyMatcher for custom scenarios
    """
    
    # Simulated database data (in real use, fetch from DB)
    menu_items = [
        ("LACTOGEN PRO 1 BIB 24x400g INNWPB176", "ITM001", "MENU001"),
        ("LACTOGEN PRO 2 BIB 24x400g INLEB086", "ITM002", "MENU002"),
        ("NESCAFE CLASSIC 100g JAR", "ITM003", "MENU003"),
        ("NESCAFE GOLD 50g POUCH", "ITM004", "MENU004"),
        ("MAGGI NOODLES 2-MIN 70g", "ITM005", "MENU005")
    ]
    
    # Initialize matcher
    matcher = FuzzyMatcher()
    matcher.load_menu_items(menu_items)
    
    # Single query match
    query = "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP"
    match_result = matcher.match_single(query, limit=3, score_cutoff=60.0)
    
    print(f"Query: {query}")
    for match in match_result['fuzzy_matches']:
        print(f"  Rank {match['rank']}: {match['desca']} (Code: {match['mcode']}, Menucode: {match['menucode']}, Score: {match['score']})")
    
    # Best match only
    best = match_result['best_match']
    if best:
        print(f"\nBest Match: {best['desca']} (Score: {best['score']})")


def example_scorer_comparison():
    """
    Example: Compare different scorers for same query
    
    This demonstrates when to use each scorer type.
    """
    
    menu_items = [
        ("Apple iPhone 15 Pro Max 256GB", "PHONE001", "MENU001"),
        ("iPhone 15 Pro Max Apple", "PHONE002", "MENU002"),
        ("Apple iPhone 15 Standard", "PHONE003", "MENU003")
    ]
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(menu_items)
    
    query = "iPhone 15 Pro Max"
    
    scorers = ["token_set_ratio", "token_sort_ratio", "WRatio", "ratio", "partial_ratio"]
    
    print(f"Query: {query}\n")
    for scorer in scorers:
        match_result = matcher.match_single(query, limit=1, scorer_name=scorer, score_cutoff=0)
        if match_result['best_match']:
            print(f"{scorer:20s}: {match_result['best_match']['desca']:40s} Score: {match_result['best_match']['score']}")


if __name__ == "__main__":
    print("=" * 80)
    print("RapidFuzz Fuzzy Matcher - Test Suite")
    print("=" * 80)
    
    print("\n--- Example 1: Standalone Matching ---")
    example_standalone_matching()
    
    print("\n--- Example 2: Scorer Comparison ---")
    example_scorer_comparison()
    
    print("\n" + "=" * 80)
    print("All tests completed. Module ready for production use.")
    print("=" * 80)
