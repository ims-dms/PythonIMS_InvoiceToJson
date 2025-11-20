# Token Management System - Quick Reference

## Quick Start

### 1. Setup Database
Run these SQL commands to set up token data:

```sql
-- Create and populate TokenMaster
INSERT INTO [docUpload].TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status, CreatedAt)
VALUES 
('NT047', 'RUBI TRADERS Pvt ltd', 'AIzaSyB7gYAy_0OzJp22NygC0i_nxeSzVDFefnM', 'Gemini', 100000, 'Active', GETDATE()),
('COMP002', 'Company Two', 'YOUR_API_KEY_2', 'Gemini', 100000, 'Active', GETDATE());

-- Verify
SELECT * FROM [docUpload].TokenMaster;
```

### 2. Make API Request
```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@invoice.pdf" \
  -F "companyID=NT047" \
  -F "username=bzumah" \
  -F "branch=RUB"
```

### 3. Check Usage Logs
```sql
-- View usage logs
SELECT * FROM [docUpload].TokenUsageLogs ORDER BY LoggedAt DESC;

-- View summary
SELECT * FROM [docUpload].TokenUsageSummary;

-- View application logs
SELECT * FROM ApplicationLogs ORDER BY Timestamp DESC;
```

---

## Key Classes & Methods

### TokenManager
```python
from token_manager import TokenManager

# Get active token for company
token = TokenManager.get_active_token("NT047")
# Returns: {'success': True, 'token_id': 1, 'api_key': '...', 'provider': 'Gemini', ...}

# Check token status
status = TokenManager.check_token_status("NT047")
# Returns: {'has_error': False, 'status': 'Active', 'message': 'Token is active'}

# Log usage
result = TokenManager.log_token_usage(
    token_id=1,
    usage_info={'input_tokens': 2518, 'output_tokens': 652, ...},
    branch='RUB',
    requested_by='bzumah'
)

# Extract usage from Gemini log
usage = TokenManager.extract_usage_from_log(
    "INFO:api:Gemini processing complete. Usage: RunUsage(...)"
)
```

### RetryPolicy
```python
from retry_policy import RetryPolicy, RetryConfig

# Create policy
config = RetryConfig(max_retries=3)
policy = RetryPolicy(config)

# Execute with retry (async)
result = await policy.execute_with_retry(async_function, arg1, arg2)

# Check retry history
retries = policy.retry_count  # Number of retries that occurred
log = policy.get_retry_log()  # List of retry attempts

# Check if error is retryable
is_retryable = policy.is_retryable_error(exception)
```

### ApplicationLogger
```python
from db_logger import ApplicationLogger

# Configure (done automatically on startup)
ApplicationLogger.configure(log_level=logging.INFO)

# Get logger instance
logger = ApplicationLogger.get_logger(__name__)

# Log messages (saved to database)
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)
```

---

## Error Handling Examples

### Example 1: Invalid File (No Retry)
```
User uploads invalid PDF
↓
PDF conversion fails with: "Unsupported format"
↓
is_retryable_error() returns: False
↓
Response: "Failed to convert PDF"
```

### Example 2: Server Error (With Retry)
```
Gemini API returns: "Service temporarily unavailable"
↓
is_retryable_error() returns: True
↓
Attempt 1: Fails after 1 second delay
↓
Attempt 2: Fails after 2 second delay
↓
Attempt 3: Fails after 4 second delay
↓
Response: "Failed to process invoice"
↓
All attempts logged in RetryAttempts table
```

### Example 3: Token Expired
```
Token status is: 'Expired'
↓
check_token_status() returns error
↓
Response: "Your AI token has expired. Please renew your subscription."
```

---

## Common SQL Queries

### Get token usage for company
```sql
SELECT t.CompanyID, t.CompanyName, u.Branch, u.RequestedBy, 
       u.InputTokens, u.OutputTokens, u.TotalTokensUsed, u.LoggedAt
FROM [docUpload].TokenUsageLogs u
JOIN [docUpload].TokenMaster t ON u.TokenID = t.TokenID
WHERE t.CompanyID = 'NT047'
ORDER BY u.LoggedAt DESC;
```

### Check remaining tokens
```sql
SELECT t.CompanyID, t.CompanyName, ts.TotalUsedTokens, 
       ts.TotalRemainingTokens, ts.Threshold,
       CASE WHEN ts.TotalRemainingTokens < ts.Threshold THEN 'WARNING' 
            ELSE 'OK' END as Status
FROM [docUpload].TokenUsageSummary ts
JOIN [docUpload].TokenMaster t ON ts.TokenID = t.TokenID
WHERE t.Status = 'Active';
```

### View recent errors
```sql
SELECT LogID, LogLevel, Message, Module, FunctionName, Timestamp
FROM ApplicationLogs
WHERE LogLevel IN ('ERROR', 'WARNING')
ORDER BY Timestamp DESC
LIMIT 50;
```

### View retry attempts
```sql
SELECT r.TokenID, r.CompanyID, r.Attempt, r.ErrorMessage, 
       CASE WHEN IsRetryable = 1 THEN 'Yes' ELSE 'No' END as Retryable,
       r.Timestamp
FROM RetryAttempts r
ORDER BY r.Timestamp DESC
LIMIT 100;
```

---

## Configuration Settings

### In api.py - /extract endpoint
```python
# Adjust retry behavior
retry_config = RetryConfig(
    max_retries=3,              # How many times to retry
    initial_delay=1.0,          # Starting delay (seconds)
    max_delay=30.0,             # Maximum delay (seconds)
    backoff_multiplier=2.0,     # Delay multiplier per retry
    jitter=True                 # Add randomness to delays
)

# Change the branch parameter default
branch = branch or 'Default'

# Change database connection method
conn = get_connection(custom_params) or get_connection()
```

### In db_logger.py
```python
# Change table name for logs
TABLE_NAME = 'ApplicationLogs'  # Customize if needed

# Change log level on startup
ApplicationLogger.configure(log_level=logging.DEBUG)
# Options: logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL
```

---

## Troubleshooting

### No token found for company
1. Check: `SELECT * FROM [docUpload].TokenMaster WHERE CompanyID = 'NT047'`
2. Insert token if missing:
   ```sql
  INSERT INTO [docUpload].TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
   VALUES ('NT047', 'Company Name', 'API_KEY', 'Gemini', 100000, 'Active');
   ```

### Tokens not being logged
1. Check: `SELECT * FROM [docUpload].TokenUsageLogs ORDER BY LoggedAt DESC;`
2. Verify token ID is being returned: Check `ApplicationLogs` for "Token X selected"
3. Check Gemini response format: Must contain usage information

### Database logging not working
1. Check: `SELECT * FROM ApplicationLogs ORDER BY Timestamp DESC;`
2. Verify table exists: `SELECT OBJECT_ID('ApplicationLogs')`
3. Check connection string in `DBConnection.txt`
4. Verify ODBC Driver 17 is installed

### Retries not happening
1. Check error type in `ApplicationLogs`
2. Non-retryable errors: invalid file, unsupported format, etc.
3. To force retry: Use keywords like "temporarily", "timeout", "connection"

---

## Database Maintenance

### Archive old logs (monthly)
```sql
-- Backup to archive table
SELECT * INTO ApplicationLogs_Archive_202511 
FROM ApplicationLogs 
WHERE MONTH(Timestamp) = 11 AND YEAR(Timestamp) = 2025;

-- Delete from main table
DELETE FROM ApplicationLogs 
WHERE Timestamp < DATEADD(MONTH, -3, GETDATE());
```

### Reset usage tracking
```sql
-- Clear usage logs for testing
DELETE FROM [docUpload].TokenUsageLogs;
DELETE FROM [docUpload].TokenUsageSummary;
DELETE FROM RetryAttempts;
```

### View database size
```sql
SELECT SUM(CAST(FILEPROPERTY(name, 'SpaceUsed') AS BIGINT)) / 1024.0 / 1024.0 as SizeMB
FROM sysfiles;
```

---

## Performance Tips

1. **Optimize token lookup**: Add index to [docUpload].TokenMaster
   ```sql
  CREATE INDEX idx_company_status ON [docUpload].TokenMaster(CompanyID, Status);
   ```

2. **Archive old logs**: Keep ApplicationLogs table lean
   ```sql
   CREATE INDEX idx_log_timestamp ON ApplicationLogs(Timestamp);
   ```

3. **Monitor token usage**: Set up alerts on token thresholds
   ```sql
  SELECT * FROM [docUpload].TokenUsageSummary 
   WHERE TotalRemainingTokens < Threshold;
   ```

4. **Cache menu items**: System already caches 700k+ items for performance

---

## API Response Examples

### Success
```json
{
  "status": "ok",
  "message": "Invoice processed successfully",
  "data": {
    "order_no": "ORD123",
    "invoice_no": "INV456",
    "products": [...],
    ...
  }
}
```

### Token Error
```json
{
  "status": "error",
  "message": "Your AI token has expired. Please renew your subscription.",
  "data": null
}
```

### Retry Failed
```json
{
  "status": "error",
  "message": "Failed to process invoice",
  "data": {
    "actual_error": "Service temporarily unavailable after 3 retries"
  }
}
```

### Invalid File (No Retry)
```json
{
  "status": "error",
  "message": "Failed to convert PDF",
  "data": {
    "actual_error": "Unsupported PDF format"
  }
}
```

---

## Development Notes

- All console logging has been removed; use `ApplicationLogger` instead
- Do NOT read from `appSetting.txt` directly; use `TokenManager.get_active_token()`
- Always catch and log exceptions to database for auditing
- Retry policy should ONLY be used for transient failures
- Token selection is deterministic (uses `random.choice()` if multiple tokens)

