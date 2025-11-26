"""
Diagnostic script to test if the API changes are working correctly
"""
import sys
import logging
from db_connection import get_connection
from fuzzy_matcher import match_ocr_products

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_database_query():
    """Test if the database query returns the new fields"""
    print("\n" + "="*60)
    print("TESTING DATABASE QUERY")
    print("="*60)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Test the updated query
        cursor.execute("""
            SELECT TOP 5 m.desca, m.mcode, m.menucode, a.BASEUOM as baseunit, a.CONFACTOR, a.altunit 
            FROM menuitem m 
            LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode 
            WHERE m.type = 'A' and m.isactive = 1
        """)
        
        rows = cursor.fetchall()
        
        print(f"\nRetrieved {len(rows)} rows from database")
        print("\nFirst 3 rows:")
        for i, row in enumerate(rows[:3], 1):
            print(f"\n  Row {i}:")
            print(f"    desca: {row[0][:50]}..." if len(row[0]) > 50 else f"    desca: {row[0]}")
            print(f"    mcode: {row[1]}")
            print(f"    menucode: {row[2]}")
            print(f"    baseunit: {row[3] if len(row) > 3 else 'N/A'}")
            print(f"    confactor: {row[4] if len(row) > 4 else 'N/A'}")
            print(f"    altunit: {row[5] if len(row) > 5 else 'N/A'}")
        
        cursor.close()
        conn.close()
        
        print("\n✓ Database query test PASSED - New fields are being retrieved")
        return True
        
    except Exception as e:
        print(f"\n✗ Database query test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fuzzy_matching():
    """Test if fuzzy matching returns the new fields"""
    print("\n" + "="*60)
    print("TESTING FUZZY MATCHING")
    print("="*60)
    
    try:
        # Get menu items with new fields
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.desca, m.mcode, m.menucode, a.BASEUOM as baseunit, a.CONFACTOR, a.altunit 
            FROM menuitem m 
            LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode 
            WHERE m.type = 'A' and m.isactive = 1
        """)
        menu_items = cursor.fetchall()
        cursor.close()
        
        print(f"\nLoaded {len(menu_items)} menu items")
        
        # Test products
        test_products = [
            {
                "sku": "Kingfisher Strong -Bottle 650ml",
                "quantity": 20,
                "unit": "Case"
            }
        ]
        
        # Run matching
        enhanced_products = match_ocr_products(
            ocr_products=test_products,
            menu_items=menu_items,
            top_k=3,
            score_cutoff=60.0,
            connection=conn,
            supplier_name="YETI BREWERY LIMITED"
        )
        
        conn.close()
        
        # Check results
        print("\nMatching Results:")
        for product in enhanced_products:
            print(f"\n  Product: {product['sku']}")
            if product.get('best_match'):
                best = product['best_match']
                print(f"    Matched to: {best.get('desca', 'N/A')}")
                print(f"    mcode: {best.get('mcode', 'N/A')}")
                print(f"    menucode: {best.get('menucode', 'N/A')}")
                print(f"    baseunit: {best.get('baseunit', 'MISSING!')}")
                print(f"    confactor: {best.get('confactor', 'MISSING!')}")
                print(f"    altunit: {best.get('altunit', 'MISSING!')}")
                print(f"    score: {best.get('score', 'N/A')}")
                
                # Verify fields exist
                if 'baseunit' in best and 'confactor' in best and 'altunit' in best:
                    print("    ✓ All new fields present!")
                else:
                    print("    ✗ MISSING FIELDS!")
                    return False
            else:
                print("    ✗ No match found")
                return False
        
        print("\n✓ Fuzzy matching test PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ Fuzzy matching test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ocr_mapped_data():
    """Test if OCRMappedData query includes new fields"""
    print("\n" + "="*60)
    print("TESTING OCRMappedData QUERY")
    print("="*60)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if OCRMappedData table exists and has data
        cursor.execute("""
            SELECT COUNT(*) 
            FROM [docUpload].[OCRMappedData]
        """)
        count = cursor.fetchone()[0]
        print(f"\nOCRMappedData has {count} records")
        
        if count > 0:
            # Test the updated query
            cursor.execute("""
                SELECT TOP 3 o.DbMcode, o.DbDesca, o.DbMenuCode, a.BASEUOM, a.CONFACTOR, a.altunit
                FROM [docUpload].[OCRMappedData] o
                LEFT JOIN MULTIALTUNIT a ON o.DbMcode = a.mcode
            """)
            
            rows = cursor.fetchall()
            print(f"\nRetrieved {len(rows)} rows from OCRMappedData with MULTIALTUNIT join")
            
            for i, row in enumerate(rows, 1):
                print(f"\n  Row {i}:")
                print(f"    DbMcode: {row[0]}")
                print(f"    DbDesca: {row[1][:50]}..." if row[1] and len(row[1]) > 50 else f"    DbDesca: {row[1]}")
                print(f"    DbMenuCode: {row[2]}")
                print(f"    BASEUOM: {row[3] if len(row) > 3 else 'N/A'}")
                print(f"    CONFACTOR: {row[4] if len(row) > 4 else 'N/A'}")
                print(f"    altunit: {row[5] if len(row) > 5 else 'N/A'}")
        
        cursor.close()
        conn.close()
        
        print("\n✓ OCRMappedData query test PASSED")
        return True
        
    except Exception as e:
        print(f"\n✗ OCRMappedData query test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("DIAGNOSTIC TEST - Checking API Implementation")
    print("="*60)
    
    all_passed = True
    
    # Run tests
    all_passed = test_database_query() and all_passed
    all_passed = test_fuzzy_matching() and all_passed
    all_passed = test_ocr_mapped_data() and all_passed
    
    # Summary
    print("\n" + "="*60)
    if all_passed:
        print("✓ ALL DIAGNOSTIC TESTS PASSED!")
        print("\nThe implementation is correct. If the API is not returning")
        print("the new fields, please RESTART THE API SERVER to clear the cache.")
    else:
        print("✗ SOME TESTS FAILED!")
        print("\nPlease review the errors above.")
    print("="*60)
