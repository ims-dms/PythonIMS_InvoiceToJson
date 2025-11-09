"""
Advanced Caching Layer for Menu Items
======================================

Purpose: Prevent repeated database queries for 700k menu items
Strategy: In-memory cache with TTL, singleton pattern for API integration
Performance: Sub-millisecond access after initial load

This cache is especially critical when processing multiple invoices
in quick succession, as it eliminates the database overhead.
"""

import time
import logging
from typing import List, Tuple, Optional
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MenuItemCache:
    """
    Thread-safe singleton cache for menu items with automatic expiration.
    
    Features:
    - Singleton pattern: Only one instance across entire application
    - Thread-safe: Can be used in multi-threaded FastAPI environment
    - Automatic expiration: Cache refreshes after TTL expires
    - Memory efficient: Stores only necessary data structures
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MenuItemCache, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, ttl: int = 3600):
        """
        Initialize cache with time-to-live.
        
        Args:
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
        """
        if self._initialized:
            return
        
        self._cache_data = None
        self._cache_timestamp = 0
        self._ttl = ttl
        self._load_count = 0
        self._initialized = True
        logger.info(f"MenuItemCache initialized with {ttl}s TTL")
    
    def set_ttl(self, ttl: int):
        """Update cache TTL."""
        self._ttl = ttl
        logger.info(f"Cache TTL updated to {ttl}s")
    
    def load(self, menu_items: List[Tuple[str, str]], force: bool = False) -> None:
        """
        Load menu items into cache.
        
        Args:
            menu_items: List of (desca, mcode) tuples from database
            force: Force reload even if cache is valid
        """
        with self._lock:
            if not force and self.is_valid():
                logger.info("Cache is still valid, skipping reload")
                return
            
            start_time = time.time()
            
            # Filter out None/empty DESCA entries
            valid_items = [(d, m) for d, m in menu_items if d and d.strip()]
            
            self._cache_data = {
                'items': valid_items,
                'count': len(valid_items)
            }
            
            self._cache_timestamp = time.time()
            self._load_count += 1
            
            elapsed = time.time() - start_time
            logger.info(
                f"Cache loaded with {self._cache_data['count']} items in {elapsed:.2f}s "
                f"(load #{self._load_count})"
            )
    
    def get(self) -> Optional[List[Tuple[str, str]]]:
        """
        Get cached menu items.
        
        Returns:
            List of (desca, mcode) tuples, or None if cache is invalid
        """
        if not self.is_valid():
            logger.warning("Cache is invalid or expired")
            return None
        
        return self._cache_data['items']
    
    def is_valid(self) -> bool:
        """Check if cache is valid and not expired."""
        if self._cache_data is None:
            return False
        
        age = time.time() - self._cache_timestamp
        return age < self._ttl
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        if self._cache_data is None:
            return {
                'status': 'empty',
                'item_count': 0,
                'age_seconds': 0,
                'load_count': self._load_count,
                'ttl': self._ttl
            }
        
        age = time.time() - self._cache_timestamp
        return {
            'status': 'valid' if self.is_valid() else 'expired',
            'item_count': self._cache_data['count'],
            'age_seconds': round(age, 2),
            'load_count': self._load_count,
            'ttl': self._ttl,
            'expires_in': max(0, round(self._ttl - age, 2))
        }
    
    def invalidate(self):
        """Manually invalidate cache (force reload on next access)."""
        with self._lock:
            self._cache_timestamp = 0
            logger.info("Cache manually invalidated")
    
    def clear(self):
        """Clear all cache data."""
        with self._lock:
            self._cache_data = None
            self._cache_timestamp = 0
            logger.info("Cache cleared")


# Global singleton instance
_global_cache = MenuItemCache()


def get_cached_menu_items(
    fetch_function,
    force_refresh: bool = False
) -> List[Tuple[str, str]]:
    """
    Get menu items from cache or fetch from database if needed.
    
    This is the primary function to use in your API.
    
    Args:
        fetch_function: Function that fetches menu items from DB
                       Should return List[Tuple[str, str]]
        force_refresh: Force database query even if cache is valid
    
    Returns:
        List of (desca, mcode) tuples
    
    Example:
        def fetch_from_db():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT desca, mcode FROM menuitem")
            items = cursor.fetchall()
            cursor.close()
            conn.close()
            return items
        
        menu_items = get_cached_menu_items(fetch_from_db)
    """
    
    # Check if cache is valid
    if not force_refresh and _global_cache.is_valid():
        cached_items = _global_cache.get()
        if cached_items is not None:
            logger.info(f"Using cached menu items ({len(cached_items)} items)")
            return cached_items
    
    # Fetch from database
    logger.info("Cache miss or expired, fetching from database...")
    start_time = time.time()
    
    items = fetch_function()
    
    elapsed = time.time() - start_time
    logger.info(f"Fetched {len(items)} items from database in {elapsed:.2f}s")
    
    # Update cache
    _global_cache.load(items, force=True)
    
    return items


def get_cache_stats() -> dict:
    """Get current cache statistics."""
    return _global_cache.get_stats()


def invalidate_cache():
    """Invalidate cache to force refresh on next request."""
    _global_cache.invalidate()


def clear_cache():
    """Clear all cached data."""
    _global_cache.clear()


# Example usage
if __name__ == "__main__":
    print("=" * 80)
    print("Menu Item Cache - Test Suite")
    print("=" * 80)
    
    # Simulate database fetch
    def mock_db_fetch():
        """Simulate fetching from database."""
        import time
        time.sleep(0.5)  # Simulate network latency
        return [
            ("LACTOGEN PRO 1 BIB 24x400g", "ITM001"),
            ("LACTOGEN PRO 2 BIB 24x400g", "ITM002"),
            ("NESCAFE CLASSIC 100g", "ITM003")
        ]
    
    # First call - should fetch from DB
    print("\n--- First call (cache miss) ---")
    start = time.time()
    items1 = get_cached_menu_items(mock_db_fetch)
    print(f"Retrieved {len(items1)} items in {time.time() - start:.3f}s")
    print(f"Cache stats: {get_cache_stats()}")
    
    # Second call - should use cache
    print("\n--- Second call (cache hit) ---")
    start = time.time()
    items2 = get_cached_menu_items(mock_db_fetch)
    print(f"Retrieved {len(items2)} items in {time.time() - start:.3f}s")
    print(f"Cache stats: {get_cache_stats()}")
    
    # Force refresh
    print("\n--- Third call (forced refresh) ---")
    start = time.time()
    items3 = get_cached_menu_items(mock_db_fetch, force_refresh=True)
    print(f"Retrieved {len(items3)} items in {time.time() - start:.3f}s")
    print(f"Cache stats: {get_cache_stats()}")
    
    print("\n" + "=" * 80)
    print("Cache test completed successfully")
    print("=" * 80)
