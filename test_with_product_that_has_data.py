"""
Test API with product that HAS MULTIALTUNIT data
"""
from db_connection import get_connection
from fuzzy_matcher import match_ocr_products

def test_product_with_data():
    print("\n" + "="*60)
    print("TESTING WITH PRODUCT THAT HAS MULTIALTUNIT DATA")
    print("="*60)
    
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
    
    # Test with the product that HAS data: MHOO7477
    test_products = [
        {
            "sku": "ARKSH FOOD DAMI CORN HONEY BISCUIT 100G",
            "quantity": 10,
            "unit": "Case"
        }
    ]
    
    enhanced_products = match_ocr_products(
        ocr_products=test_products,
        menu_items=menu_items,
        top_k=3,
        score_cutoff=60.0,
        connection=conn,
        supplier_name="TEST SUPPLIER"
    )
    
    conn.close()
    
    # Display results
    import json
    from decimal import Decimal
    
    # Convert Decimal to float for JSON serialization
    def convert_decimals(obj):
        if isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(item) for item in obj]
        elif isinstance(obj, Decimal):
            return float(obj)
        return obj
    
    print("\nAPI RESPONSE (formatted JSON):")
    print("="*60)
    
    result = {
        "status": "ok",
        "message": "Invoice processed successfully",
        "data": {
            "products": convert_decimals(enhanced_products)
        }
    }
    
    print(json.dumps(result, indent=2))
    
    # Verify the fields
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    if enhanced_products[0].get('best_match'):
        best = enhanced_products[0]['best_match']
        print(f"\nProduct: {enhanced_products[0]['sku']}")
        print(f"  Matched to: {best.get('desca')}")
        print(f"  baseunit: {best.get('baseunit')} ← Should be 'PC'")
        print(f"  confactor: {best.get('confactor')} ← Should be 30.0")
        print(f"  altunit: {best.get('altunit')} ← Should be 'CASE'")
        
        if best.get('baseunit') == 'PC' and best.get('confactor') == 30.0 and best.get('altunit') == 'CASE':
            print("\n✓✓✓ SUCCESS! The API IS returning the unit data correctly!")
            print("    The issue is that your other products don't have data in MULTIALTUNIT table.")
        else:
            print("\n✗ The fields are not correct")
    else:
        print("\n✗ No match found")

if __name__ == "__main__":
    test_product_with_data()
