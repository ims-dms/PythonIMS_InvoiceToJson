"""
Test script to verify Kingfisher matching and OCRMappedData lookup fixes
"""

import logging
from db_connection import get_connection
from fuzzy_matcher import match_ocr_products

# Enable logging to see what's happening
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_ocr_mapped_data_lookup():
    """Test that OCRMappedData lookup works correctly"""
    print("\n" + "="*80)
    print("TEST 1: OCRMappedData Lookup")
    print("="*80)
    
    # Sample products from your JSON
    ocr_products = [
        {
            "sku": "Kingfisher Strong -Bottle 330ml",
            "sku_code": "",
            "quantity": 20,
            "rate": 1235.48,
            "unit": "Case"
        },
        {
            "sku": "Kingfisher Strong -Can 500ml",
            "sku_code": "",
            "quantity": 20,
            "rate": 1101.59,
            "unit": "Case"
        }
    ]
    
    # Get database connection
    conn = get_connection()
    
    # Get menu items
    cursor = conn.cursor()
    cursor.execute("SELECT desca, mcode, menucode FROM menuitem WHERE type = 'A'")
    menu_items = cursor.fetchall()
    cursor.close()
    
    logger.info(f"Loaded {len(menu_items)} menu items from database")
    
    # Test with supplier name
    supplier_name = "YETI BREWERY LIMITED"
    
    # Run matching
    results = match_ocr_products(
        ocr_products=ocr_products,
        menu_items=menu_items,
        top_k=3,
        score_cutoff=60.0,
        connection=conn,
        supplier_name=supplier_name
    )
    
    conn.close()
    
    # Print results
    for product in results:
        print(f"\nProduct: {product['sku']}")
        print(f"  Mapped Nature: {product.get('mapped_nature', 'N/A')}")
        print(f"  Match Confidence: {product.get('match_confidence', 'N/A')}")
        print(f"  Best Match: {product.get('best_match')}")
        print(f"  Fuzzy Matches Count: {len(product.get('fuzzy_matches', []))}")
        if product.get('fuzzy_matches'):
            for match in product['fuzzy_matches'][:3]:
                print(f"    - {match['desca']} (Score: {match['score']}, MCODE: {match['mcode']})")

def test_fuzzy_matching():
    """Test that fuzzy matching works for Kingfisher products"""
    print("\n" + "="*80)
    print("TEST 2: Fuzzy Matching (without OCRMappedData)")
    print("="*80)
    
    # Sample products from your JSON
    ocr_products = [
        {
            "sku": "Kingfisher Strong -Bottle 330ml",
            "sku_code": "",
            "quantity": 20,
        },
        {
            "sku": "Kingfisher Strong -Bottle 650ml",
            "sku_code": "",
            "quantity": 20,
        }
    ]
    
    # Get database connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT desca, mcode, menucode FROM menuitem WHERE type = 'A'")
    menu_items = cursor.fetchall()
    cursor.close()
    conn.close()
    
    logger.info(f"Loaded {len(menu_items)} menu items from database")
    
    # Run matching WITHOUT database connection (to test fuzzy matching only)
    results = match_ocr_products(
        ocr_products=ocr_products,
        menu_items=menu_items,
        top_k=5,
        score_cutoff=50.0,  # Lower threshold to see more matches
        connection=None,  # No DB connection to force fuzzy matching
        supplier_name=""
    )
    
    # Print results
    for product in results:
        print(f"\nProduct: {product['sku']}")
        print(f"  Mapped Nature: {product.get('mapped_nature', 'N/A')}")
        print(f"  Match Confidence: {product.get('match_confidence', 'N/A')}")
        if product.get('best_match'):
            bm = product['best_match']
            print(f"  Best Match: {bm['desca']} (Score: {bm['score']}, MCODE: {bm['mcode']})")
        print(f"  All Fuzzy Matches:")
        if product.get('fuzzy_matches'):
            for match in product['fuzzy_matches']:
                print(f"    {match['rank']}. {match['desca'][:60]} (Score: {match['score']}, MCODE: {match['mcode']})")
        else:
            print("    No matches found")

def test_database_direct_query():
    """Test direct database query to see what's in menuitem"""
    print("\n" + "="*80)
    print("TEST 3: Direct Database Query for Kingfisher")
    print("="*80)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Search for Kingfisher products
    cursor.execute("""
        SELECT TOP 10 mcode, menucode, desca 
        FROM menuitem 
        WHERE desca LIKE '%KINGFISHER%' AND type = 'A'
        ORDER BY desca
    """)
    
    rows = cursor.fetchall()
    
    print(f"\nFound {len(rows)} Kingfisher products in database:")
    for row in rows:
        print(f"  MCODE: {row[0]}, MENUCODE: {row[1]}")
        print(f"    DESCA: {row[2]}")
    
    cursor.close()
    conn.close()

def test_ocr_mapped_data_contents():
    """Check what's actually in the OCRMappedData table"""
    print("\n" + "="*80)
    print("TEST 4: OCRMappedData Table Contents")
    print("="*80)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT InvoiceProductCode, InvoiceProductName, DbMcode, DbDesca, InvoiceSupplierName, DbSupplierName, DbMenuCode
            FROM [docUpload].[OCRMappedData]
            WHERE InvoiceProductName LIKE '%Kingfisher%'
        """)
        
        rows = cursor.fetchall()
        
        print(f"\nFound {len(rows)} Kingfisher entries in OCRMappedData:")
        for row in rows:
            print(f"  InvoiceProductCode: {row[0]}")
            print(f"  InvoiceProductName: {row[1]}")
            print(f"  DbMcode: {row[2]}")
            print(f"  DbDesca: {row[3]}")
            print(f"  InvoiceSupplierName: {row[4]}")
            print(f"  DbSupplierName: {row[5]}")
            print(f"  DbMenuCode: {row[6]}")
            print()
    except Exception as e:
        print(f"Error querying OCRMappedData: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    try:
        # Run all tests
        test_database_direct_query()
        test_ocr_mapped_data_contents()
        test_fuzzy_matching()
        test_ocr_mapped_data_lookup()
        
        print("\n" + "="*80)
        print("ALL TESTS COMPLETED")
        print("="*80)
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print(f"\nERROR: {e}")
