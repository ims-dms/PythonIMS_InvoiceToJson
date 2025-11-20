# Token Management System - Implementation Guide

## Overview

This document outlines the comprehensive token management system that has been implemented for the OCR API. The system includes:

1. **Token Retrieval from Database** - Replaces hardcoded tokens with dynamic database-driven approach
2. **Retry Mechanism** - Implements exponential backoff for handling transient failures
3. **Token Usage Logging** - Automatic logging of token consumption
4. **Database Logging** - All application logs are saved to the database
5. **Error Handling** - Proper error messages for different token statuses

---

## Task 1: Token Retrieval from [docUpload].TokenMaster

### Implementation Details

**Location:** `token_manager.py` - `TokenManager.get_active_token()`

#### Features:
- Retrieves tokens from `[docUpload].TokenMaster` table filtered by:
  - `CompanyID` (provided in API request)
  - `Status = 'Active'`
- If multiple active tokens exist, **randomly selects** one
- Returns token details including: `TokenID`, `ApiKey`, `Provider`, `Status`, `TotalLimit`

#### Usage in API:
```python
token_result = TokenManager.get_active_token(company_id)
if token_result.get('success'):
    api_key = token_result.get('api_key')
    token_id = token_result.get('token_id')
```

#### Fallback Mechanism:
If no token is found in the database, the system falls back to `appSetting.txt`:
```python
model, api_key, token_info = get_gemini_model_and_api_key(company_id)
# Priority: Database > appSetting.txt
```

---

## Task 2: Retry Mechanism & Fallback

### Implementation Details

**Location:** `retry_policy.py` - `RetryPolicy` class

#### Configuration:
```python
RetryConfig(
    max_retries=3,           # Maximum retry attempts
    initial_delay=1.0,       # Initial delay in seconds
    max_delay=30.0,          # Maximum delay in seconds
    backoff_multiplier=2.0,  # Exponential backoff multiplier
    jitter=True              # Add random jitter to delays
)
```

#### Error Classification:

**Retryable Errors:**
- Connection timeouts
- Rate limit / Quota exceeded
- Service temporarily unavailable
- Server errors (5xx)
- "Try again" messages

**Non-Retryable Errors:**
- Invalid file format
- Not an invoice
- Unsupported file type
- Malformed data
- `ValueError`, `FileNotFoundError`

#### Implementation in API:
```python
retry_policy = RetryPolicy(retry_config)
result = await retry_policy.execute_with_retry(process_with_gemini)

# Check if retryable before retrying
if not retry_policy.is_retryable_error(error):
    # Show error immediately to user
    return error_response
```

#### Retry Log Example:
```python
retry_log = [
    {
        'attempt': 1,
        'error': 'Connection timeout',
        'retryable': True,
        'timestamp': 1700000000.123
    },
    {
        'attempt': 2,
        'error': 'Service temporarily unavailable',
        'retryable': True,
        'timestamp': 1700000002.456
    }
]
```

---

## Task 3: Database Tables

### Tables Created

#### 1. TokenMaster
```sql
CREATE TABLE [docUpload].TokenMaster (
    TokenID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID VARCHAR(50),
    CompanyName VARCHAR(200),
    ApiKey VARCHAR(500),
    Provider VARCHAR(100),         -- Gemini / OpenAI
    TotalTokenLimit INT,           -- Internal limit
    Status VARCHAR(50),            -- Active / BelowThreshold / FullyUtilized / Blocked
    CreatedAt DATETIME DEFAULT GETDATE()
);
```

#### 2. TokenUsageLogs
```sql
CREATE TABLE [docUpload].TokenUsageLogs (
    UsageID INT IDENTITY(1,1) PRIMARY KEY,
    TokenID INT FOREIGN KEY REFERENCES [docUpload].TokenMaster(TokenID),
    Branch VARCHAR(50),            -- Which branch/division used the token
    RequestedBy VARCHAR(100),      -- Username who made the request
    InputTokens INT,
    OutputTokens INT,
    TextPromptTokens INT,
    ImagePromptTokens INT,
    TextCandidatesTokens INT,
    TotalTokensUsed INT,
    RequestCount INT,
    LoggedAt DATETIME DEFAULT GETDATE()
);
```

#### 3. TokenUsageSummary
```sql
CREATE TABLE [docUpload].TokenUsageSummary (
    SummaryID INT IDENTITY(1,1) PRIMARY KEY,
    TokenID INT FOREIGN KEY REFERENCES [docUpload].TokenMaster(TokenID),
    TotalUsedTokens INT DEFAULT 0,
    TotalRemainingTokens INT,
    Threshold INT DEFAULT 3000,        -- Warning threshold
    LastUpdated DATETIME DEFAULT GETDATE()
);
```

#### 4. ApplicationLogs (Database Logging)
```sql
CREATE TABLE ApplicationLogs (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    Timestamp DATETIME DEFAULT GETDATE(),
    LogLevel VARCHAR(20),            -- DEBUG, INFO, WARNING, ERROR
    Logger VARCHAR(255),
    Message VARCHAR(MAX),
    Exception VARCHAR(MAX),
    Module VARCHAR(255),
    FunctionName VARCHAR(255),
    LineNumber INT
);
```

#### 5. RetryAttempts (Retry Logging)
```sql
CREATE TABLE RetryAttempts (
    RetryID INT IDENTITY(1,1) PRIMARY KEY,
    TokenID INT,
    CompanyID VARCHAR(50),
    Attempt INT,
    ErrorMessage VARCHAR(MAX),
    IsRetryable BIT,
    Timestamp DATETIME DEFAULT GETDATE()
);
```

### Automatic Table Creation

Tables are automatically created on application startup:
```python
@app.on_event("startup")
async def startup_event():
    conn = get_connection()
    create_token_tables(conn)  # Creates all tables if they don't exist
    conn.close()
```

---

## Task 4: Error Messages

### Token Status Messages

#### 1. Expired Token
**Status:** `Expired`
```
Message: "Your AI token has expired. Please renew your subscription."
```

#### 2. Exceeded / Disabled Token
**Status:** `Exceeded` or `Disabled`
```
Message: "Your AI token is no longer available or has been disabled. Please contact support."
```

#### 3. No Token Found
**Status:** No active token exists
```
Message: "No active token found for your company. Please contact support."
```

#### 4. Invalid File
**Status:** User uploads invalid file
```
Message: "Failed to process invoice" (shown immediately, no retry)
```

### Implementation in API
```python
# Check token status first
status_check = TokenManager.check_token_status(company_id)
if status_check.get('has_error'):
    return format_api_response(
        message=status_check.get('message'),
        status="error"
    )
```

---

## Token Usage Logging

### Automatic Logging

When OCR processing completes, usage is automatically logged:

```python
# Parse usage from Gemini response
usage_details = TokenManager.extract_usage_from_log(usage_info_string)

# Log to database
log_result = TokenManager.log_token_usage(
    token_id=token_id,
    usage_info=usage_details,
    branch=branch,           # Optional: branch/division
    requested_by=username    # Optional: username
)
```

### Usage Information Extracted

From log message like:
```
INFO:api:Gemini processing complete. Usage: RunUsage(
    input_tokens=2518,
    output_tokens=652,
    details={
        'text_prompt_tokens': 712,
        'image_prompt_tokens': 1806,
        'text_candidates_tokens': 652
    },
    requests=1
)
```

Extracted as:
```python
{
    'input_tokens': 2518,
    'output_tokens': 652,
    'text_prompt_tokens': 712,
    'image_prompt_tokens': 1806,
    'text_candidates_tokens': 652,
    'requests': 1
}
```

### Updates

1. **TokenUsageLogs** - New entry inserted with all usage details
2. **TokenUsageSummary** - Updated with running totals:
   - `TotalUsedTokens` += tokens used
   - `TotalRemainingTokens` = limit - total used
   - `LastUpdated` = current timestamp

---

## Database Logging

### All Logs Saved to Database

The `ApplicationLogger` handles all logging:

```python
# Application startup
ApplicationLogger.configure(log_level=logging.INFO)

# Usage in any module
logger = ApplicationLogger.get_logger(__name__)
logger.info("Invoice processing started")  # Saved to ApplicationLogs table
logger.error("Processing failed", exc_info=True)  # Exception included
```

### Log Levels Recorded

- **DEBUG** - Detailed diagnostic information
- **INFO** - Informational messages
- **WARNING** - Warning messages
- **ERROR** - Error messages with exceptions
- **CRITICAL** - Critical errors

### Log Entry Structure

```python
{
    'LogID': 1,
    'Timestamp': '2025-11-19 12:30:45.123',
    'LogLevel': 'INFO',
    'Logger': 'api',
    'Message': 'Token 5 selected for company NT047',
    'Exception': None,
    'Module': 'token_manager',
    'FunctionName': 'get_active_token',
    'LineNumber': 42
}
```

---

## API Changes

### Updated Endpoint: /extract

**New Parameters:**
- `branch` (optional) - Branch/division using the token

**Removed Parameter:**
- Direct API key (now uses [docUpload].TokenMaster)

**New Response Fields:**
- Token information is logged internally
- Retry attempts are logged if they occur

### Request Example:
```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@invoice.pdf" \
  -F "companyID=NT047" \
  -F "username=bzumah" \
  -F "branch=RUB" \
  -F "licenceID=LIC001"
```

### Token Selection Process:
1. Check if token exists and is active for company
2. Show error if no token or token is expired/disabled
3. Randomly select token if multiple active tokens exist
4. Use selected token for Gemini processing
5. Log usage after successful processing

---

## Modules Overview

### `token_manager.py`
- `TokenManager.get_active_token()` - Retrieve active token for company
- `TokenManager.check_token_status()` - Check token status
- `TokenManager.log_token_usage()` - Log usage to database
- `TokenManager.extract_usage_from_log()` - Parse usage from log string

### `retry_policy.py`
- `RetryConfig` - Configuration for retry behavior
- `RetryPolicy` - Implements retry logic with exponential backoff
- `is_retryable_error()` - Classify if error is retryable
- `execute_with_retry()` - Async retry execution
- `execute_with_retry_sync()` - Sync retry execution

### `db_logger.py`
- `DatabaseLogHandler` - Custom logging handler for database
- `ApplicationLogger` - Centralized logging configuration
- `log_retry_attempts()` - Log retry attempts to database

### `db_connection.py` (Updated)
- `create_token_tables()` - Create token management tables
- Existing functions unchanged

---

## Configuration

### Retry Configuration
Edit in `api.py` `/extract` endpoint:
```python
retry_config = RetryConfig(
    max_retries=3,              # Change to adjust retry attempts
    initial_delay=1.0,          # Change initial delay
    max_delay=30.0,             # Change maximum delay
    backoff_multiplier=2.0,     # Change backoff multiplier
    jitter=True                 # Toggle jitter on/off
)
```

### Logging Level
Edit in `api.py` startup:
```python
ApplicationLogger.configure(log_level=logging.INFO)
# Change logging.INFO to:
# - logging.DEBUG (most verbose)
# - logging.WARNING (less verbose)
# - logging.ERROR (errors only)
```

---

## Data Flow Diagram

```
Request → Check Token Status
         ↓
    Token Valid?
    ↙ (Yes)        ↘ (No)
Select Token    Return Error
    ↓
Process with Gemini
(with Retry Logic)
    ↓
Success?
↙ (Yes)           ↘ (No)
Extract Usage    Check Retryable?
    ↓             ↙ (No)
Log Usage      Return Error
    ↓             
Return Result
```

---

## Testing

### Test Token Selection:
```python
from token_manager import TokenManager

result = TokenManager.get_active_token("NT047")
if result.get('success'):
    print(f"Token ID: {result.get('token_id')}")
    print(f"API Key: {result.get('api_key')}")
```

### Test Retry Logic:
```python
from retry_policy import RetryPolicy, RetryConfig

config = RetryConfig(max_retries=3)
policy = RetryPolicy(config)

# Test retryable error
async def test_func():
    raise ConnectionError("Connection timeout")

try:
    await policy.execute_with_retry(test_func)
except Exception as e:
    print(f"Retries: {policy.retry_count}")
    print(f"Log: {policy.get_retry_log()}")
```

### Test Database Logging:
```python
from db_logger import ApplicationLogger

logger = ApplicationLogger.get_logger(__name__)
logger.info("Test message")  # Saved to ApplicationLogs table
```

---

## Requirements

New dependency added to `requirements.txt`:
```
tenacity
```

Install with:
```bash
pip install -r requirements.txt
```

---

## Migration Notes

If you have existing token data, you need to:

1. **Populate TokenMaster table** with your API keys:
```sql
INSERT INTO [docUpload].TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
VALUES ('NT047', 'RUBI TRADERS Pvt ltd', 'YOUR_API_KEY_HERE', 'Gemini', 100000, 'Active');
```

2. **Remove or backup** `appSetting.txt` (system now reads from database first)

3. **Restart** the application to initialize tables

---

## Support

For issues or questions:
1. Check `ApplicationLogs` table for detailed error information
2. Check `RetryAttempts` table for retry behavior
3. Verify token exists and is Active in `[docUpload].TokenMaster`
4. Ensure database tables exist and are properly configured

