# SKU Classification Fix

## Problem Description

The OCR extraction was incorrectly classifying product identifiers, resulting in:

1. **HSCode values appearing in SKU field**: Numeric codes like "100830" were being extracted into the `sku` (product description) field instead of the `hscode` field
2. **Product codes in wrong field**: Product codes like "1212-MM", "1212-44", "Conditioner" were being placed in `sku_code` instead of `sku`
3. **UI Impact**: The "Item From Doc" column in the UI was showing HSCodes instead of actual product descriptions

### Example Issue
```json
{
    "sku": "",           // Should be "1212-MM" 
    "sku_code": "1212-MM",  // Should be empty
    "hscode": "100830"
}
```

Or worse:
```json
{
    "sku": "100830",     // HSCode in wrong field! Should be empty
    "sku_code": "",
    "hscode": "100830"
}
```

## Solution Implemented

Added enhanced field disambiguation logic in [api.py](api.py) (lines 790-837) that:

### Step 1: Clean up duplicate HSCodes
- If `hscode` and `sku_code` are identical (70%+ overlap), blank out `sku_code`
- If `hscode` is empty but `sku_code` contains HS-like codes (70%+ numeric), move them to `hscode`

### Step 2: Move HSCodes from SKU to HSCode field
```python
# If sku contains an HS code (purely numeric 4-10 digits), move it to hscode
if sku_val and _is_hscode_like(sku_val):
    if not hs_val:
        hscode_list[i] = sku_val
    sku_list[i] = ""
```

### Step 3: Move Product Codes from sku_code to SKU
```python
# If sku is empty but sku_code exists and is NOT an HS code, move it to sku
if not sku_val and sku_code_val and not _is_hscode_like(sku_code_val):
    sku_list[i] = sku_code_val
    sku_code_list[i] = ""
```

## Field Definitions

- **sku**: Product description/name (text) - used for fuzzy matching
- **sku_code**: Optional item/product code (alphanumeric)
- **hscode**: HS Code (4-10 digit numeric code for customs/tax classification)

## HSCode Detection

An HS code is identified by the pattern: `\d{4,10}(?:[.\-]\d{1,4})?`

Examples:
- ✅ `100830` - Valid HSCode
- ✅ `1901` - Valid HSCode
- ✅ `0402.10` - Valid HSCode with decimal
- ❌ `1212-MM` - NOT an HSCode (contains letters)
- ❌ `ABC-123` - NOT an HSCode (contains letters)
- ❌ `Conditioner` - NOT an HSCode (text)

## Test Cases

The fix handles these scenarios correctly:

### Test Case 1: HSCode in SKU field
**Before:**
```
sku="100830", sku_code="1212-MM", hscode=""
```

**After:**
```
sku="1212-MM", sku_code="", hscode="100830"
```

### Test Case 2: Product codes in sku_code
**Before:**
```
sku="", sku_code="1212-MM", hscode="100830"
```

**After:**
```
sku="1212-MM", sku_code="", hscode="100830"
```

### Test Case 3: Numeric codes stay in sku_code
**Before:**
```
sku="", sku_code="100830", hscode=""
```

**After:**
```
sku="", sku_code="100830", hscode=""
```
(No change - numeric code stays in sku_code)

### Test Case 4: Actual descriptions preserved
**Before:**
```
sku="Product Name", sku_code="1212-MM", hscode="100830"
```

**After:**
```
sku="Product Name", sku_code="1212-MM", hscode="100830"
```
(No change - actual product description is preserved)

## Verification

Run the test suite to verify the fix:
```bash
python test_sku_fix.py
```

Expected output: All 4 test cases should pass ✓

## Impact

After this fix:
- ✅ Product descriptions/codes will appear correctly in the UI's "Item From Doc" column
- ✅ Fuzzy matching will work properly (matches against `sku` field)
- ✅ HSCodes will be in the correct field for tax/customs processing
- ✅ Product codes like "1212-MM" will be properly classified as SKUs

## Files Modified

- **api.py** (lines 790-837): Added enhanced field disambiguation logic
- **test_sku_fix.py**: Comprehensive test suite for the fix

## Deployment

1. Restart the API server after deploying this fix
2. Test with the problematic PDF: `Testmultipage.pdf`
3. Verify that "Item From Doc" shows product codes, not HSCodes
4. Confirm fuzzy matching suggestions appear correctly

## Notes

- The fix is non-breaking and backward compatible
- Existing invoices with correct extraction will remain unaffected
- The logic only moves data when fields are misclassified
- All changes are wrapped in try-except for robustness
