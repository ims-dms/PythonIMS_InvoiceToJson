"""
QUICK REFERENCE: API Response Format
=====================================

ALL API responses now return this structure:

{
  "status": "ok" | "error",
  "message": "User-friendly message",
  "data": { ... }
}

CHECKING RESPONSES IN YOUR CODE
================================

Frontend/Client Example:

```javascript
const response = await fetch('/extract', {
  method: 'POST',
  body: formData
});

const result = await response.json();

if (result.status === 'ok') {
  // Success!
  const invoiceData = result.data;
  console.log('Success:', result.message);
  console.log('Invoice:', invoiceData);
} else {
  // Error occurred
  console.error('Error:', result.message);
  console.error('Details:', result.data.actual_error); // For debugging
  
  // Show user-friendly message to user
  alert(result.message);
}
```

Python Example:

```python
import requests

response = requests.post('http://localhost:8000/extract', files=files)
result = response.json()

if result['status'] == 'ok':
    print("Success:", result['message'])
    invoice_data = result['data']
    # Process invoice data
else:
    print("Error:", result['message'])
    print("Details:", result['data']['actual_error'])
```

COMMON ERROR MESSAGES
=====================

1. Gemini API Rate Limit (429):
   - User sees: "Error with the server: Resource limit exceeded. Please try again later."
   - Solution: Wait a few minutes and retry

2. Invalid Parameters:
   - User sees: "Please provide both companyID and username."
   - Solution: Check required parameters

3. PDF Processing Error:
   - User sees: "Failed to convert PDF"
   - Solution: Check PDF file is valid and not corrupted

4. Database Connection Error:
   - User sees: "Invalid connection parameters"
   - Solution: Verify connection_params JSON is correct

SUCCESS RESPONSE STRUCTURE
===========================

{
  "status": "ok",
  "message": "Invoice processed successfully",
  "data": {
    "order_no": "...",
    "invoice_no": "...",
    "dealer_name": "...",
    "products": [
      {
        "sku": "LACTOGEN PRO1 BIB 24x400g",
        "quantity": 5,
        "best_match": {
          "desca": "LACTOGEN PRO 1 BIB 24x400g",
          "mcode": "ITM001",
          "score": 95.5,
          "rank": 1
        },
        "match_confidence": "high",
        "mapped_nature": "New Mapped"
      }
    ]
  }
}

KEY FIELDS IN SUCCESS RESPONSE
===============================

- status: Always "ok" for success
- message: "Invoice processed successfully"
- data: Contains all invoice fields
- data.products: Array of products with fuzzy matching results
- data.products[].best_match: Top matching item from database
- data.products[].match_confidence: "high" (>85), "medium" (70-85), "low" (60-70), "none" (<60)
- data.products[].mapped_nature: "Existing" | "New Mapped" | "Not Matched"

ERROR RESPONSE STRUCTURE
========================

{
  "status": "error",
  "message": "User-friendly error message",
  "data": {
    "actual_error": "Detailed technical error for debugging"
  }
}

IMPORTANT NOTES
===============

1. ALWAYS check result['status'] - don't rely on HTTP status codes
2. Show result['message'] to end users
3. Log result['data']['actual_error'] for debugging
4. All responses are valid JSON (no more HTTPException)
5. Errors are handled gracefully with user-friendly messages
"""

if __name__ == "__main__":
    print(__doc__)
