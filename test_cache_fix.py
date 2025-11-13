"""
Quick test to verify the menu_cache fix works with the actual database query.
"""
import sys
from db_connection import get_connection
from menu_cache import get_cached_menu_items, clear_cache

def test_database_query():
    """Test that the actual database query works with the cache."""
    print("Testing database query with cache...")
    
    # Clear cache first
    clear_cache()
    print("✓ Cache cleared")
    
    def fetch_from_db():
        """Fetch menu items from database."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT desca, mcode, menucode FROM menuitem WHERE type = 'A'")
        items = cursor.fetchall()
        cursor.close()
        conn.close()
        print(f"✓ Fetched {len(items)} items from database")
        if items:
            print(f"  First item type: {type(items[0])}, length: {len(items[0])}")
            print(f"  First item: {items[0][:3] if len(items[0]) >= 3 else items[0]}")
        return items
    
    try:
        # First call - should fetch from DB
        print("\n--- Test 1: Cache miss (fetch from DB) ---")
        menu_items = get_cached_menu_items(fetch_from_db)
        print(f"✓ Successfully loaded {len(menu_items)} items")
        print(f"  Cached item format: {menu_items[0] if menu_items else 'No items'}")
        
        # Second call - should use cache
        print("\n--- Test 2: Cache hit ---")
        menu_items_cached = get_cached_menu_items(fetch_from_db)
        print(f"✓ Successfully retrieved {len(menu_items_cached)} items from cache")
        
        # Verify format
        if menu_items_cached:
            first_item = menu_items_cached[0]
            if len(first_item) == 3:
                print(f"✓ Items are in correct 3-tuple format: (desca, mcode, menucode)")
                print(f"  Sample: desca='{first_item[0][:30]}...', mcode='{first_item[1]}', menucode='{first_item[2]}'")
            else:
                print(f"✗ ERROR: Items have wrong format: {len(first_item)} values")
                return False
        
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_database_query()
    sys.exit(0 if success else 1)
