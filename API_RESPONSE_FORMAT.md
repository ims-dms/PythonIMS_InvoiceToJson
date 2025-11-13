# API Response Format Update

## Summary
Updated the API to return standardized responses with proper status codes and user-friendly error messages.

## Response Structure

All API responses now follow this structure:

```json
{
  "status": "ok" | "error",
  "message": "User-friendly message",
  "data": {
    // For success: invoice data
    // For error: { "actual_error": "detailed error" }
  }
}
```

## Success Response Example

```json
{
  "status": "ok",
  "message": "Invoice processed successfully",
  "data": {
    "order_no": "ORD12345",
    "invoice_no": "INV-001",
    "products": [
      {
        "sku": "LACTOGEN PRO1 BIB 24x400g",
        "quantity": 5,
        "best_match": {
          "desca": "LACTOGEN PRO 1 BIB 24x400g",
          "menucode": "ITM001",
          "score": 95.5
        }
      }
    ]
  }
}
```

## Error Response Example

```json
{
  "status": "error",
  "message": "Error with the server: Resource limit exceeded. Please try again later.",
  "data": {
    "actual_error": "Internal server error: status_code: 429, model_name: gemini-2.0-flash-lite, body: {...}"
  }
}
```

## Error Types Handled

1. **429 - Resource Exhausted (Gemini API)**
   - User Message: "Error with the server: Resource limit exceeded. Please try again later."
   - Original error preserved in `data.actual_error`

2. **500 - Internal Server Error**
   - User Message: "Error with the server: Internal server error occurred."

3. **503 - Service Unavailable**
   - User Message: "Error with the server: Service temporarily unavailable."

4. **Timeout Errors**
   - User Message: "Error with the server: Request timed out."

5. **Connection Errors**
   - User Message: "Error with the server: Connection refused."

## New Helper Functions

### 1. `format_api_response(data=None, message=None, status="ok")`
Creates a standardized API response with status, message, and data.

### 2. `minimize_error_message(detail)`
Converts verbose error messages into user-friendly messages.

### 3. `api_error_response(detail)`
Combines the above two functions to create error responses.

## Integration

All error handling in `api.py` now uses these functions:

- ✅ Invalid parameters
- ✅ PDF download failures
- ✅ PDF conversion errors
- ✅ Database connection errors
- ✅ Gemini API errors (429, 500, etc.)
- ✅ JSON parsing errors
- ✅ Unexpected errors

## Benefits

1. **Consistent Response Format**: All responses have the same structure
2. **User-Friendly Messages**: Technical errors are simplified for end users
3. **Debugging Information**: Original errors are preserved in `data.actual_error`
4. **Clear Status**: `status` field makes it easy to check success/failure
5. **Descriptive Messages**: `message` field provides context

## Testing

Run the test files to see examples:

```bash
python test_error_handling.py
python response_format_examples.py
```

## Migration Notes

- Old responses returned raw data or raised HTTPException
- New responses always return JSON with status, message, and data
- Frontend should check `status` field instead of HTTP status codes
- Error details are now in `data.actual_error` instead of `detail` field
