"""
Test script to verify OCRMappedData returns baseunit, confactor, altunit
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

def test_ocrmapped_products():
    print("\n" + "="*60)
    print("TESTING OCRMappedData WITH YOUR EXACT PRODUCTS")
    print("="*60)
    
    # Get database connection
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get menu items with new fields
    cursor.execute("""
        SELECT m.desca, m.mcode, m.menucode, a.BASEUOM as baseunit, a.CONFACTOR, a.altunit 
        FROM menuitem m 
        LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode 
        WHERE m.type = 'A' and m.isactive = 1
    """)
    menu_items = cursor.fetchall()
    print(f"\nLoaded {len(menu_items)} menu items")
    
    # Test with your exact products from Postman
    test_products = [
        {
            "sku": "Kingfisher Strong -Bottle 330ml",
            "sku_code": "",
            "quantity": 20,
            "unit": "Case"
        },
        {
            "sku": "Kingfisher Strong -Bottle 650ml",
            "sku_code": "",
            "quantity": 20,
            "unit": "Case"
        },
        {
            "sku": "Kingfisher Strong -Can 500ml",
            "sku_code": "",
            "quantity": 20,
            "unit": "Case"
        }
    ]
    
    # Run matching with supplier name
    enhanced_products = match_ocr_products(
        ocr_products=test_products,
        menu_items=menu_items,
        top_k=3,
        score_cutoff=60.0,
        connection=conn,
        supplier_name="YETI BREWERY LIMITED"
    )
    
    conn.close()
    
    # Display results
    print("\n" + "="*60)
    print("API RESPONSE (formatted JSON)")
    print("="*60)
    
    result = {
        "status": "ok",
        "message": "Invoice processed successfully",
        "data": {
            "products": convert_decimals(enhanced_products)
        }
    }
    
    print(json.dumps(result, indent=2))
    
    # Verify fields
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    all_have_fields = True
    for product in enhanced_products:
        print(f"\n✓ Product: {product['sku']}")
        print(f"  mapped_nature: {product.get('mapped_nature', 'N/A')}")
        
        if product.get('best_match'):
            best = product['best_match']
            
            # Check if fields exist
            has_baseunit = 'baseunit' in best
            has_confactor = 'confactor' in best
            has_altunit = 'altunit' in best
            
            print(f"  baseunit: {best.get('baseunit', 'MISSING')} {'✓' if has_baseunit else '✗'}")
            print(f"  confactor: {best.get('confactor', 'MISSING')} {'✓' if has_confactor else '✗'}")
            print(f"  altunit: {best.get('altunit', 'MISSING')} {'✓' if has_altunit else '✗'}")
            
            if not (has_baseunit and has_confactor and has_altunit):
                all_have_fields = False
                print("  ✗ MISSING FIELDS!")
        else:
            print("  ✗ No match found")
            all_have_fields = False
    
    print("\n" + "="*60)
    if all_have_fields:
        print("✓✓✓ SUCCESS! All products have the required fields!")
    else:
        print("✗✗✗ FAILED! Some products are missing fields!")
    print("="*60)
    
    return all_have_fields

if __name__ == "__main__":
    test_ocrmapped_products()
