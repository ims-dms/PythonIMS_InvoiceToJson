# Vector Search Integration Guide

## Overview

This document describes the vector search integration for the OCR Invoice Processing API. Vector search uses semantic embeddings to significantly improve product matching accuracy compared to pure fuzzy string matching.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OCR Invoice Processing                        │
├─────────────────────────────────────────────────────────────────┤
│  Invoice Image → Gemini OCR → Product Extraction                 │
│                          ↓                                       │
│              ┌───────────────────────┐                          │
│              │   Matching Engine     │                          │
│              ├───────────────────────┤                          │
│              │  1. SQL OCRMappedData │ ← Existing exact matches │
│              │  2. Qdrant Vector DB  │ ← Semantic similarity    │
│              │  3. RapidFuzz Fuzzy   │ ← Character-level match  │
│              └───────────────────────┘                          │
│                          ↓                                       │
│              Hybrid Score = 0.7×Vector + 0.3×Fuzzy              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Vector Database (Qdrant)                      │
├─────────────────────────────────────────────────────────────────┤
│  Collections:                                                    │
│  ├── menu_items     (700k+ products, 1024-dim embeddings)       │
│  ├── ocr_mappings   (learned mappings from successful matches)  │
│  └── suppliers      (supplier name variations)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Vector Config (`vector_config.py`)
- Configuration for Qdrant connection
- Embedding model settings (text-embedding-005, 1024 dimensions)
- Collection schemas

### 2. Embedding Service (`embedding_service.py`)
- Generates 1024-dimensional embeddings using Google's text-embedding-005
- Caching to reduce API calls
- Batch processing for efficiency

### 3. Qdrant Manager (`qdrant_manager.py`)
- Connection management to Qdrant
- Collection creation and indexing
- Batch upsert operations
- Vector similarity search

### 4. Vector Sync (`vector_sync.py`)
- Synchronizes SQL Server data to Qdrant
- Handles MenuItem and OCRMappedData tables
- Incremental sync support

### 5. Vector Matcher (`vector_matcher.py`)
- Hybrid matching combining vector + fuzzy
- Drop-in replacement for fuzzy matcher
- Graceful fallback if vector unavailable

### 6. Vector API (`vector_api.py`)
- REST endpoints for management
- Sync triggers
- Status monitoring

## Setup

### 1. Start Qdrant (Docker)

```bash
# Basic local setup
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# With persistence and performance tuning (recommended for production)
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v /data/qdrant_storage:/qdrant/storage \
  -e QDRANT__STORAGE__STORAGE_PATH=/qdrant/storage \
  -e QDRANT__SERVICE__HTTP_PORT=6333 \
  -e QDRANT__SERVICE__GRPC_PORT=6334 \
  --restart unless-stopped \
  qdrant/qdrant
```

### 2. Install Dependencies

```bash
pip install qdrant-client>=1.7.0 google-generativeai>=0.4.0
# Or install all requirements
pip install -r requirements.txt
```

### 3. Configure Environment

Add to `.env` or set environment variables:

```bash
# Qdrant settings
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Enable vector search
USE_VECTOR_SEARCH=true
VECTOR_SEARCH_AUTO_INIT=true
VECTOR_SEARCH_AUTO_SYNC=false

# Gemini API key (uses existing TokenManager by default)
GEMINI_API_KEY=your-key-here  # Optional if using TokenManager
```

### 4. Initialize and Sync

#### Option A: API Endpoints

```bash
# Initialize vector system
curl -X POST http://localhost:8000/vector/init \
  -H "Content-Type: application/json" \
  -d '{"company_id": "NT047", "auto_sync": true}'

# Check status
curl http://localhost:8000/vector/status

# Manual sync
curl -X POST http://localhost:8000/vector/sync \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}'
```

#### Option B: Python Script

```python
from vector_init import initialize_vector_search_system

# Initialize with auto-sync
system = initialize_vector_search_system(
    gemini_api_key="your-api-key",  # Or will read from appSetting.txt
    qdrant_host="localhost",
    qdrant_port=6333,
    auto_sync=True
)

print(f"Ready: {system.is_ready}")
print(system.get_status())
```

### 5. Run Tests

```bash
python test_vector_search.py
```

## Usage

### Automatic (Default)

The API automatically uses vector search when:
1. `USE_VECTOR_SEARCH=true` (default)
2. Qdrant is connected
3. Vector system is initialized

No code changes needed - the existing `/extract` endpoint uses vector search automatically.

### Manual Vector Search

```python
from vector_matcher import get_vector_matcher

matcher = get_vector_matcher()

# Single search
result = matcher.match_single(
    query="LACTOGEN PRO1 BIB 24x400g",
    limit=5,
    score_cutoff=0.60,
    supplier_name="Nestle",
    use_hybrid=True
)

print(result['best_match'])
print(result['match_method'])  # "hybrid", "vector", or "fuzzy"

# Batch search
results = matcher.match_batch(
    queries=["Product A", "Product B", "Product C"],
    limit=3
)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/vector/init` | POST | Initialize vector system |
| `/vector/status` | GET | Get system status |
| `/vector/sync` | POST | Trigger data sync |
| `/vector/search` | POST | Perform vector search |
| `/vector/search/batch` | POST | Batch vector search |
| `/vector/mapping` | POST | Add new OCR mapping |
| `/vector/sync/item` | POST | Sync single item |
| `/vector/item/{mcode}` | DELETE | Delete item from vectors |
| `/vector/collections` | GET | List collections |
| `/vector/embedding/cache` | GET | Cache statistics |

## Sync Strategies

### Initial Full Sync

For 700,000+ menu items, initial sync takes approximately:
- Embedding generation: ~2-3 hours (with caching)
- Qdrant indexing: ~30 minutes

Run during off-peak hours:

```bash
# Start sync in background
curl -X POST http://localhost:8000/vector/sync \
  -d '{"sync_type": "full"}'
```

### Incremental Sync

When a menu item is added/updated in SQL Server:

```bash
# Sync single item
curl -X POST http://localhost:8000/vector/sync/item \
  -d "mcode=ITM001&desca=New Product 500ml&baseunit=PCS"
```

### Scheduled Sync

Add a cron job for periodic sync:

```bash
# Every night at 2 AM
0 2 * * * curl -X POST http://localhost:8000/vector/sync -d '{"sync_type": "menu_items"}'
```

## Performance Tuning

### Embedding Cache

The embedding service caches embeddings to reduce API calls:

```python
from embedding_service import get_embedding_service

service = get_embedding_service()
stats = service.get_cache_stats()
print(f"Cache hit rate: {stats['hit_rate']}")

# Clear cache if needed
service.clear_cache()
```

### Qdrant Optimization

For 700k+ items, enable disk storage:

```python
# In vector_config.py
qdrant.on_disk = True
```

### Batch Size

Adjust batch sizes for your hardware:

```python
# In vector_sync.py
sync.sync_menu_items(batch_size=1000)  # Larger batches, more memory
```

## Troubleshooting

### Vector search not working

1. Check Qdrant connection:
   ```bash
   curl http://localhost:6333/health
   ```

2. Check system status:
   ```bash
   curl http://localhost:8000/vector/status
   ```

3. Verify collections exist:
   ```bash
   curl http://localhost:8000/vector/collections
   ```

### Poor match quality

1. Ensure full sync completed:
   ```python
   stats = sync.get_sync_stats()
   print(stats['menu_items']['total'])
   ```

2. Check embedding cache:
   ```python
   print(embedding.get_cache_stats())
   ```

3. Adjust score thresholds:
   ```python
   result = matcher.match_single(query, score_cutoff=0.50)  # Lower threshold
   ```

### High latency

1. Enable HNSW index (automatic for >20k points)
2. Increase `ef` for accuracy:
   ```python
   # In qdrant_manager.py search params
   search_params=SearchParams(hnsw_ef=256)
   ```

## Linux Deployment

### Docker Compose (Recommended)

```yaml
# docker-compose.yml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    restart: unless-stopped

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - USE_VECTOR_SEARCH=true
      - VECTOR_SEARCH_AUTO_INIT=true
    depends_on:
      - qdrant
    restart: unless-stopped
```

### Systemd Service

```ini
# /etc/systemd/system/qdrant.service
[Unit]
Description=Qdrant Vector Database
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker start -a qdrant
ExecStop=/usr/bin/docker stop qdrant

[Install]
WantedBy=multi-user.target
```

## Monitoring

### Health Check

```bash
# Check all components
curl http://localhost:8000/vector/status | jq .
```

### Metrics

```python
from vector_init import get_vector_system

status = get_vector_system().get_status()
print(f"Qdrant: {status['qdrant']['connected']}")
print(f"Menu items indexed: {status['qdrant']['collections'][0]['points_count']}")
print(f"Embedding cache hit rate: {status['embedding']['cache']['hit_rate']}")
```

## Security Notes

1. **API Keys**: Never commit API keys. Use environment variables.
2. **Qdrant**: For production, use Qdrant Cloud or add authentication.
3. **Network**: Restrict Qdrant ports to internal network only.

## Migration from Fuzzy-Only

The integration is backward compatible. To migrate:

1. Deploy with `USE_VECTOR_SEARCH=false`
2. Start Qdrant and run initial sync
3. Set `USE_VECTOR_SEARCH=true`
4. Monitor match quality improvements

To rollback, simply set `USE_VECTOR_SEARCH=false`.
