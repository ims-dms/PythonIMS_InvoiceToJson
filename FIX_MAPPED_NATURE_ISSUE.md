# Fix: Mapped_Nature Always Returning "New Mapped" Instead of "Existing"

## Problem
When calling `/extract` endpoint with fuzzy matching, the response always returns `"mapped_nature": "New Mapped"` even when products should already exist in the `OCRMappedData` database table.

## Root Cause
The issue was **insufficient logging and debugging** in the database lookup process. The code attempts to check the `OCRMappedData` table for existing mappings BEFORE falling back to fuzzy matching, but:

1. **Silent Failures**: If the database lookup failed or was skipped, there was no logging to indicate this
2. **Missing Supplier Name**: If `supplier_name` wasn't properly extracted or was empty, the database lookup was completely skipped
3. **No Query Diagnostics**: There was no logging showing:
   - Whether the database lookup was attempted
   - What parameters were used for the query
   - What results were returned from the database

## Solution Implemented

### Changes to `fuzzy_matcher.py`

#### 1. Added Diagnostic Logging Before Database Lookup
```python
logger.debug(f"Processing product: sku_query='{sku_query}', connection={connection is not None}, supplier_name='{supplier_name}'")

if connection and supplier_name:
    try:
        cursor = connection.cursor()
        logger.debug(f"Attempting database lookup for sku_query='{sku_query}' with supplier_name='{supplier_name}'")
```

#### 2. Added Query Result Logging
```python
row = cursor.fetchone()
logger.debug(f"Database query result for sku_query='{sku_query}' and supplier_name='{supplier_name}': {row}")

if row:
    # ... create mapped_match ...
    logger.info(f"Found existing mapping in OCRMappedData: {mapped_match}")
else:
    logger.debug(f"No mapping found in OCRMappedData for sku_query='{sku_query}' with supplier_name='{supplier_name}'")
```

#### 3. Added Logging When Lookup is Skipped
```python
else:
    logger.debug(f"Skipping OCRMappedData lookup: connection={'not provided' if not connection else 'provided'}, supplier_name={'empty' if not supplier_name else 'provided'}")
```

### Changes to `api.py`

#### 1. Enhanced Supplier Name Extraction and Logging
```python
supplier_name = (data.get('company_name', '') or '').strip()
logger.info(f"Supplier name extracted from invoice: '{supplier_name}'")
logger.info(f"Database connection available: {db_conn is not None}")
```

## How to Verify the Fix is Working

### Check Logs
When the `/extract` endpoint is called, you should now see logs like:

**Case 1: Existing Mapping Found**
```
Processing product: sku_query='LACTOGEN PRO1 BIB 24x400g', connection=True, supplier_name='Company ABC'
Attempting database lookup for sku_query='LACTOGEN PRO1 BIB 24x400g' with supplier_name='Company ABC'
Database query result for sku_query='LACTOGEN PRO1 BIB 24x400g' and supplier_name='Company ABC': ('ITM001', 'LACTOGEN PRO1 BIB 24x400g', 'MENU001')
Found existing mapping in OCRMappedData: {'desca': 'LACTOGEN PRO1 BIB 24x400g', 'mcode': 'ITM001', 'menucode': 'MENU001', 'score': 100.0, 'rank': 1}
```
→ Result: `"mapped_nature": "Existing"`

**Case 2: No Mapping Found - Falls Back to Fuzzy Matching**
```
Processing product: sku_query='LACTOGEN PRO1 BIB 24x400g', connection=True, supplier_name='Company ABC'
Attempting database lookup for sku_query='LACTOGEN PRO1 BIB 24x400g' with supplier_name='Company ABC'
Database query result for sku_query='LACTOGEN PRO1 BIB 24x400g' and supplier_name='Company ABC': None
No mapping found in OCRMappedData for sku_query='LACTOGEN PRO1 BIB 24x400g' with supplier_name='Company ABC'
```
→ Result: `"mapped_nature": "New Mapped"` or `"Not Matched"` (depending on fuzzy match results)

**Case 3: Database Lookup Skipped**
```
Skipping OCRMappedData lookup: connection=provided, supplier_name=empty
```
→ Result: Always `"mapped_nature": "New Mapped"`

## Troubleshooting Steps

If you're still seeing only "New Mapped":

1. **Enable Debug Logging**
   - Ensure logger level is set to DEBUG in `ApplicationLogger.configure()`
   - Check if debug logs appear in your logs

2. **Verify Supplier Name**
   - Look for: `Supplier name extracted from invoice: '...'`
   - If it shows `'Existing'` is still not appearing, the supplier name from the invoice might not match what's in the database

3. **Check Database Connection**
   - Look for: `Database connection available: True/False`
   - If False, the connection isn't being passed

4. **Verify OCRMappedData Table**
   - Manually check if records exist in `[docUpload].[OCRMappedData]`
   - Ensure the `InvoiceProductName` and `InvoiceSupplierName` match exactly what's in the invoice

5. **Database Query Matching**
   - The query uses exact matching: `WHERE InvoiceProductName = ? AND InvoiceSupplierName = ?`
   - Both fields must match EXACTLY (case-sensitive by default in SQL Server)
   - If data has extra spaces or different casing, it won't match

## API Flow (Now with Proper Checking)

```
1. Client calls POST /extract with invoice file
   ↓
2. Gemini extracts: company_name, sku, sku_code, etc.
   ↓
3. API extracts supplier_name = company_name.strip()
   ↓
4. For each product:
   a) Check OCRMappedData table
      - If found → mapped_nature = "Existing" ✓
      - If not found → proceed to step b)
   
   b) Perform fuzzy matching on database menu items
      - If fuzzy match score ≥ 85 → mapped_nature = "New Mapped", match_confidence = "high"
      - If fuzzy match score 70-85 → mapped_nature = "New Mapped", match_confidence = "medium"
      - If fuzzy match score 60-70 → mapped_nature = "New Mapped", match_confidence = "low"
      - If no fuzzy match → mapped_nature = "Not Matched"
```

## Response Examples

### Existing Mapping (from OCRMappedData table)
```json
{
  "sku": "LACTOGEN PRO1 BIB 24x400g",
  "best_match": {
    "desca": "LACTOGEN PRO1 BIB 24x400g",
    "mcode": "ITM001",
    "menucode": "MENU001",
    "score": 100.0,
    "rank": 1
  },
  "mapped_nature": "Existing"
}
```

### New Mapped (from Fuzzy Matching)
```json
{
  "sku": "LACTOGEN PRO1 BIB 24x400g",
  "fuzzy_matches": [
    {
      "desca": "LACTOGEN PRO1 BIB 24x400g",
      "mcode": "ITM001",
      "menucode": "MENU001",
      "score": 95.5,
      "rank": 1
    }
  ],
  "best_match": {
    "desca": "LACTOGEN PRO1 BIB 24x400g",
    "mcode": "ITM001",
    "menucode": "MENU001",
    "score": 95.5,
    "rank": 1
  },
  "match_confidence": "high",
  "mapped_nature": "New Mapped"
}
```

### Not Matched
```json
{
  "sku": "UNKNOWN PRODUCT XYZ",
  "fuzzy_matches": [],
  "best_match": null,
  "match_confidence": "none",
  "mapped_nature": "Not Matched"
}
```
