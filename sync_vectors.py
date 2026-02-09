"""
Vector Database Sync Script
============================

Standalone script to synchronize SQL Server data to Qdrant vector database.
Run this after initial setup or to refresh vectors.

Usage:
    python sync_vectors.py                           # Full sync (resumes from checkpoint)
    python sync_vectors.py --menu-only               # Sync menu items only
    python sync_vectors.py --mappings-only           # Sync OCR mappings only
    python sync_vectors.py --status                  # Show sync status
    python sync_vectors.py --fresh                   # Start fresh, ignore checkpoints
    python sync_vectors.py --company <id>            # Sync for specific company
    python sync_vectors.py --list-companies          # List all companies
    python sync_vectors.py --incremental             # Sync only changed data
    python sync_vectors.py --incremental --hours 24  # Sync data changed in last 24 hours
    python sync_vectors.py --checkpoint-status       # Show checkpoint status

Prerequisites:
    1. Qdrant running on localhost:6333
    2. GEMINI_API_KEY in appSetting.txt or environment
    3. DBConnection.txt configured for SQL Server
"""

import argparse
import os
import sys
import logging
import time
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_api_key_from_db():
    """Get Gemini API key from database TokenMaster table."""
    try:
        from db_connection import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        # Look for any active Gemini/Google token
        cursor.execute("""
            SELECT TOP 1 ApiKey FROM [docUpload].TokenMaster 
            WHERE Status = 'Active' AND Provider IN ('Gemini', 'Google', 'gemini', 'google')
            ORDER BY CreatedAt DESC
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.debug(f"Could not get API key from database: {e}")
    return None


def get_api_key():
    """Get Gemini API key from environment, appSetting.txt, or database."""
    # 1. Check environment variable
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    
    # 2. Check appSetting.txt
    try:
        with open('appSetting.txt', 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    key = line.split('=', 1)[1].strip()
                    if key:
                        return key
    except FileNotFoundError:
        pass
    
    # 3. Try to get from database TokenMaster
    key = get_api_key_from_db()
    if key:
        logger.info("Using Gemini API key from database TokenMaster")
        return key
    
    return None


def initialize_system(api_key: str):
    """Initialize the vector search system."""
    from vector_init import initialize_vector_search_system
    
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    
    logger.info(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port}")
    
    system = initialize_vector_search_system(
        gemini_api_key=api_key,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        auto_sync=False  # We'll sync manually
    )
    
    if not system.is_ready:
        raise RuntimeError("Failed to initialize vector system")
    
    return system


def show_status():
    """Display current sync status."""
    from vector_init import get_vector_system
    from qdrant_manager import get_qdrant_manager
    
    system = get_vector_system()
    status = system.get_status()
    
    print("\n" + "="*60)
    print("VECTOR SEARCH STATUS")
    print("="*60)
    
    print(f"\nSystem Ready: {status.get('ready', False)}")
    
    if status.get('error'):
        print(f"Error: {status['error']}")
    
    if 'qdrant' in status:
        qdrant = status['qdrant']
        print(f"\nQdrant Connected: {qdrant.get('connected', False)}")
        
        for col in qdrant.get('collections', []):
            print(f"  - {col['name']}: {col.get('points_count', 0)} vectors")
            print(f"    Status: {col.get('status', 'unknown')}")
    
    if 'embedding' in status:
        emb = status['embedding']
        print(f"\nEmbedding Model: {emb.get('model', 'N/A')}")
        print(f"Dimensions: {emb.get('dimensions', 'N/A')}")
        cache = emb.get('cache', {})
        print(f"Cache: {cache.get('size', 0)} items, {cache.get('hit_rate', '0%')} hit rate")
    
    if 'sync' in status:
        sync = status['sync']
        mi = sync.get('menu_items', {})
        print(f"\nMenu Items Synced: {mi.get('total', 0)}")
        print(f"Last Sync: {mi.get('last_sync', 'Never')}")
    
    print()


def sync_menu_items(progress=True, resume=True, company_id=None, incremental_hours=None):
    """Sync menu items to vector database with checkpoint support."""
    from vector_sync import get_vector_sync_service
    
    sync = get_vector_sync_service()
    
    # Set company context if specified
    if company_id:
        companies = sync.get_companies()
        company = next((c for c in companies if str(c['company_id']) == str(company_id)), None)
        if company:
            sync.set_company_context(company['company_id'], company['company_name'])
            print(f"\n  Company: {company['company_name']} (ID: {company['company_id']})")
        else:
            print(f"\n  ⚠ Company ID {company_id} not found, using default collection")
    
    def progress_callback(current, total):
        if progress:
            pct = (current / total * 100) if total > 0 else 0
            bar_len = 40
            filled = int(bar_len * current / total) if total > 0 else 0
            bar = '█' * filled + '░' * (bar_len - filled)
            print(f"\r  [{bar}] {current:,}/{total:,} ({pct:.1f}%)", end='', flush=True)
    
    print("\nSyncing menu items...")
    if resume:
        checkpoint_status = sync.get_checkpoint_status(company_id)
        if checkpoint_status.get('menu_items', {}).get('exists'):
            cp = checkpoint_status['menu_items']
            print(f"  📌 Found checkpoint at {cp['percentage']:.1f}% - will resume")
    else:
        print("  🔄 Starting fresh sync (ignoring checkpoints)")
    
    print("  This may take several minutes for large datasets.\n")
    
    # Calculate incremental timestamp if specified
    incremental_since = None
    if incremental_hours:
        incremental_since = datetime.utcnow() - timedelta(hours=incremental_hours)
        print(f"  📊 Incremental mode: syncing changes from last {incremental_hours} hours\n")
    
    result = sync.sync_menu_items(
        batch_size=500,
        progress_callback=progress_callback,
        resume_from_checkpoint=resume,
        incremental_since=incremental_since
    )
    
    print("\n")
    print(f"  ✓ Synced: {result.get('synced', 0):,} items")
    print(f"  ✓ Duration: {result.get('duration_seconds', 0):.1f}s")
    print(f"  ✓ Rate: {result.get('records_per_second', 0):.0f} records/sec")
    
    if result.get('resumed_from_checkpoint'):
        print(f"  ✓ Resumed from checkpoint")
    
    if result.get('errors', 0) > 0:
        print(f"  ⚠ Errors: {result['errors']}")
    
    return result


def sync_ocr_mappings(company_id=None):
    """Sync OCR mappings to vector database."""
    from vector_sync import get_vector_sync_service
    
    sync = get_vector_sync_service()
    
    # Set company context if specified
    if company_id:
        companies = sync.get_companies()
        company = next((c for c in companies if str(c['company_id']) == str(company_id)), None)
        if company:
            sync.set_company_context(company['company_id'], company['company_name'])
    
    print("\nSyncing OCR mappings...")
    
    result = sync.sync_ocr_mappings()
    
    print(f"  ✓ Synced: {result.get('synced', 0)} mappings")
    print(f"  ✓ Duration: {result.get('duration_seconds', 0):.1f}s")
    
    return result


def list_companies():
    """List all companies available for sync."""
    from vector_sync import get_vector_sync_service
    
    sync = get_vector_sync_service()
    companies = sync.get_companies()
    
    print("\n" + "="*60)
    print("AVAILABLE COMPANIES")
    print("="*60)
    
    if not companies:
        print("\n  No companies found in database.")
        return
    
    print(f"\n  Found {len(companies)} companies:\n")
    print(f"  {'ID':<10} {'Name':<30} {'Collection Prefix':<20}")
    print(f"  {'-'*10} {'-'*30} {'-'*20}")
    
    for c in companies:
        print(f"  {str(c['company_id']):<10} {c['company_name'][:30]:<30} {c['collection_prefix']:<20}")
    
    print()


def show_checkpoint_status(company_id=None):
    """Show current checkpoint status."""
    from vector_sync import get_vector_sync_service
    
    sync = get_vector_sync_service()
    status = sync.get_checkpoint_status(company_id)
    
    print("\n" + "="*60)
    print("CHECKPOINT STATUS")
    if company_id:
        print(f"Company ID: {company_id}")
    print("="*60)
    
    for sync_type, info in status.items():
        print(f"\n{sync_type}:")
        if info.get('exists'):
            print(f"  ✓ Checkpoint found")
            print(f"    Progress: {info['percentage']:.1f}%")
            print(f"    Offset: {info['offset']:,} / {info['total']:,}")
            print(f"    Saved at: {info['timestamp']}")
            print(f"    Can resume: {info['can_resume']}")
        else:
            print(f"  ✗ No checkpoint (will start fresh)")
    
    print()


def create_company_collections(company_id, company_name=None):
    """Create Qdrant collections for a specific company."""
    from vector_sync import get_vector_sync_service
    
    sync = get_vector_sync_service()
    
    print(f"\nCreating collections for company: {company_id}")
    
    success = sync.create_company_collections(company_id, company_name)
    
    if success:
        print(f"  ✓ Collections created successfully")
    else:
        print(f"  ✗ Failed to create collections")
    
    return success


def full_sync(company_id=None, resume=True):
    """Perform full synchronization."""
    from vector_sync import get_vector_sync_service
    
    sync = get_vector_sync_service()
    
    print("\n" + "="*60)
    print("FULL VECTOR SYNC")
    if company_id:
        companies = sync.get_companies()
        company = next((c for c in companies if str(c['company_id']) == str(company_id)), None)
        if company:
            print(f"Company: {company['company_name']} (ID: {company['company_id']})")
    print("="*60)
    
    start = time.time()
    
    # Sync menu items
    sync_menu_items(resume=resume, company_id=company_id)
    
    # Sync OCR mappings
    sync_ocr_mappings(company_id=company_id)
    
    elapsed = time.time() - start
    
    print("\n" + "-"*60)
    print(f"Full sync completed in {elapsed:.1f} seconds")
    print("-"*60)


def main():
    parser = argparse.ArgumentParser(
        description='Synchronize SQL Server data to Qdrant vector database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_vectors.py                           # Full sync with resume
  python sync_vectors.py --fresh                   # Full sync, ignore checkpoints
  python sync_vectors.py --company 1               # Sync for company ID 1
  python sync_vectors.py --list-companies          # List all companies
  python sync_vectors.py --incremental --hours 24  # Sync changes from last 24 hours
  python sync_vectors.py --checkpoint-status       # Check checkpoint status
        """
    )
    parser.add_argument(
        '--menu-only', 
        action='store_true',
        help='Sync only menu items'
    )
    parser.add_argument(
        '--mappings-only',
        action='store_true', 
        help='Sync only OCR mappings'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current sync status'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    # New arguments for checkpoint support
    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Start fresh sync, ignore existing checkpoints'
    )
    parser.add_argument(
        '--checkpoint-status',
        action='store_true',
        help='Show current checkpoint status'
    )
    # Company-wise sync arguments
    parser.add_argument(
        '--company',
        type=str,
        metavar='ID',
        help='Sync for specific company ID'
    )
    parser.add_argument(
        '--list-companies',
        action='store_true',
        help='List all available companies'
    )
    parser.add_argument(
        '--create-company-collections',
        type=str,
        metavar='ID',
        help='Create Qdrant collections for specific company'
    )
    # Incremental sync arguments
    parser.add_argument(
        '--incremental',
        action='store_true',
        help='Sync only changed/new data'
    )
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='Hours to look back for incremental sync (default: 24)'
    )
    
    args = parser.parse_args()
    
    print("\n" + "#"*60)
    print("# VECTOR DATABASE SYNC")
    print("#"*60)
    
    # Handle list-companies first (no API key needed)
    if args.list_companies:
        try:
            # Initialize minimal system for database access
            list_companies()
            return 0
        except Exception as e:
            logger.error(f"Failed to list companies: {e}")
            return 1
    
    # Get API key
    api_key = get_api_key()
    if not api_key:
        print("\n✗ ERROR: GEMINI_API_KEY not found!")
        print("  Set it in appSetting.txt or as environment variable")
        sys.exit(1)
    
    print(f"\n✓ API key found: {api_key[:8]}...{api_key[-4:]}")
    
    try:
        # Initialize system
        system = initialize_system(api_key)
        print("✓ Vector system initialized")
        
        # Execute requested action
        if args.checkpoint_status:
            show_checkpoint_status(args.company)
        elif args.create_company_collections:
            create_company_collections(args.create_company_collections)
        elif args.status:
            show_status()
        elif args.menu_only:
            if args.incremental:
                sync_menu_items(
                    progress=not args.no_progress,
                    resume=not args.fresh,
                    company_id=args.company,
                    incremental_hours=args.hours
                )
            else:
                sync_menu_items(
                    progress=not args.no_progress,
                    resume=not args.fresh,
                    company_id=args.company
                )
            show_status()
        elif args.mappings_only:
            sync_ocr_mappings(company_id=args.company)
            show_status()
        elif args.incremental:
            sync_menu_items(
                progress=not args.no_progress,
                resume=not args.fresh,
                company_id=args.company,
                incremental_hours=args.hours
            )
            show_status()
        else:
            full_sync(company_id=args.company, resume=not args.fresh)
            show_status()
        
        print("\n✓ Done!\n")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠ Sync interrupted. Checkpoint saved - run again to resume.")
        return 130
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
