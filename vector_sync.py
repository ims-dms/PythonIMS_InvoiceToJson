"""
Vector Sync Service
====================

Synchronizes SQL Server data (MenuItem, OCRMappedData) with Qdrant vector database.
Handles initial bulk load and incremental updates.

Features:
- Full sync of all menu items
- Incremental sync based on timestamps
- OCR mappings sync for learning from previous matches
- Change detection and auto-sync triggers
"""

import logging
import time
import hashlib
import os
import re
from typing import List, Dict, Optional, Tuple, Callable
from datetime import datetime
from threading import Thread, Lock
import json
from pathlib import Path

from db_connection import get_connection
from qdrant_manager import get_qdrant_manager, QdrantManager
from embedding_service import get_embedding_service, EmbeddingService
from vector_config import get_vector_config

logger = logging.getLogger(__name__)


class VectorSyncService:
    """
    Synchronizes SQL Server data with Qdrant vector database.
    
    Handles:
    - MenuItem table → menu_items collection
    - OCRMappedData table → ocr_mappings collection
    - Incremental updates on data changes
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._qdrant: Optional[QdrantManager] = None
        self._embedding: Optional[EmbeddingService] = None
        self._config = None
        self._sync_lock = Lock()
        self._last_sync_time: Optional[datetime] = None
        self._sync_stats = {
            "menu_items": {"total": 0, "last_sync": None},
            "ocr_mappings": {"total": 0, "last_sync": None}
        }
        # Checkpoint directory for resumable syncs
        self._checkpoint_dir = Path(os.path.dirname(__file__)) / ".sync_checkpoints"
        self._checkpoint_dir.mkdir(exist_ok=True)
        # Current company context
        self._current_company_id: Optional[str] = None
        self._current_company_name: Optional[str] = None
        self._initialized = True
        
        logger.info("VectorSyncService initialized")
    
    def configure(
        self,
        qdrant_manager: QdrantManager,
        embedding_service: EmbeddingService
    ):
        """
        Configure sync service with required dependencies.
        
        Args:
            qdrant_manager: Initialized Qdrant manager
            embedding_service: Configured embedding service
        """
        self._qdrant = qdrant_manager
        self._embedding = embedding_service
        self._config = get_vector_config()
        
        logger.info("VectorSyncService configured")
    
    def _ensure_configured(self):
        """Ensure service is properly configured."""
        if not self._qdrant or not self._embedding:
            raise RuntimeError(
                "VectorSyncService not configured. Call configure() first."
            )
    
    def _generate_point_id(self, collection: str, unique_key: str) -> str:
        """
        Generate deterministic point ID from unique key.
        Uses hash to ensure consistent IDs for the same record.
        """
        key = f"{collection}:{unique_key}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def _fetch_menu_items(
        self,
        connection_params: Dict = None,
        limit: int = None,
        offset: int = 0,
        since_timestamp: datetime = None,
        mcode_list: List[str] = None
    ) -> List[Dict]:
        """
        Fetch menu items from SQL Server with supplier information.
        
        Args:
            connection_params: Optional connection override
            limit: Max records to fetch
            offset: Starting offset for pagination
            since_timestamp: Only fetch records updated after this time (for incremental sync)
            mcode_list: Specific mcodes to fetch (for targeted updates)
            
        Returns:
            List of menu item dictionaries with supplier info
        """
        conn = get_connection(connection_params)
        cursor = conn.cursor()
        
        # Build query with supplier information (JOIN with rmd_aclist)
        query = """
            SELECT 
                m.mcode,
                m.menucode,
                m.desca,
                m.type,
                m.isactive,
                m.VAT as vat,
                a.BASEUOM as baseunit,
                a.CONFACTOR as confactor,
                a.altunit,
                m.SUPCODE as supplier_code,
                ISNULL(ra.acname, '') as supplier_name
            FROM menuitem m
            LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode
            LEFT JOIN rmd_aclist ra ON m.SUPCODE = ra.acid
            WHERE m.type = 'A' AND m.isactive = 1
        """
        
        params = []
        
        # Add incremental sync filter
        if since_timestamp:
            query += " AND m.ModifiedDate > ?"
            params.append(since_timestamp)
        
        # Add specific mcode filter
        if mcode_list:
            placeholders = ','.join(['?' for _ in mcode_list])
            query += f" AND m.mcode IN ({placeholders})"
            params.extend(mcode_list)
        
        if limit:
            query += f" ORDER BY m.mcode OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        columns = [desc[0] for desc in cursor.description]
        
        items = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            # Handle Decimal types
            if item.get('confactor'):
                item['confactor'] = float(item['confactor'])
            if item.get('vat') is not None:
                item['vat'] = int(item['vat'])
            items.append(item)
        
        cursor.close()
        conn.close()
        
        return items
    
    def _fetch_ocr_mappings(
        self,
        connection_params: Dict = None,
        limit: int = None
    ) -> List[Dict]:
        """
        Fetch OCR mappings from SQL Server.
        
        Args:
            connection_params: Optional connection override
            limit: Max records to fetch
            
        Returns:
            List of OCR mapping dictionaries
        """
        conn = get_connection(connection_params)
        cursor = conn.cursor()
        
        query = """
            SELECT 
                o.InvoiceProductCode,
                o.InvoiceProductName,
                o.Dbmcode,
                o.DbDesca,
                o.DbMenuCode,
                o.InvoiceSupplierName,
                o.DbSupplierName
            FROM [docUpload].[OCRMappedData] o
        """
        
        if limit:
            query = f"SELECT TOP {limit} * FROM ({query}) sub"
        
        try:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            
            items = []
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                items.append(item)
            
            cursor.close()
            conn.close()
            return items
            
        except Exception as e:
            logger.warning(f"OCRMappedData table might not exist: {e}")
            cursor.close()
            conn.close()
            return []
    
    def _count_menu_items(self, connection_params: Dict = None, since_timestamp: datetime = None) -> int:
        """Count total menu items in database."""
        conn = get_connection(connection_params)
        cursor = conn.cursor()
        
        query = """
            SELECT COUNT(*) FROM menuitem 
            WHERE type = 'A' AND isactive = 1
        """
        
        if since_timestamp:
            query += " AND ModifiedDate > ?"
            cursor.execute(query, (since_timestamp,))
        else:
            cursor.execute(query)
        
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        return count
    
    # ==================== CHECKPOINT MANAGEMENT ====================
    
    def _get_checkpoint_file(self, company_id: str = None, sync_type: str = "menu_items") -> Path:
        """Get checkpoint file path for a specific sync operation."""
        company_suffix = f"_{company_id}" if company_id else ""
        return self._checkpoint_dir / f"checkpoint_{sync_type}{company_suffix}.json"
    
    def _save_checkpoint(
        self,
        sync_type: str,
        offset: int,
        total: int,
        synced: int,
        errors: int,
        company_id: str = None,
        extra_data: Dict = None
    ):
        """
        Save checkpoint for resumable sync.
        
        Args:
            sync_type: Type of sync (menu_items, ocr_mappings)
            offset: Current offset in the dataset
            total: Total records to sync
            synced: Successfully synced records
            errors: Error count
            company_id: Company identifier
            extra_data: Additional data to save
        """
        checkpoint = {
            "sync_type": sync_type,
            "offset": offset,
            "total": total,
            "synced": synced,
            "errors": errors,
            "company_id": company_id,
            "timestamp": datetime.utcnow().isoformat(),
            "percentage": round((offset / total * 100) if total > 0 else 0, 2),
            "extra_data": extra_data or {}
        }
        
        checkpoint_file = self._get_checkpoint_file(company_id, sync_type)
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, indent=2)
        
        logger.debug(f"Checkpoint saved: {sync_type} @ {checkpoint['percentage']:.1f}%")
    
    def _load_checkpoint(self, company_id: str = None, sync_type: str = "menu_items") -> Optional[Dict]:
        """
        Load checkpoint for resuming sync.
        
        Returns:
            Checkpoint data or None if no checkpoint exists
        """
        checkpoint_file = self._get_checkpoint_file(company_id, sync_type)
        
        if not checkpoint_file.exists():
            return None
        
        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint = json.load(f)
            
            # Check if checkpoint is recent (within 24 hours)
            checkpoint_time = datetime.fromisoformat(checkpoint['timestamp'])
            age_hours = (datetime.utcnow() - checkpoint_time).total_seconds() / 3600
            
            if age_hours > 24:
                logger.info(f"Checkpoint is {age_hours:.1f} hours old, starting fresh")
                self._clear_checkpoint(company_id, sync_type)
                return None
            
            logger.info(
                f"Found checkpoint: {sync_type} @ {checkpoint['percentage']:.1f}% "
                f"(offset={checkpoint['offset']}, synced={checkpoint['synced']})"
            )
            return checkpoint
            
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None
    
    def _clear_checkpoint(self, company_id: str = None, sync_type: str = "menu_items"):
        """Clear checkpoint after successful completion."""
        checkpoint_file = self._get_checkpoint_file(company_id, sync_type)
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.debug(f"Checkpoint cleared: {sync_type}")
    
    def get_checkpoint_status(self, company_id: str = None) -> Dict:
        """
        Get status of any existing checkpoints.
        
        Returns:
            Dictionary with checkpoint status for each sync type
        """
        status = {}
        for sync_type in ["menu_items", "ocr_mappings"]:
            checkpoint = self._load_checkpoint(company_id, sync_type)
            if checkpoint:
                status[sync_type] = {
                    "exists": True,
                    "offset": checkpoint['offset'],
                    "total": checkpoint['total'],
                    "percentage": checkpoint['percentage'],
                    "timestamp": checkpoint['timestamp'],
                    "can_resume": True
                }
            else:
                status[sync_type] = {"exists": False, "can_resume": False}
        return status
    
    # ==================== COMPANY MANAGEMENT ====================
    
    def get_companies(self, connection_params: Dict = None) -> List[Dict]:
        """
        Get list of all companies from database.
        
        Returns:
            List of company dictionaries with id, name, and collection_prefix
        """
        conn = get_connection(connection_params)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT companyid, NAME, 
                       CAST(companyid AS VARCHAR) + NAME AS unique_identifier
                FROM company
            """)
            
            companies = []
            for row in cursor.fetchall():
                # Create a safe collection prefix from the unique identifier
                unique_id = row[2] if row[2] else str(row[0])
                # Remove special characters for collection name
                safe_prefix = re.sub(r'[^a-zA-Z0-9_]', '_', unique_id)[:50]
                
                companies.append({
                    "company_id": row[0],
                    "company_name": row[1],
                    "unique_identifier": unique_id,
                    "collection_prefix": safe_prefix.lower()
                })
            
            cursor.close()
            conn.close()
            return companies
            
        except Exception as e:
            logger.error(f"Failed to get companies: {e}")
            cursor.close()
            conn.close()
            return []
    
    def set_company_context(self, company_id: str, company_name: str = None):
        """
        Set the current company context for sync operations.
        
        Args:
            company_id: Company identifier
            company_name: Optional company name
        """
        self._current_company_id = company_id
        self._current_company_name = company_name
        logger.info(f"Company context set: {company_id} ({company_name})")
    
    def get_collection_name(self, base_name: str) -> str:
        """
        Get company-specific collection name.
        
        Args:
            base_name: Base collection name (e.g., 'menu_items')
            
        Returns:
            Company-prefixed collection name or base name if no company set
        """
        if self._current_company_id:
            safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', str(self._current_company_id))[:30]
            return f"{safe_id}_{base_name}"
        return base_name
    
    def create_company_collections(
        self,
        company_id: str,
        company_name: str = None,
        vector_size: int = 768
    ) -> bool:
        """
        Create Qdrant collections for a specific company.
        
        Args:
            company_id: Company identifier
            company_name: Optional company name for logging
            vector_size: Vector dimensions
            
        Returns:
            True if collections created successfully
        """
        self._ensure_configured()
        
        # Set company context
        self.set_company_context(company_id, company_name)
        
        try:
            # Create company-specific menu_items collection
            menu_collection = self.get_collection_name(self._config.qdrant.menu_items_collection)
            self._qdrant.create_collection(
                menu_collection,
                vector_size=vector_size,
                on_disk=True
            )
            
            # Create indexes for filtering
            for field, ftype in [
                ("mcode", "keyword"),
                ("menucode", "keyword"),
                ("supplier_code", "keyword"),
                ("supplier_name", "keyword"),
                ("baseunit", "keyword"),
                ("vat", "integer"),
                ("isactive", "integer"),
            ]:
                self._qdrant.create_payload_index(menu_collection, field, ftype)
            
            # Create company-specific ocr_mappings collection
            ocr_collection = self.get_collection_name(self._config.qdrant.ocr_mappings_collection)
            self._qdrant.create_collection(
                ocr_collection,
                vector_size=vector_size
            )
            
            for field, ftype in [
                ("db_mcode", "keyword"),
                ("supplier_name", "keyword"),
                ("usage_count", "integer"),
            ]:
                self._qdrant.create_payload_index(ocr_collection, field, ftype)
            
            logger.info(f"Created collections for company: {company_id} ({company_name})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create company collections: {e}")
            return False
    
    def sync_menu_items(
        self,
        connection_params: Dict = None,
        batch_size: int = 500,
        full_sync: bool = True,
        progress_callback: Callable[[int, int], None] = None,
        resume_from_checkpoint: bool = True,
        incremental_since: datetime = None
    ) -> Dict:
        """
        Sync menu items from SQL Server to Qdrant with checkpoint support.
        
        Args:
            connection_params: Optional DB connection params
            batch_size: Records to process at a time
            full_sync: If True, sync all items; if False, only changed
            progress_callback: Optional callback(current, total) for progress
            resume_from_checkpoint: If True, resume from last checkpoint if available
            incremental_since: Only sync records modified after this timestamp
            
        Returns:
            Sync result statistics
        """
        self._ensure_configured()
        
        with self._sync_lock:
            start_time = time.time()
            # Use company-specific collection if context is set
            collection = self.get_collection_name(self._config.qdrant.menu_items_collection)
            
            logger.info(f"Starting menu items sync (full={full_sync}, collection={collection})")
            
            # Get total count
            total_count = self._count_menu_items(connection_params, incremental_since)
            logger.info(f"Total menu items to sync: {total_count}")
            
            synced = 0
            errors = 0
            offset = 0
            resumed = False
            
            # Check for existing checkpoint
            if resume_from_checkpoint:
                checkpoint = self._load_checkpoint(self._current_company_id, "menu_items")
                if checkpoint:
                    offset = checkpoint['offset']
                    synced = checkpoint['synced']
                    errors = checkpoint['errors']
                    resumed = True
                    logger.info(f"Resuming from checkpoint at offset {offset} ({checkpoint['percentage']:.1f}%)")
            
            try:
                while offset < total_count:
                    # Fetch batch from SQL Server with supplier info
                    items = self._fetch_menu_items(
                        connection_params,
                        limit=batch_size,
                        offset=offset,
                        since_timestamp=incremental_since
                    )
                    
                    if not items:
                        break
                    
                    # Generate embeddings for batch
                    texts = [
                        self._build_menu_item_text(item)
                        for item in items
                    ]
                    
                    try:
                        embeddings = self._embedding.embed_batch(
                            texts,
                            use_cache=True,
                            show_progress=False
                        )
                    except Exception as e:
                        logger.error(f"Embedding generation failed: {e}")
                        errors += len(items)
                        offset += batch_size
                        # Save checkpoint before continuing
                        self._save_checkpoint(
                            "menu_items", offset, total_count, synced, errors,
                            self._current_company_id
                        )
                        continue
                    
                    # Build points for Qdrant with supplier info
                    points = []
                    for item, embedding in zip(items, embeddings):
                        point_id = self._generate_point_id(collection, item['mcode'])
                        
                        points.append({
                            'id': point_id,
                            'vector': embedding,
                            'payload': {
                                'mcode': item['mcode'],
                                'menucode': item.get('menucode') or item['mcode'],
                                'desca': item.get('desca', ''),
                                'desca_normalized': self._embedding.preprocess_text(
                                    item.get('desca', '')
                                ),
                                'baseunit': item.get('baseunit') or '',
                                'confactor': item.get('confactor') or 0,
                                'altunit': item.get('altunit') or '',
                                'vat': item.get('vat', 0),
                                'type': item.get('type', 'A'),
                                'isactive': item.get('isactive', 1),
                                # NEW: Supplier information
                                'supplier_code': item.get('supplier_code') or '',
                                'supplier_name': item.get('supplier_name') or '',
                                'updated_at': datetime.utcnow().isoformat()
                            }
                        })
                    
                    # Upsert to Qdrant
                    try:
                        self._qdrant.upsert_points(collection, points, batch_size=100)
                        synced += len(points)
                    except Exception as e:
                        logger.error(f"Qdrant upsert failed: {e}")
                        errors += len(points)
                    
                    offset += batch_size
                    
                    # Save checkpoint after each batch
                    self._save_checkpoint(
                        "menu_items", offset, total_count, synced, errors,
                        self._current_company_id
                    )
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(min(offset, total_count), total_count)
                    
                    # Log progress
                    pct = (min(offset, total_count) / total_count * 100)
                    logger.info(
                        f"Sync progress: {min(offset, total_count)}/{total_count} "
                        f"({pct:.1f}%) - synced={synced}, errors={errors}"
                    )
                
                # Clear checkpoint on successful completion
                self._clear_checkpoint(self._current_company_id, "menu_items")
                
            except KeyboardInterrupt:
                logger.warning("Sync interrupted by user. Checkpoint saved for resume.")
                self._save_checkpoint(
                    "menu_items", offset, total_count, synced, errors,
                    self._current_company_id
                )
                raise
            except Exception as e:
                logger.error(f"Sync failed: {e}. Checkpoint saved for resume.")
                self._save_checkpoint(
                    "menu_items", offset, total_count, synced, errors,
                    self._current_company_id
                )
                raise
            
            elapsed = time.time() - start_time
            
            # Update stats
            self._sync_stats["menu_items"] = {
                "total": synced,
                "last_sync": datetime.utcnow().isoformat(),
                "duration_seconds": round(elapsed, 2),
                "errors": errors,
                "resumed": resumed
            }
            
            result = {
                "collection": collection,
                "total_records": total_count,
                "synced": synced,
                "errors": errors,
                "duration_seconds": round(elapsed, 2),
                "records_per_second": round(synced / elapsed, 1) if elapsed > 0 else 0,
                "resumed_from_checkpoint": resumed,
                "company_id": self._current_company_id
            }
            
            logger.info(f"Menu items sync completed: {result}")
            return result
    
    def sync_ocr_mappings(
        self,
        connection_params: Dict = None,
        batch_size: int = 500
    ) -> Dict:
        """
        Sync OCR mappings from SQL Server to Qdrant.
        
        These mappings help the system learn from previous successful matches.
        """
        self._ensure_configured()
        
        with self._sync_lock:
            start_time = time.time()
            collection = self._config.qdrant.ocr_mappings_collection
            
            logger.info("Starting OCR mappings sync")
            
            # Fetch all mappings
            items = self._fetch_ocr_mappings(connection_params)
            
            if not items:
                logger.info("No OCR mappings found to sync")
                return {"collection": collection, "synced": 0}
            
            logger.info(f"Found {len(items)} OCR mappings to sync")
            
            # Generate embeddings
            texts = [
                item.get('InvoiceProductName', '')
                for item in items
            ]
            
            embeddings = self._embedding.embed_batch(texts, use_cache=True)
            
            # Build points
            points = []
            for item, embedding in zip(items, embeddings):
                # Create unique key from product name + supplier
                unique_key = f"{item.get('InvoiceProductName', '')}:{item.get('InvoiceSupplierName', '')}"
                point_id = self._generate_point_id(collection, unique_key)
                
                points.append({
                    'id': point_id,
                    'vector': embedding,
                    'payload': {
                        'invoice_product_code': item.get('InvoiceProductCode', ''),
                        'invoice_product_name': item.get('InvoiceProductName', ''),
                        'db_mcode': item.get('Dbmcode', ''),
                        'db_desca': item.get('DbDesca', ''),
                        'db_menucode': item.get('DbMenuCode', ''),
                        'supplier_name': item.get('InvoiceSupplierName', ''),
                        'db_supplier_name': item.get('DbSupplierName', ''),
                        'confidence_score': 1.0,  # Existing mappings are 100% confident
                        'usage_count': 1,
                        'created_at': datetime.utcnow().isoformat()
                    }
                })
            
            # Upsert to Qdrant
            self._qdrant.upsert_points(collection, points, batch_size=100)
            
            elapsed = time.time() - start_time
            
            self._sync_stats["ocr_mappings"] = {
                "total": len(points),
                "last_sync": datetime.utcnow().isoformat(),
                "duration_seconds": round(elapsed, 2)
            }
            
            result = {
                "collection": collection,
                "synced": len(points),
                "duration_seconds": round(elapsed, 2)
            }
            
            logger.info(f"OCR mappings sync completed: {result}")
            return result
    
    def sync_single_item(
        self,
        mcode: str,
        item_data: Dict,
        connection_params: Dict = None
    ) -> bool:
        """
        Sync a single menu item (for incremental updates).
        
        Args:
            mcode: Item mcode (primary key)
            item_data: Item data dictionary with supplier_code and supplier_name
            connection_params: Optional DB connection params
            
        Returns:
            True if successful
        """
        self._ensure_configured()
        
        collection = self.get_collection_name(self._config.qdrant.menu_items_collection)
        
        try:
            # Generate embedding
            text = self._build_menu_item_text(item_data)
            embedding = self._embedding.embed_text(text)
            
            # Generate point ID
            point_id = self._generate_point_id(collection, mcode)
            
            # Prepare point with supplier info
            point = {
                'id': point_id,
                'vector': embedding,
                'payload': {
                    'mcode': mcode,
                    'menucode': item_data.get('menucode') or mcode,
                    'desca': item_data.get('desca', ''),
                    'desca_normalized': self._embedding.preprocess_text(
                        item_data.get('desca', '')
                    ),
                    'baseunit': item_data.get('baseunit') or '',
                    'confactor': item_data.get('confactor') or 0,
                    'altunit': item_data.get('altunit') or '',
                    'vat': item_data.get('vat', 0),
                    'type': item_data.get('type', 'A'),
                    'isactive': item_data.get('isactive', 1),
                    # Supplier information
                    'supplier_code': item_data.get('supplier_code') or '',
                    'supplier_name': item_data.get('supplier_name') or '',
                    'updated_at': datetime.utcnow().isoformat()
                }
            }
            
            # Upsert to Qdrant
            self._qdrant.upsert_points(collection, [point])
            
            logger.debug(f"Synced single item: {mcode}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync item {mcode}: {e}")
            return False
    
    def sync_new_mapping(
        self,
        invoice_product_name: str,
        db_mcode: str,
        db_desca: str,
        supplier_name: str = "",
        db_menucode: str = ""
    ) -> bool:
        """
        Add a new OCR mapping to the vector database.
        
        Called when a new successful mapping is created.
        """
        self._ensure_configured()
        
        collection = self._config.qdrant.ocr_mappings_collection
        
        try:
            # Generate embedding for the invoice product name
            embedding = self._embedding.embed_text(invoice_product_name)
            
            # Generate point ID
            unique_key = f"{invoice_product_name}:{supplier_name}"
            point_id = self._generate_point_id(collection, unique_key)
            
            # Prepare point
            point = {
                'id': point_id,
                'vector': embedding,
                'payload': {
                    'invoice_product_name': invoice_product_name,
                    'db_mcode': db_mcode,
                    'db_desca': db_desca,
                    'db_menucode': db_menucode or db_mcode,
                    'supplier_name': supplier_name,
                    'confidence_score': 1.0,
                    'usage_count': 1,
                    'created_at': datetime.utcnow().isoformat()
                }
            }
            
            # Upsert to Qdrant
            self._qdrant.upsert_points(collection, [point])
            
            logger.info(f"Added new OCR mapping: '{invoice_product_name}' → {db_mcode}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync new mapping: {e}")
            return False
    
    def delete_item(self, mcode: str) -> bool:
        """Delete a menu item from vector database."""
        self._ensure_configured()
        
        collection = self.get_collection_name(self._config.qdrant.menu_items_collection)
        point_id = self._generate_point_id(collection, mcode)
        
        return self._qdrant.delete_points(collection, [point_id])
    
    # ==================== INCREMENTAL SYNC ====================
    
    def sync_incremental(
        self,
        since_timestamp: datetime = None,
        mcode_list: List[str] = None,
        connection_params: Dict = None,
        progress_callback: Callable[[int, int], None] = None
    ) -> Dict:
        """
        Perform incremental sync - only sync changed/new records.
        
        Use this method when:
        - New products are added to the database
        - Existing products are updated
        - You want to sync specific items by mcode
        
        Args:
            since_timestamp: Only sync records modified after this timestamp
            mcode_list: Specific mcodes to sync (for targeted updates)
            connection_params: Optional DB connection params
            progress_callback: Optional callback(current, total)
            
        Returns:
            Sync result statistics
        """
        self._ensure_configured()
        
        with self._sync_lock:
            start_time = time.time()
            collection = self.get_collection_name(self._config.qdrant.menu_items_collection)
            
            logger.info(f"Starting incremental sync (since={since_timestamp}, mcodes={len(mcode_list) if mcode_list else 'all'})")
            
            # Fetch items based on criteria
            if mcode_list:
                # Fetch specific items
                items = self._fetch_menu_items(
                    connection_params,
                    mcode_list=mcode_list
                )
                total_count = len(items)
            elif since_timestamp:
                # Count items modified since timestamp
                total_count = self._count_menu_items(connection_params, since_timestamp)
                items = self._fetch_menu_items(
                    connection_params,
                    since_timestamp=since_timestamp
                )
            else:
                logger.warning("No criteria specified for incremental sync")
                return {"synced": 0, "error": "No criteria specified"}
            
            if not items:
                logger.info("No items to sync")
                return {
                    "collection": collection,
                    "synced": 0,
                    "duration_seconds": 0,
                    "message": "No items matched criteria"
                }
            
            logger.info(f"Found {len(items)} items to sync")
            
            synced = 0
            errors = 0
            
            # Process in batches
            batch_size = 100
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                
                # Generate embeddings
                texts = [self._build_menu_item_text(item) for item in batch]
                
                try:
                    embeddings = self._embedding.embed_batch(texts, use_cache=True, show_progress=False)
                except Exception as e:
                    logger.error(f"Embedding generation failed: {e}")
                    errors += len(batch)
                    continue
                
                # Build points with supplier info
                points = []
                for item, embedding in zip(batch, embeddings):
                    point_id = self._generate_point_id(collection, item['mcode'])
                    points.append({
                        'id': point_id,
                        'vector': embedding,
                        'payload': {
                            'mcode': item['mcode'],
                            'menucode': item.get('menucode') or item['mcode'],
                            'desca': item.get('desca', ''),
                            'desca_normalized': self._embedding.preprocess_text(item.get('desca', '')),
                            'baseunit': item.get('baseunit') or '',
                            'confactor': item.get('confactor') or 0,
                            'altunit': item.get('altunit') or '',
                            'vat': item.get('vat', 0),
                            'type': item.get('type', 'A'),
                            'isactive': item.get('isactive', 1),
                            'supplier_code': item.get('supplier_code') or '',
                            'supplier_name': item.get('supplier_name') or '',
                            'updated_at': datetime.utcnow().isoformat()
                        }
                    })
                
                # Upsert to Qdrant (handles both insert and update)
                try:
                    self._qdrant.upsert_points(collection, points, batch_size=100)
                    synced += len(points)
                except Exception as e:
                    logger.error(f"Qdrant upsert failed: {e}")
                    errors += len(points)
                
                if progress_callback:
                    progress_callback(min(i + batch_size, len(items)), len(items))
            
            elapsed = time.time() - start_time
            
            result = {
                "collection": collection,
                "total_found": len(items),
                "synced": synced,
                "errors": errors,
                "duration_seconds": round(elapsed, 2),
                "mode": "incremental"
            }
            
            logger.info(f"Incremental sync completed: {result}")
            return result
    
    def sync_by_supplier(
        self,
        supplier_code: str,
        connection_params: Dict = None,
        progress_callback: Callable[[int, int], None] = None
    ) -> Dict:
        """
        Sync all menu items for a specific supplier.
        
        Args:
            supplier_code: Supplier code (SUPCODE from menuitem)
            connection_params: Optional DB connection params
            progress_callback: Optional callback(current, total)
            
        Returns:
            Sync result statistics
        """
        self._ensure_configured()
        
        conn = get_connection(connection_params)
        cursor = conn.cursor()
        
        # Get all mcodes for this supplier
        cursor.execute("""
            SELECT mcode FROM menuitem 
            WHERE SUPCODE = ? AND type = 'A' AND isactive = 1
        """, (supplier_code,))
        
        mcode_list = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        if not mcode_list:
            return {"synced": 0, "message": f"No items found for supplier {supplier_code}"}
        
        logger.info(f"Found {len(mcode_list)} items for supplier {supplier_code}")
        
        return self.sync_incremental(
            mcode_list=mcode_list,
            connection_params=connection_params,
            progress_callback=progress_callback
        )
    
    def _build_menu_item_text(self, item: Dict) -> str:
        """
        Build rich text representation for embedding.
        
        Combines multiple fields for better semantic matching.
        """
        parts = []
        
        # Primary: description
        if item.get('desca'):
            parts.append(str(item['desca']))
        
        # Add unit context
        if item.get('baseunit'):
            parts.append(f"UNIT {item['baseunit']}")
        if item.get('altunit') and item.get('altunit') != item.get('baseunit'):
            parts.append(f"ALT {item['altunit']}")
        
        # Extract potential brand (first word)
        if item.get('desca'):
            words = str(item['desca']).split()
            if words and len(words[0]) > 2:
                parts.append(f"BRAND {words[0]}")
        
        return ' '.join(parts)
    
    def get_sync_stats(self) -> Dict:
        """Get synchronization statistics."""
        return {
            "menu_items": self._sync_stats["menu_items"],
            "ocr_mappings": self._sync_stats["ocr_mappings"],
            "qdrant_status": self._get_qdrant_stats()
        }
    
    def _get_qdrant_stats(self) -> Dict:
        """Get Qdrant collection statistics."""
        if not self._qdrant or not self._qdrant.is_connected:
            return {"status": "disconnected"}
        
        try:
            return {
                "status": "connected",
                "collections": self._qdrant.get_all_collections_info()
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def full_sync(
        self,
        connection_params: Dict = None,
        progress_callback: Callable[[str, int, int], None] = None
    ) -> Dict:
        """
        Perform full synchronization of all data.
        
        Args:
            connection_params: Optional DB connection params
            progress_callback: Optional callback(phase, current, total)
            
        Returns:
            Complete sync results
        """
        self._ensure_configured()
        
        results = {
            "start_time": datetime.utcnow().isoformat(),
            "menu_items": None,
            "ocr_mappings": None,
            "end_time": None,
            "total_duration": None
        }
        
        start = time.time()
        
        # Sync menu items
        logger.info("=== Starting full vector sync ===")
        
        def menu_progress(current, total):
            if progress_callback:
                progress_callback("menu_items", current, total)
        
        results["menu_items"] = self.sync_menu_items(
            connection_params,
            progress_callback=menu_progress
        )
        
        # Sync OCR mappings
        results["ocr_mappings"] = self.sync_ocr_mappings(connection_params)
        
        elapsed = time.time() - start
        results["end_time"] = datetime.utcnow().isoformat()
        results["total_duration"] = round(elapsed, 2)
        
        logger.info(f"=== Full sync completed in {elapsed:.1f}s ===")
        
        return results


# Global instance accessor
def get_vector_sync_service() -> VectorSyncService:
    """Get the singleton sync service instance."""
    return VectorSyncService()


def initialize_vector_sync(
    qdrant_manager: QdrantManager,
    embedding_service: EmbeddingService
) -> VectorSyncService:
    """
    Initialize the vector sync service.
    
    Args:
        qdrant_manager: Configured Qdrant manager
        embedding_service: Configured embedding service
        
    Returns:
        Configured VectorSyncService
    """
    service = get_vector_sync_service()
    service.configure(qdrant_manager, embedding_service)
    return service
