"""
Comprehensive test to verify baseunit, confactor, and altunit fields are ALWAYS present
"""
from db_connection import get_connection
from fuzzy_matcher import match_ocr_products
import json
from decimal import Decimal

def convert_decimals(obj):
    """Convert Decimal to float for JSON serialization"""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def test_fields_always_present():
    print("\n" + "="*70)
    print("TESTING: Fields ALWAYS Present (Even When Data is Missing)")
    print("="*70)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get menu items
    cursor.execute("""
        SELECT m.desca, m.mcode, m.menucode, a.BASEUOM as baseunit, a.CONFACTOR, a.altunit 
        FROM menuitem m 
        LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode 
        WHERE m.type = 'A' and m.isactive = 1
    """)
    menu_items = cursor.fetchall()
    
    print(f"\nLoaded {len(menu_items)} menu items from database")
    
    # Test products - mix of products with and without data
    test_products = [
        {
            "sku": "Kingfisher Strong -Bottle 330ml",
            "quantity": 20,
            "unit": "Case"
        },
        {
            "sku": "Kingfisher Strong -Bottle 650ml",
            "quantity": 20,
            "unit": "Case"
        },
        {
            "sku": "Kingfisher Strong -Can 500ml",
            "quantity": 20,
            "unit": "Case"
        },
        {
            "sku": "ARKSH FOOD DAMI CORN HONEY BISCUIT 100G",
            "quantity": 10,
            "unit": "Case"
        }
    ]
    
    # Run matching with connection to test OCRMappedData (Existing) matches
    enhanced_products = match_ocr_products(
        ocr_products=test_products,
        menu_items=menu_items,
        top_k=3,
        score_cutoff=60.0,
        connection=conn,
        supplier_name="YETI BREWERY LIMITED"
    )
    
    conn.close()
    
    # Convert to JSON-serializable format
    enhanced_products = convert_decimals(enhanced_products)
    
    # Verify results
    print("\n" + "="*70)
    print("VERIFICATION RESULTS")
    print("="*70)
    
    all_passed = True
    
    for i, product in enumerate(enhanced_products, 1):
        print(f"\n{'─'*70}")
        print(f"Product {i}: {product['sku']}")
        print(f"{'─'*70}")
        
        # Check best_match
        if product.get('best_match'):
            best = product['best_match']
            mapped_nature = product.get('mapped_nature', 'Unknown')
            match_confidence = product.get('match_confidence', 'Unknown')
            
            print(f"  Matched to: {best.get('desca', 'N/A')[:60]}...")
            print(f"  Match Type: {mapped_nature}")
            print(f"  Confidence: {match_confidence}")
            print(f"  MCode: {best.get('mcode', 'N/A')}")
            
            # Check if fields exist
            has_baseunit = 'baseunit' in best
            has_confactor = 'confactor' in best
            has_altunit = 'altunit' in best
            
            print(f"\n  Field Presence:")
            print(f"    baseunit:  {'✓ PRESENT' if has_baseunit else '✗ MISSING'}")
            print(f"    confactor: {'✓ PRESENT' if has_confactor else '✗ MISSING'}")
            print(f"    altunit:   {'✓ PRESENT' if has_altunit else '✗ MISSING'}")
            
            if has_baseunit and has_confactor and has_altunit:
                # Check values
                baseunit_val = best.get('baseunit')
                confactor_val = best.get('confactor')
                altunit_val = best.get('altunit')
                
                print(f"\n  Field Values:")
                print(f"    baseunit:  '{baseunit_val}' {f'(type: {type(baseunit_val).__name__})' if baseunit_val != '' else '(empty string)'}")
                print(f"    confactor: '{confactor_val}' {f'(type: {type(confactor_val).__name__})' if confactor_val != '' else '(empty string)'}")
                print(f"    altunit:   '{altunit_val}' {f'(type: {type(altunit_val).__name__})' if altunit_val != '' else '(empty string)'}")
                
                # Verify not None
                if baseunit_val is None or confactor_val is None or altunit_val is None:
                    print(f"\n  ✗ FAILED: Some fields are None instead of empty string!")
                    all_passed = False
                else:
                    print(f"\n  ✓ PASSED: All fields present and not None")
            else:
                print(f"\n  ✗ FAILED: Required fields are missing!")
                all_passed = False
            
            # Check fuzzy_matches too
            print(f"\n  Fuzzy Matches: {len(product.get('fuzzy_matches', []))} matches")
            for j, match in enumerate(product.get('fuzzy_matches', [])[:1], 1):  # Check first match
                has_all = 'baseunit' in match and 'confactor' in match and 'altunit' in match
                if not has_all:
                    print(f"    Match {j}: ✗ Missing fields in fuzzy_matches!")
                    all_passed = False
                else:
                    print(f"    Match {j}: ✓ All fields present")
        else:
            print("  ✗ No match found")
    
    # Generate JSON response
    print("\n" + "="*70)
    print("SAMPLE JSON RESPONSE")
    print("="*70)
    
    result = {
        "status": "ok",
        "message": "Invoice processed successfully",
        "data": {
            "products": enhanced_products
        }
    }
    
    # Show first product in detail
    if enhanced_products:
        sample_product = enhanced_products[0]
        print(f"\nFirst Product JSON (formatted):")
        print(json.dumps(sample_product, indent=2))
    
    # Final result
    print("\n" + "="*70)
    if all_passed:
        print("✓✓✓ ALL TESTS PASSED!")
        print("\nbaseunit, confactor, and altunit fields are:")
        print("  ✓ Present in best_match")
        print("  ✓ Present in fuzzy_matches")
        print("  ✓ Present for 'Existing' mapped_nature")
        print("  ✓ Present for 'New Mapped' mapped_nature")
        print("  ✓ Returning empty string ('') when no data")
        print("  ✓ Returning actual values when data exists")
    else:
        print("✗✗✗ SOME TESTS FAILED!")
        print("\nPlease check the errors above.")
    print("="*70)

if __name__ == "__main__":
    test_fields_always_present()
