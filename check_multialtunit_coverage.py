"""
Check which products have MULTIALTUNIT data
"""
from db_connection import get_connection

def check_multialtunit_data():
    print("\n" + "="*60)
    print("CHECKING MULTIALTUNIT DATA FOR YOUR PRODUCTS")
    print("="*60)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # The products from your Postman response
    test_mcodes = [
        'MHOO7477',  # ARKSH FOOD DAMI CORN HONEY BISCUIT
        'M44493P',   # KINGFISHER STRONG BEER 650ML
        'MHOO6152'   # NESCAFE GOLD RICH AROMA COFFEE
    ]
    
    for mcode in test_mcodes:
        print(f"\n{'='*60}")
        print(f"Checking mcode: {mcode}")
        print('='*60)
        
        # Get menuitem details
        cursor.execute("""
            SELECT desca, mcode, menucode
            FROM menuitem
            WHERE mcode = ?
        """, (mcode,))
        
        item = cursor.fetchone()
        if item:
            print(f"  Product: {item[0][:60]}...")
            print(f"  MCode: {item[1]}")
            print(f"  MenuCode: {item[2]}")
        else:
            print(f"  ✗ Product not found in menuitem table!")
            continue
        
        # Check MULTIALTUNIT
        cursor.execute("""
            SELECT BASEUOM, CONFACTOR, altunit
            FROM MULTIALTUNIT
            WHERE mcode = ?
        """, (mcode,))
        
        multi = cursor.fetchone()
        if multi:
            print(f"\n  ✓ MULTIALTUNIT Data Found:")
            print(f"    Base Unit: {multi[0]}")
            print(f"    ConFactor: {multi[1]}")
            print(f"    Alt Unit: {multi[2]}")
        else:
            print(f"\n  ✗ NO MULTIALTUNIT DATA for this product!")
            print(f"    This product needs to be added to MULTIALTUNIT table")
    
    # Check how many products have MULTIALTUNIT data
    print(f"\n{'='*60}")
    print("OVERALL STATISTICS")
    print('='*60)
    
    cursor.execute("SELECT COUNT(*) FROM menuitem WHERE type = 'A' and isactive = 1")
    total_active = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(DISTINCT m.mcode)
        FROM menuitem m
        INNER JOIN MULTIALTUNIT a ON m.mcode = a.mcode
        WHERE m.type = 'A' and m.isactive = 1
    """)
    with_data = cursor.fetchone()[0]
    
    print(f"\n  Total active menu items: {total_active}")
    print(f"  Items with MULTIALTUNIT data: {with_data}")
    print(f"  Items WITHOUT MULTIALTUNIT data: {total_active - with_data}")
    print(f"  Coverage: {(with_data/total_active*100):.2f}%")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_multialtunit_data()
