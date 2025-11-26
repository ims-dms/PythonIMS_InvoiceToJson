"""
Test script to verify that baseunit, confactor, and altunit are included in the API response
"""
import json

# Simulate the data structure that would come from the database
# (desca, mcode, menucode, baseunit, confactor, altunit)
test_menu_items = [
    ("NESCAFE GOLD RICH AROMA COFFEE 50GR JAR(SC) MRP-875/-", "MHOO6152", "MHOO6152", "Pcs", 12, "Case"),
    ("KINGFISHER STRONG BEER 650ML BOTTLE MRP-300", "M44493P", "M44493P", "Pcs", 12, "Case"),
    ("LACTOGEN PRO1 BIB 24x400g", "ITM001", "MENU001", "Pcs", 24, "Case"),
]

# Test the fuzzy_matcher with the new structure
from fuzzy_matcher import FuzzyMatcher

def test_match_single_with_new_fields():
    """Test that match_single returns baseunit, confactor, and altunit"""
    matcher = FuzzyMatcher(cache_ttl=3600)
    matcher.load_menu_items(test_menu_items)
    
    # Test matching
    query = "Kingfisher Strong Beer 650ml"
    result = matcher.match_single(query, limit=3, score_cutoff=60.0)
    
    print("\n=== Test Results ===")
    print(f"Query: {query}\n")
    
    if result['best_match']:
        print("Best Match:")
        best = result['best_match']
        print(f"  Description: {best['desca']}")
        print(f"  M-Code: {best['mcode']}")
        print(f"  Menu Code: {best['menucode']}")
        print(f"  Base Unit: {best.get('baseunit', 'N/A')}")
        print(f"  Conversion Factor: {best.get('confactor', 'N/A')}")
        print(f"  Alt Unit: {best.get('altunit', 'N/A')}")
        print(f"  Score: {best['score']}")
        print(f"  Rank: {best['rank']}")
    
    print("\nAll Matches:")
    for match in result['fuzzy_matches']:
        print(f"\n  Rank {match['rank']}: {match['desca']}")
        print(f"    M-Code: {match['mcode']}, Menu Code: {match['menucode']}")
        print(f"    Base Unit: {match.get('baseunit', 'N/A')}, ConFactor: {match.get('confactor', 'N/A')}, Alt Unit: {match.get('altunit', 'N/A')}")
        print(f"    Score: {match['score']}")
    
    # Verify that the new fields exist
    assert 'baseunit' in result['best_match'], "baseunit field is missing!"
    assert 'confactor' in result['best_match'], "confactor field is missing!"
    assert 'altunit' in result['best_match'], "altunit field is missing!"
    
    print("\n✓ All new fields (baseunit, confactor, altunit) are present in the response!")
    return True

def test_match_ocr_products_with_new_fields():
    """Test that match_ocr_products returns baseunit, confactor, and altunit"""
    from fuzzy_matcher import match_ocr_products
    
    # Simulate OCR products
    ocr_products = [
        {
            "sku": "Kingfisher Strong -Bottle 650ml",
            "sku_code": "",
            "quantity": 20,
            "unit": "Case"
        },
        {
            "sku": "NESCAFE GOLD RICH AROMA COFFEE 50GR JAR",
            "sku_code": "",
            "quantity": 10,
            "unit": "Case"
        }
    ]
    
    # Match products
    enhanced_products = match_ocr_products(
        ocr_products=ocr_products,
        menu_items=test_menu_items,
        top_k=3,
        score_cutoff=60.0
    )
    
    print("\n\n=== Test OCR Products Matching ===")
    for product in enhanced_products:
        print(f"\nProduct: {product['sku']}")
        if product.get('best_match'):
            best = product['best_match']
            print(f"  Matched to: {best['desca']}")
            print(f"  M-Code: {best['mcode']}")
            print(f"  Base Unit: {best.get('baseunit', 'N/A')}")
            print(f"  Conversion Factor: {best.get('confactor', 'N/A')}")
            print(f"  Alt Unit: {best.get('altunit', 'N/A')}")
            print(f"  Score: {best['score']}")
            print(f"  Confidence: {product.get('match_confidence', 'N/A')}")
            
            # Verify fields exist
            assert 'baseunit' in best, f"baseunit missing for product: {product['sku']}"
            assert 'confactor' in best, f"confactor missing for product: {product['sku']}"
            assert 'altunit' in best, f"altunit missing for product: {product['sku']}"
    
    print("\n✓ All OCR products have the new fields (baseunit, confactor, altunit)!")
    return True

if __name__ == "__main__":
    try:
        print("Testing fuzzy matcher with new fields...")
        test_match_single_with_new_fields()
        test_match_ocr_products_with_new_fields()
        print("\n" + "="*50)
        print("✓ ALL TESTS PASSED!")
        print("="*50)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
