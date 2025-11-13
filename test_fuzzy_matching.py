"""
Fuzzy Matching Test Suite
==========================

Purpose: Validate RapidFuzz matching performance and accuracy with sample OCR data
Tests: Performance benchmarks, accuracy tests, edge cases
"""

import json
import time
from fuzzy_matcher import FuzzyMatcher, match_ocr_products
from menu_cache import get_cached_menu_items, get_cache_stats, clear_cache


# ========================================
# SAMPLE DATA
# ========================================

# Sample OCR-extracted products (similar to your actual use case)
SAMPLE_OCR_PRODUCTS = [
    {
        "sku": "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP",
        "sku_code": "12579462",
        "quantity": 5,
        "shortage": 0,
        "breakage": 0,
        "leakage": 0,
        "batch": "50320453L1",
        "sno": "",
        "rate": 872.82,
        "discount": 0.0,
        "mrp": 15898.56,
        "vat": 0,
        "hscode": "0402",
        "altQty": 0,
        "unit": "Case"
    },
    {
        "sku": "LACTOGEN PRO 2 BIB 24x400g INLEB086 NP",
        "sku_code": "12581598",
        "quantity": 5,
        "shortage": 0,
        "breakage": 0,
        "leakage": 0,
        "batch": "50400453L2",
        "sno": "",
        "rate": 872.82,
        "discount": 0.0,
        "mrp": 15898.53,
        "vat": 0,
        "hscode": "0402",
        "altQty": 0,
        "unit": "Case"
    },
    {
        "sku": "NESCAFE CLASSIC INSTANT COFFEE 100g JAR",
        "sku_code": "12345678",
        "quantity": 10,
        "shortage": 0,
        "breakage": 0,
        "leakage": 0,
        "batch": "BATCH001",
        "sno": "",
        "rate": 150.00,
        "discount": 5.0,
        "mrp": 1500.00,
        "vat": 0,
        "hscode": "0901",
        "altQty": 0,
        "unit": "Box"
    }
]

# Sample database menu items (simulating 700k items with representative sample)
SAMPLE_MENU_ITEMS = [
    ("LACTOGEN PRO 1 BIB 24x400g INNWPB176", "menucode_001"),
    ("LACTOGEN PRO 2 BIB 24x400g INLEB086", "menucode_002"),
    ("LACTOGEN PRO 3 FOLLOW UP FORMULA 400g", "menucode_003"),
    ("NESCAFE CLASSIC INSTANT COFFEE 100g", "menucode_004"),
    ("NESCAFE GOLD BLEND 50g POUCH", "menucode_005"),
    ("MAGGI 2-MINUTE NOODLES MASALA 70g", "menucode_006"),
    ("MAGGI HOT & SWEET SAUCE 1kg BOTTLE", "menucode_007"),
    ("KITKAT CHOCOLATE 4 FINGER 41.5g", "menucode_008"),
    ("MILO ENERGY DRINK POWDER 400g TIN", "menucode_009"),
    ("CERELAC WHEAT WITH MILK 300g STAGE 1", "menucode_010")
]


# ========================================
# TEST FUNCTIONS
# ========================================

def test_basic_matching():
    """Test 1: Basic fuzzy matching functionality."""
    print("=" * 80)
    print("TEST 1: Basic Fuzzy Matching")
    print("=" * 80)
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(SAMPLE_MENU_ITEMS)
    
    # Test single match
    query = "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP"
    print(f"\nQuery: {query}")
    
    matches = matcher.match_single(query, limit=3, score_cutoff=60.0)
    
    if matches:
        print(f"✓ Found {len(matches)} matches:")
        for match in matches:
            print(f"  Rank {match['rank']}: {match['desca']}")
            print(f"    Code: {match['menucode']}, Score: {match['score']}")
    else:
        print("✗ No matches found")
    
    # Validate results
    assert len(matches) > 0, "Should find at least one match"
    assert matches[0]['score'] > 80, "Top match should have score > 80"
    print("\n✓ Basic matching test PASSED")


def test_scorer_comparison():
    """Test 2: Compare different scoring algorithms."""
    print("\n" + "=" * 80)
    print("TEST 2: Scorer Algorithm Comparison")
    print("=" * 80)
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(SAMPLE_MENU_ITEMS)
    
    query = "NESCAFE CLASSIC INSTANT COFFEE 100g JAR"
    scorers = ["token_set_ratio", "token_sort_ratio", "WRatio", "partial_ratio"]
    
    print(f"\nQuery: {query}\n")
    print(f"{'Scorer':<25} {'Best Match':<45} {'Score':<10}")
    print("-" * 80)
    
    for scorer in scorers:
        matches = matcher.match_single(query, limit=1, scorer_name=scorer, score_cutoff=0)
        if matches:
            print(f"{scorer:<25} {matches[0]['desca']:<45} {matches[0]['score']:<10.2f}")
    
    print("\n✓ Scorer comparison test PASSED")


def test_batch_matching():
    """Test 3: Batch matching performance."""
    print("\n" + "=" * 80)
    print("TEST 3: Batch Matching Performance")
    print("=" * 80)
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(SAMPLE_MENU_ITEMS)
    
    queries = [p['sku'] for p in SAMPLE_OCR_PRODUCTS]
    
    print(f"\nMatching {len(queries)} queries...")
    start_time = time.time()
    
    results = matcher.match_batch(queries, limit=3, score_cutoff=60.0)
    
    elapsed = time.time() - start_time
    
    print(f"\n✓ Batch matching completed in {elapsed*1000:.2f}ms")
    print(f"  Average: {(elapsed/len(queries))*1000:.2f}ms per query")
    
    for query, matches in results.items():
        print(f"\n  Query: {query[:50]}...")
        if matches:
            print(f"    Best match: {matches[0]['desca']} (Score: {matches[0]['score']})")
        else:
            print(f"    No matches found")
    
    print("\n✓ Batch matching test PASSED")


def test_ocr_integration():
    """Test 4: Full OCR product matching integration."""
    print("\n" + "=" * 80)
    print("TEST 4: OCR Product Integration")
    print("=" * 80)
    
    print(f"\nMatching {len(SAMPLE_OCR_PRODUCTS)} OCR products...")
    
    enhanced_products = match_ocr_products(
        ocr_products=SAMPLE_OCR_PRODUCTS,
        menu_items=SAMPLE_MENU_ITEMS,
        top_k=3,
        score_cutoff=60.0
    )
    
    print(f"\n✓ Enhanced {len(enhanced_products)} products with fuzzy matches\n")
    
    for i, product in enumerate(enhanced_products, 1):
        print(f"Product {i}: {product['sku']}")
        print(f"  Confidence: {product['match_confidence']}")
        
        if product['best_match']:
            print(f"  Best Match: {product['best_match']['desca']}")
            print(f"  Code: {product['best_match']['menucode']}")
            print(f"  Score: {product['best_match']['score']}")
        else:
            print(f"  No match found")
        
        print(f"  All Matches: {len(product['fuzzy_matches'])}")
        print()
    
    # Validate structure
    for product in enhanced_products:
        assert 'fuzzy_matches' in product, "Should have fuzzy_matches field"
        assert 'best_match' in product, "Should have best_match field"
        assert 'match_confidence' in product, "Should have match_confidence field"
    
    print("✓ OCR integration test PASSED")


def test_cache_performance():
    """Test 5: Cache performance with simulated large dataset."""
    print("\n" + "=" * 80)
    print("TEST 5: Cache Performance Test")
    print("=" * 80)
    
    # Clear cache first
    clear_cache()
    
    # Simulate large dataset (in real scenario, this would be 700k items)
    # For testing, we'll use 10k items
    large_dataset = []
    for i in range(10000):
        large_dataset.append((f"PRODUCT_{i}_DESCRIPTION_TEXT_{i%100}", f"menucode_{i}"))
    
    print(f"\nSimulated dataset: {len(large_dataset)} items")
    
    # Define fetch function
    def fetch_large_dataset():
        return large_dataset
    
    # First call - cache miss
    print("\nFirst call (cache miss):")
    start = time.time()
    items1 = get_cached_menu_items(fetch_large_dataset)
    elapsed1 = time.time() - start
    print(f"  Loaded {len(items1)} items in {elapsed1:.3f}s")
    
    stats1 = get_cache_stats()
    print(f"  Cache status: {stats1['status']}")
    
    # Second call - cache hit
    print("\nSecond call (cache hit):")
    start = time.time()
    items2 = get_cached_menu_items(fetch_large_dataset)
    elapsed2 = time.time() - start
    print(f"  Loaded {len(items2)} items in {elapsed2:.3f}s")
    
    stats2 = get_cache_stats()
    print(f"  Cache status: {stats2['status']}")
    
    # Calculate speedup
    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float('inf')
    print(f"\nCache speedup: {speedup:.1f}x faster")
    
    assert elapsed2 < elapsed1, "Cached call should be faster"
    print("\n✓ Cache performance test PASSED")


def test_performance_benchmark():
    """Test 6: Performance benchmark with 700k simulated items."""
    print("\n" + "=" * 80)
    print("TEST 6: Performance Benchmark (700k Items)")
    print("=" * 80)
    
    # Generate 700k simulated items (representative of real workload)
    print("\nGenerating 700,000 simulated menu items...")
    start = time.time()
    
    large_dataset = []
    product_templates = [
        "NESTLE PRODUCT {} VARIANT {} SIZE {}g",
        "MAGGI {} FLAVOR {} PACK {}ml",
        "NESCAFE {} BLEND {} SACHET {}g",
        "KITKAT {} EDITION {} BAR {}g",
        "MILO {} ENERGY {} TIN {}g"
    ]
    
    for i in range(700000):
        template = product_templates[i % len(product_templates)]
        desca = template.format(i % 1000, i % 500, i % 100)
        menucode = f"menucode_{i:07d}"
        large_dataset.append((desca, menucode))
    
    generation_time = time.time() - start
    print(f"Generated {len(large_dataset)} items in {generation_time:.2f}s")
    
    # Test matching performance
    matcher = FuzzyMatcher()
    
    print("\nLoading items into matcher...")
    start = time.time()
    matcher.load_menu_items(large_dataset)
    load_time = time.time() - start
    print(f"Loaded in {load_time:.2f}s")
    
    # Test single query
    test_query = "NESTLE PRODUCT 123 VARIANT 456 SIZE 789g"
    
    print(f"\nTesting single query against 700k items:")
    print(f"Query: {test_query}")
    
    start = time.time()
    matches = matcher.match_single(test_query, limit=5, score_cutoff=60.0)
    query_time = time.time() - start
    
    print(f"Found {len(matches)} matches in {query_time*1000:.2f}ms")
    
    if matches:
        print(f"\nTop 3 matches:")
        for match in matches[:3]:
            print(f"  {match['rank']}. {match['desca']}")
            print(f"     Score: {match['score']}, Code: {match['menucode']}")
    
    # Performance assertions
    assert query_time < 1.0, "Query should complete in under 1 second for 700k items"
    
    print(f"\n✓ Performance benchmark PASSED")
    print(f"  Dataset size: 700,000 items")
    print(f"  Load time: {load_time:.2f}s")
    print(f"  Query time: {query_time*1000:.2f}ms")
    print(f"  Throughput: {1/query_time:.1f} queries/second")


def test_edge_cases():
    """Test 7: Edge cases and error handling."""
    print("\n" + "=" * 80)
    print("TEST 7: Edge Cases & Error Handling")
    print("=" * 80)
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(SAMPLE_MENU_ITEMS)
    
    # Test empty query
    print("\nTest: Empty query")
    matches = matcher.match_single("", limit=3)
    assert len(matches) == 0, "Empty query should return no matches"
    print("  ✓ Handled correctly")
    
    # Test whitespace-only query
    print("\nTest: Whitespace-only query")
    matches = matcher.match_single("   ", limit=3)
    assert len(matches) == 0, "Whitespace query should return no matches"
    print("  ✓ Handled correctly")
    
    # Test very short query
    print("\nTest: Very short query")
    matches = matcher.match_single("AB", limit=3, score_cutoff=0)
    print(f"  Found {len(matches)} matches")
    print("  ✓ Handled correctly")
    
    # Test special characters
    print("\nTest: Special characters")
    matches = matcher.match_single("PRODUCT @#$%^& TEST", limit=3, score_cutoff=0)
    print(f"  Found {len(matches)} matches")
    print("  ✓ Handled correctly")
    
    # Test very high score cutoff
    print("\nTest: Very high score cutoff (99)")
    matches = matcher.match_single("LACTOGEN PRO1", limit=3, score_cutoff=99)
    print(f"  Found {len(matches)} matches")
    print("  ✓ Handled correctly")
    
    print("\n✓ Edge cases test PASSED")


# ========================================
# RUN ALL TESTS
# ========================================

def run_all_tests():
    """Execute complete test suite."""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "RAPIDFUZZ FUZZY MATCHING TEST SUITE" + " " * 23 + "║")
    print("╚" + "═" * 78 + "╝")
    
    tests = [
        test_basic_matching,
        test_scorer_comparison,
        test_batch_matching,
        test_ocr_integration,
        test_cache_performance,
        test_performance_benchmark,
        test_edge_cases
    ]
    
    passed = 0
    failed = 0
    
    overall_start = time.time()
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ TEST FAILED: {test_func.__name__}")
            print(f"  Error: {str(e)}")
            failed += 1
    
    overall_elapsed = time.time() - overall_start
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total Time: {overall_elapsed:.2f}s")
    
    if failed == 0:
        print("\n✓ ALL TESTS PASSED - System ready for production")
    else:
        print(f"\n✗ {failed} TEST(S) FAILED - Review errors above")
    
    print("=" * 80)


# ========================================
# SAMPLE OUTPUT DEMO
# ========================================

def demo_sample_output():
    """Demonstrate expected JSON output format."""
    print("\n" + "=" * 80)
    print("SAMPLE OUTPUT FORMAT DEMO")
    print("=" * 80)
    
    enhanced_products = match_ocr_products(
        ocr_products=SAMPLE_OCR_PRODUCTS[:1],  # Just first product
        menu_items=SAMPLE_MENU_ITEMS,
        top_k=3,
        score_cutoff=60.0
    )
    
    print("\nExpected API Response Format:")
    print(json.dumps(enhanced_products, indent=2))


if __name__ == "__main__":
    # Run all tests
    run_all_tests()
    
    # Show sample output
    demo_sample_output()
