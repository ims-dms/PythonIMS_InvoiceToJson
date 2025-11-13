"""
Example of the final API response format with:
- Status: "ok" or "error"
- User Message: User-friendly message
- Actual Error: Original error details (for debugging)
"""

import json

# Example 1: Error response (e.g., Gemini 429 error)
error_response = {
    "status": "error",
    "message": "Error with the server: Resource limit exceeded. Please try again later.",
    "data": {
        "actual_error": 'Internal server error: status_code: 429, model_name: gemini-2.0-flash-lite, body: {\n  "error": {\n    "code": 429,\n    "message": "Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.",\n    "status": "RESOURCE_EXHAUSTED"\n  }\n}\n'
    }
}

print("=" * 80)
print("Example 1: ERROR Response (Gemini 429)")
print("=" * 80)
print(json.dumps(error_response, indent=2))

# Example 2: Success response
success_response = {
    "status": "ok",
    "message": "Invoice processed successfully",
    "data": {
        "order_no": "ORD12345",
        "invoice_no": "INV-2024-001",
        "delivery_note": "DN-001",
        "vehicle_no": "BA 1 KHA 1234",
        "transporter": "ABC Transport",
        "date": "2024-01-15",
        "dealer_name": "ABC Store",
        "pws_no": "PWS123",
        "company_name": "XYZ Suppliers",
        "transaction_type": "Cash",
        "transaction_date": "2024-01-15",
        "due_date": "2024-01-30",
        "invoice_miti": "2080-10-01",
        "invoice_date": "2024-01-15",
        "products": [
            {
                "sku": "LACTOGEN PRO1 BIB 24x400g",
                "sku_code": "12579462",
                "quantity": 5,
                "shortage": 0,
                "breakage": 0,
                "leakage": 0,
                "batch": "BATCH001",
                "sno": "001",
                "rate": 450.50,
                "discount": 10.0,
                "mrp": 500.0,
                "vat": 13.0,
                "hscode": "1901",
                "altQty": 0,
                "unit": "PCS",
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

print("\n" + "=" * 80)
print("Example 2: SUCCESS Response")
print("=" * 80)
print(json.dumps(success_response, indent=2))

print("\n" + "=" * 80)
print("Response Structure:")
print("=" * 80)
print("""
For ALL responses, the structure is:
{
  "status": "ok" | "error",
  "message": "User-friendly message",
  "data": {
    // For success: invoice data with products
    // For error: { "actual_error": "detailed error for debugging" }
  }
}

SUCCESS Example:
- status: "ok"
- message: "Invoice processed successfully"
- data: Contains the full invoice data with products and fuzzy matching results

ERROR Example:
- status: "error"
- message: "Error with the server: Resource limit exceeded. Please try again later."
- data: { "actual_error": "Internal server error: status_code: 429, ..." }

The user sees the "message" field (user-friendly).
Developers can check "actual_error" in data for debugging.
""")
