"""
Quick Start Examples for RapidFuzz Fuzzy Matching
==================================================

This file demonstrates common usage patterns for the fuzzy matching system.
Run this file to see examples in action.
"""

from fuzzy_matcher import FuzzyMatcher, match_ocr_products
from menu_cache import get_cached_menu_items


# ========================================
# EXAMPLE 1: Basic Single Match
# ========================================

def example_1_basic_match():
    """Find the best match for a single SKU."""
    print("=" * 80)
    print("EXAMPLE 1: Basic Single Match")
    print("=" * 80)
    
    # Sample database data
    menu_items = [
        ("LACTOGEN PRO 1 BIB 24x400g INNWPB176", "menucode_001"),
        ("LACTOGEN PRO 2 BIB 24x400g INLEB086", "menucode_002"),
        ("NESCAFE CLASSIC INSTANT COFFEE 100g", "menucode_003"),
    ]
    
    # Initialize matcher
    matcher = FuzzyMatcher()
    matcher.load_menu_items(menu_items)
    
    # OCR extracted SKU (with OCR errors/variations)
    ocr_sku = "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP"
    
    # Get best match
    best = matcher.get_best_match(ocr_sku, score_cutoff=70.0)
    
    print(f"\nOCR Extracted: {ocr_sku}")
    if best:
        print(f"✓ Best Match Found:")
        print(f"  Database: {best['desca']}")
        print(f"  Code: {best['menucode']}")
        print(f"  Confidence: {best['score']}%")
    else:
        print("✗ No match found above threshold")


# ========================================
# EXAMPLE 2: Multiple Suggestions
# ========================================

def example_2_multiple_suggestions():
    """Get multiple match suggestions for user selection."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Multiple Match Suggestions")
    print("=" * 80)
    
    menu_items = [
        ("NESCAFE CLASSIC INSTANT COFFEE 100g JAR", "menucode_101"),
        ("NESCAFE CLASSIC INSTANT COFFEE 50g POUCH", "menucode_102"),
        ("NESCAFE GOLD INSTANT COFFEE 100g JAR", "menucode_103"),
        ("NESCAFE GOLD BLEND 50g REFILL", "menucode_104"),
    ]
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(menu_items)
    
    ocr_sku = "NESCAFE CLASSIC 100g"
    
    # Get top 3 suggestions
    matches = matcher.match_single(ocr_sku, limit=3, score_cutoff=60.0)
    
    print(f"\nOCR Extracted: {ocr_sku}")
    print(f"\nTop Suggestions:")
    for match in matches:
        print(f"  {match['rank']}. {match['desca']}")
        print(f"     Code: {match['menucode']}, Score: {match['score']}%")


# ========================================
# EXAMPLE 3: Full OCR Integration
# ========================================

def example_3_ocr_integration():
    """Complete workflow with OCR products."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Full OCR Product Integration")
    print("=" * 80)
    
    # Simulated OCR extraction result
    ocr_products = [
        {
            "sku": "LACTOGEN PRO1 BIB 24x400g INNWPB176 NP",
            "sku_code": "12579462",
            "quantity": 5,
            "rate": 872.82,
            "mrp": 15898.56
        },
        {
            "sku": "NESCAFE CLASSIC INSTANT COFFEE 100g JAR",
            "sku_code": "12345678",
            "quantity": 10,
            "rate": 150.00,
            "mrp": 1500.00
        }
    ]
    
    # Database menu items
    menu_items = [
        ("LACTOGEN PRO 1 BIB 24x400g INNWPB176", "menucode_001"),
        ("LACTOGEN PRO 2 BIB 24x400g INLEB086", "menucode_002"),
        ("NESCAFE CLASSIC INSTANT COFFEE 100g", "menucode_003"),
        ("NESCAFE GOLD INSTANT COFFEE 100g", "menucode_004"),
    ]
    
    # Apply fuzzy matching
    enhanced_products = match_ocr_products(
        ocr_products=ocr_products,
        menu_items=menu_items,
        top_k=2,
        score_cutoff=60.0
    )
    
    # Display results
    for i, product in enumerate(enhanced_products, 1):
        print(f"\n--- Product {i} ---")
        print(f"OCR SKU: {product['sku']}")
        print(f"Quantity: {product['quantity']}, Rate: {product['rate']}")
        
        if product['best_match']:
            print(f"\n✓ Best Match:")
            print(f"  Database: {product['best_match']['desca']}")
            print(f"  Code: {product['best_match']['menucode']}")
            print(f"  Score: {product['best_match']['score']}%")
            print(f"  Confidence: {product['match_confidence']}")
        else:
            print(f"\n✗ No match found")
        
        if len(product['fuzzy_matches']) > 1:
            print(f"\nAlternative Suggestions:")
            for alt in product['fuzzy_matches'][1:]:
                print(f"  - {alt['desca']} (Score: {alt['score']}%)")


# ========================================
# EXAMPLE 4: Scorer Comparison
# ========================================

def example_4_scorer_comparison():
    """Compare different scoring algorithms."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Scorer Algorithm Comparison")
    print("=" * 80)
    
    menu_items = [
        ("Apple iPhone 15 Pro Max 256GB", "PHONE_001"),
    ]
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(menu_items)
    
    # Different query variations
    queries = [
        "iPhone 15 Pro Max",           # Missing brand
        "Apple iPhone 15 Pro",         # Missing variant
        "iPhone Pro Max Apple 15",     # Different word order
        "iphone 15 pro max apple",     # Case variation
    ]
    
    scorers = ["token_set_ratio", "token_sort_ratio", "WRatio"]
    
    print(f"\nDatabase: {menu_items[0][0]}\n")
    
    for query in queries:
        print(f"Query: '{query}'")
        for scorer in scorers:
            matches = matcher.match_single(query, limit=1, scorer_name=scorer, score_cutoff=0)
            if matches:
                print(f"  {scorer:20s}: {matches[0]['score']:6.2f}%")
        print()


# ========================================
# EXAMPLE 5: Handling Edge Cases
# ========================================

def example_5_edge_cases():
    """Demonstrate edge case handling."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Edge Case Handling")
    print("=" * 80)
    
    menu_items = [
        ("PRODUCT ABC 123", "menucode_001"),
        ("PRODUCT XYZ 456", "menucode_002"),
    ]
    
    matcher = FuzzyMatcher()
    matcher.load_menu_items(menu_items)
    
    edge_cases = [
        ("", "Empty string"),
        ("   ", "Whitespace only"),
        ("ZZZZZZZZ", "No similarity"),
        ("AB", "Very short"),
        ("PRODUCT!@#$%", "Special characters"),
    ]
    
    for query, description in edge_cases:
        matches = matcher.match_single(query, limit=1, score_cutoff=60.0)
        result = matches[0] if matches else None
        
        print(f"\nTest: {description}")
        print(f"  Query: '{query}'")
        if result:
            print(f"  ✓ Match: {result['desca']} (Score: {result['score']}%)")
        else:
            print(f"  ✗ No match found")


# ========================================
# EXAMPLE 6: Cache Usage
# ========================================

def example_6_cache_usage():
    """Demonstrate cache functionality."""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Cache Usage")
    print("=" * 80)
    
    # Simulate database fetch
    fetch_count = [0]
    
    def fetch_from_database():
        fetch_count[0] += 1
        print(f"\n  → Fetching from database (call #{fetch_count[0]})...")
        import time
        time.sleep(0.1)  # Simulate DB latency
        return [
            ("PRODUCT A", "menucode_A"),
            ("PRODUCT B", "menucode_B"),
        ]
    
    # First call - cache miss
    print("\nFirst call (cache miss):")
    items1 = get_cached_menu_items(fetch_from_database)
    print(f"  Loaded {len(items1)} items")
    
    # Second call - cache hit
    print("\nSecond call (cache hit):")
    items2 = get_cached_menu_items(fetch_from_database)
    print(f"  Loaded {len(items2)} items")
    
    # Third call - still cache hit
    print("\nThird call (still cache hit):")
    items3 = get_cached_menu_items(fetch_from_database)
    print(f"  Loaded {len(items3)} items")
    
    print(f"\n✓ Database was queried {fetch_count[0]} time(s) for 3 requests")
    print(f"  Cache efficiency: {((3-fetch_count[0])/3)*100:.0f}%")


# ========================================
# RUN ALL EXAMPLES
# ========================================

if __name__ == "__main__":
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 15 + "RAPIDFUZZ FUZZY MATCHING - USAGE EXAMPLES" + " " * 22 + "║")
    print("╚" + "═" * 78 + "╝")
    
    example_1_basic_match()
    example_2_multiple_suggestions()
    example_3_ocr_integration()
    example_4_scorer_comparison()
    example_5_edge_cases()
    example_6_cache_usage()
    
    print("\n" + "=" * 80)
    print("All examples completed! Review the output above to understand usage.")
    print("=" * 80)
