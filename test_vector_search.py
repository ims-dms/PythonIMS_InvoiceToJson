"""
Vector Search Test Script
==========================

Tests the complete vector search integration:
1. Qdrant connection
2. Embedding generation
3. Data synchronization
4. Vector search matching

Run with: python test_vector_search.py

Prerequisites:
- Qdrant running on localhost:6333 (Docker)
- GEMINI_API_KEY set in appSetting.txt or environment
"""

import os
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_gemini_api_key():
    """Get Gemini API key from various sources."""
    # Try environment variable
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    
    # Try appSetting.txt
    try:
        with open('appSetting.txt', 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    key = line.split('=', 1)[1].strip()
                    if key:
                        return key
    except FileNotFoundError:
        pass
    
    return None


def test_qdrant_connection():
    """Test Qdrant server connection."""
    print("\n" + "="*60)
    print("TEST 1: Qdrant Connection")
    print("="*60)
    
    try:
        from qdrant_manager import initialize_qdrant, get_qdrant_manager
        
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        
        print(f"Connecting to Qdrant at {host}:{port}...")
        
        manager = initialize_qdrant(host=host, port=port)
        
        if manager.is_connected:
            print("✓ Connected successfully!")
            
            # List collections
            collections = manager.get_all_collections_info()
            print(f"✓ Found {len(collections)} collections")
            for col in collections:
                print(f"  - {col['name']}: {col['points_count']} points")
            
            return True
        else:
            print("✗ Connection failed")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_embedding_service(api_key: str):
    """Test embedding generation."""
    print("\n" + "="*60)
    print("TEST 2: Embedding Service")
    print("="*60)
    
    try:
        from embedding_service import configure_embedding_service, get_embedding_service
        
        print(f"Configuring embedding service with text-embedding-005...")
        
        service = configure_embedding_service(api_key)
        
        print(f"✓ Model: {service.model_name}")
        print(f"✓ Dimensions: {service.dimensions}")
        
        # Test single embedding
        test_text = "LACTOGEN PRO 1 BIB 24x400g INNWPB176 NP"
        print(f"\nGenerating embedding for: '{test_text}'")
        
        start = time.time()
        embedding = service.embed_text(test_text)
        elapsed = (time.time() - start) * 1000
        
        print(f"✓ Generated {len(embedding)}-dim embedding in {elapsed:.0f}ms")
        print(f"  First 5 values: {embedding[:5]}")
        
        # Test batch embedding
        test_texts = [
            "NESCAFE CLASSIC 100g JAR",
            "MAGGI NOODLES 2-MIN 70g",
            "COCA COLA 500ML PET",
            "KINGFISHER STRONG 500ML"
        ]
        
        print(f"\nGenerating batch embeddings for {len(test_texts)} items...")
        start = time.time()
        embeddings = service.embed_batch(test_texts)
        elapsed = (time.time() - start) * 1000
        
        print(f"✓ Generated {len(embeddings)} embeddings in {elapsed:.0f}ms")
        print(f"  Average: {elapsed/len(test_texts):.0f}ms per item")
        
        # Test cache
        print(f"\nCache stats: {service.get_cache_stats()}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vector_sync(api_key: str):
    """Test data synchronization."""
    print("\n" + "="*60)
    print("TEST 3: Vector Sync (Sample Data)")
    print("="*60)
    
    try:
        from qdrant_manager import get_qdrant_manager
        from embedding_service import get_embedding_service
        from vector_sync import initialize_vector_sync, get_vector_sync_service
        
        qdrant = get_qdrant_manager()
        embedding = get_embedding_service()
        
        if not qdrant.is_connected:
            print("✗ Qdrant not connected")
            return False
        
        # Initialize sync service
        sync = initialize_vector_sync(qdrant, embedding)
        
        # For testing, we'll sync a small sample
        print("Syncing menu items from database...")
        print("(This may take several minutes for 700k+ items)")
        
        # Get stats before
        stats_before = sync.get_sync_stats()
        print(f"Before sync: {stats_before}")
        
        # Perform sync with progress
        def progress_callback(current, total):
            pct = (current / total * 100) if total > 0 else 0
            print(f"  Progress: {current}/{total} ({pct:.1f}%)", end='\r')
        
        result = sync.sync_menu_items(
            batch_size=500,
            progress_callback=progress_callback
        )
        
        print("\n")
        print(f"✓ Synced {result['synced']} items in {result['duration_seconds']}s")
        print(f"  Rate: {result['records_per_second']} records/second")
        
        if result.get('errors', 0) > 0:
            print(f"  Warnings: {result['errors']} errors")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vector_search(api_key: str):
    """Test vector similarity search."""
    print("\n" + "="*60)
    print("TEST 4: Vector Search")
    print("="*60)
    
    try:
        from vector_matcher import get_vector_matcher
        from vector_config import get_vector_config
        from qdrant_manager import get_qdrant_manager
        from embedding_service import get_embedding_service
        
        qdrant = get_qdrant_manager()
        embedding = get_embedding_service()
        config = get_vector_config()
        
        if not qdrant.is_connected:
            print("✗ Qdrant not connected")
            return False
        
        # Check if we have data
        collection = config.qdrant.menu_items_collection
        count = qdrant.count_points(collection)
        print(f"Menu items in vector DB: {count}")
        
        if count == 0:
            print("✗ No items in vector database. Run sync first.")
            return False
        
        # Configure matcher
        matcher = get_vector_matcher()
        matcher.configure(qdrant, embedding, config)
        
        # Test queries
        test_queries = [
            "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP",  # Common OCR variation
            "NESCAFE CLASIC 100g",  # Typo
            "MAGGI NODLES 2 MIN",  # Typo + missing chars
            "COCA COLA 500 ML PET BOTTLE",  # Extended description
            "KINGFISHER BEER 500ML",  # Missing "STRONG"
        ]
        
        print("\nPerforming vector searches:")
        
        for query in test_queries:
            print(f"\nQuery: '{query}'")
            
            start = time.time()
            result = matcher.match_single(
                query=query,
                limit=3,
                score_cutoff=0.50,
                use_hybrid=True
            )
            elapsed = (time.time() - start) * 1000
            
            matches = result.get('matches', [])
            method = result.get('match_method', 'unknown')
            
            print(f"  Method: {method}, Time: {elapsed:.0f}ms")
            
            if matches:
                for m in matches[:3]:
                    print(f"  #{m.get('rank')}: {m.get('desca')[:50]}...")
                    print(f"      Score: {m.get('score'):.1f} (V:{m.get('vector_score', '-')}, F:{m.get('fuzzy_score', '-')})")
            else:
                print("  No matches found")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hybrid_comparison():
    """Compare vector search vs pure fuzzy matching."""
    print("\n" + "="*60)
    print("TEST 5: Hybrid vs Fuzzy Comparison")
    print("="*60)
    
    try:
        from vector_matcher import get_vector_matcher
        from fuzzy_matcher import FuzzyMatcher
        from menu_cache import get_cached_menu_items
        from db_connection import get_connection
        
        matcher = get_vector_matcher()
        
        if not matcher.is_vector_enabled:
            print("✗ Vector search not enabled")
            return False
        
        # Load fuzzy matcher cache
        def fetch_from_db():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.desca, m.mcode, m.menucode, 
                       a.BASEUOM, a.CONFACTOR, a.altunit, m.VAT
                FROM menuitem m
                LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode
                WHERE m.type = 'A' AND m.isactive = 1
            """)
            items = cursor.fetchall()
            cursor.close()
            conn.close()
            return items
        
        print("Loading menu items for comparison...")
        menu_items = get_cached_menu_items(fetch_from_db)
        matcher.load_fuzzy_cache(menu_items)
        
        # Test challenging queries
        test_cases = [
            ("LACTGEN PRO 1 400G", "OCR typo: LACTOGEN → LACTGEN"),
            ("NESTLE COFFEE 100G", "Semantic: NESCAFE CLASSIC"),
            ("BEER BOTTLE 500ML STRONG", "Word order + missing brand"),
        ]
        
        for query, description in test_cases:
            print(f"\n{description}")
            print(f"Query: '{query}'")
            
            # Vector hybrid search
            result_v = matcher.match_single(query, limit=1, use_hybrid=True)
            
            # Pure fuzzy fallback
            result_f = matcher._fuzzy_match_only(query, 1, 0.5, time.time())
            
            match_v = result_v.get('best_match')
            match_f = result_f.get('best_match')
            
            print(f"  Vector+Hybrid: {match_v.get('desca', 'N/A')[:40] if match_v else 'No match'}... (score: {match_v.get('score', 0) if match_v else 0:.1f})")
            print(f"  Fuzzy Only:    {match_f.get('desca', 'N/A')[:40] if match_f else 'No match'}... (score: {match_f.get('score', 0) if match_f else 0:.1f})")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# VECTOR SEARCH INTEGRATION TEST SUITE")
    print("#"*60)
    
    # Check for API key
    api_key = get_gemini_api_key()
    if not api_key:
        print("\n✗ ERROR: GEMINI_API_KEY not found!")
        print("  Set it in appSetting.txt or as environment variable")
        sys.exit(1)
    
    print(f"\n✓ Found API key: {api_key[:10]}...{api_key[-4:]}")
    
    # Run tests
    results = {}
    
    # Test 1: Qdrant connection
    results['qdrant'] = test_qdrant_connection()
    
    if not results['qdrant']:
        print("\n⚠️  Qdrant not running. Start it with:")
        print("    docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant")
        print("\nSkipping remaining tests...")
    else:
        # Test 2: Embedding service
        results['embedding'] = test_embedding_service(api_key)
        
        if results['embedding']:
            # Test 3: Vector sync
            results['sync'] = test_vector_sync(api_key)
            
            if results['sync']:
                # Test 4: Vector search
                results['search'] = test_vector_search(api_key)
                
                # Test 5: Comparison
                results['comparison'] = test_hybrid_comparison()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("✓ All tests passed!" if all_passed else "✗ Some tests failed"))
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
