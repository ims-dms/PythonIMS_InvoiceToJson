"""
Test the new error handling and response formatting
"""

from fuzzy_matcher import format_api_response, minimize_error_message, api_error_response

# Test 1: Minimizing the Gemini 429 error
gemini_error = """Internal server error: status_code: 429, model_name: gemini-2.0-flash-lite, body: {
  "error": {
    "code": 429,
    "message": "Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.",
    "status": "RESOURCE_EXHAUSTED"
  }
}
"""

print("=" * 80)
print("Test 1: Gemini 429 Error")
print("=" * 80)
print("\nOriginal error:")
print(gemini_error[:200] + "...")
print("\nMinimized message:")
print(minimize_error_message(gemini_error))
print("\nAPI error response:")
import json
print(json.dumps(api_error_response(gemini_error), indent=2))

# Test 2: Success response
print("\n" + "=" * 80)
print("Test 2: Success Response")
print("=" * 80)
success_data = {
    "order_no": "12345",
    "invoice_no": "INV-001",
    "products": [
        {"sku": "LACTOGEN PRO1", "quantity": 5}
    ]
}
print(json.dumps(format_api_response(data=success_data, message="Invoice processed successfully", status="ok"), indent=2))

# Test 3: Different error types
print("\n" + "=" * 80)
print("Test 3: Various Error Types")
print("=" * 80)

test_errors = [
    "Connection refused to database server",
    "Request timeout after 30 seconds",
    "status_code: 500, Internal server error occurred",
    "Service Unavailable: status_code: 503",
    "Some random error message"
]

for err in test_errors:
    print(f"\nOriginal: {err[:50]}...")
    print(f"Minimized: {minimize_error_message(err)}")

print("\n" + "=" * 80)
print("All tests completed!")
print("=" * 80)
