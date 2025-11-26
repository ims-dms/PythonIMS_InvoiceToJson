"""
Test to find the KINGFISHER STRONG product mentioned by user
"""

import logging
from db_connection import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_kingfisher_strong():
    """Search for KINGFISHER STRONG products"""
    print("\n" + "="*80)
    print("Searching for KINGFISHER STRONG products")
    print("="*80)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Search with different criteria
    print("\n1. Search in menuitem WHERE desca LIKE '%KINGFISHER%STRONG%' (any type):")
    cursor.execute("""
        SELECT TOP 20 mcode, menucode, desca, type
        FROM menuitem 
        WHERE desca LIKE '%KINGFISHER%STRONG%'
        ORDER BY desca
    """)
    rows = cursor.fetchall()
    print(f"   Found {len(rows)} results:")
    for row in rows:
        print(f"     MCODE: {row[0]}, MENUCODE: {row[1]}, TYPE: {row[3]}")
        print(f"       DESCA: {row[2]}")
    
    print("\n2. Search for specific MCODE 'MHOO2916':")
    cursor.execute("""
        SELECT mcode, menucode, desca, type
        FROM menuitem 
        WHERE mcode = 'MHOO2916'
    """)
    rows = cursor.fetchall()
    print(f"   Found {len(rows)} results:")
    for row in rows:
        print(f"     MCODE: {row[0]}, MENUCODE: {row[1]}, TYPE: {row[3]}")
        print(f"       DESCA: {row[2]}")
    
    print("\n3. Search for MENUCODE '11.6362':")
    cursor.execute("""
        SELECT mcode, menucode, desca, type
        FROM menuitem 
        WHERE menucode = '11.6362'
    """)
    rows = cursor.fetchall()
    print(f"   Found {len(rows)} results:")
    for row in rows:
        print(f"     MCODE: {row[0]}, MENUCODE: {row[1]}, TYPE: {row[3]}")
        print(f"       DESCA: {row[2]}")
    
    print("\n4. Search WHERE desca LIKE '%330%' AND desca LIKE '%KINGFISHER%' (any type):")
    cursor.execute("""
        SELECT TOP 10 mcode, menucode, desca, type
        FROM menuitem 
        WHERE desca LIKE '%330%' AND desca LIKE '%KINGFISHER%'
        ORDER BY desca
    """)
    rows = cursor.fetchall()
    print(f"   Found {len(rows)} results:")
    for row in rows:
        print(f"     MCODE: {row[0]}, MENUCODE: {row[1]}, TYPE: {row[3]}")
        print(f"       DESCA: {row[2]}")
    
    print("\n5. Count all menuitem records:")
    cursor.execute("SELECT COUNT(*) FROM menuitem")
    count = cursor.fetchone()[0]
    print(f"   Total menuitem records: {count}")
    
    print("\n6. Count menuitem records WHERE type = 'A':")
    cursor.execute("SELECT COUNT(*) FROM menuitem WHERE type = 'A' and isactive = 1")
    count = cursor.fetchone()[0]
    print(f"   Total type='A' records: {count}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    find_kingfisher_strong()
