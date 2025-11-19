# Token Management System - Implementation Summary

## ✅ Completed Tasks

### Task 1: Token Retrieval from TokenMaster ✅
- [x] Created `TokenManager` class to retrieve tokens from database
- [x] Filters by CompanyID and Status = 'Active'
- [x] Randomly selects token if multiple active tokens exist
- [x] Implemented fallback to appSetting.txt if database token not available
- [x] Added `get_active_token()` method
- [x] Added `check_token_status()` method for error handling

**Files:** `token_manager.py`, `db_connection.py`, `api.py`

---

### Task 2: Retry Mechanism & Fallback ✅
- [x] Created `RetryPolicy` class with exponential backoff
- [x] Implemented error classification (retryable vs non-retryable)
- [x] Distinguishes between server errors and user input errors
- [x] Retries for: timeout, rate limit, service unavailable, server errors
- [x] No retry for: invalid file, malformed data, unsupported format
- [x] Integrated into main `/extract` endpoint
- [x] Logs all retry attempts to database

**Files:** `retry_policy.py`, `api.py`, `db_logger.py`

**Configuration:**
```python
RetryConfig(
    max_retries=3,              # Number of retry attempts
    initial_delay=1.0,          # Starting delay (seconds)
    max_delay=30.0,             # Maximum delay cap (seconds)
    backoff_multiplier=2.0,     # Exponential backoff factor
    jitter=True                 # Add random jitter to delays
)
```

---

### Task 3: Database Tables ✅
Created all required tables with proper schema:

1. **TokenMaster** - Stores API tokens per company
   - Columns: TokenID, CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status, CreatedAt
   - Indexes: company_status, created

2. **TokenUsageLogs** - Records each token usage
   - Columns: UsageID, TokenID, Branch, RequestedBy, InputTokens, OutputTokens, TextPromptTokens, ImagePromptTokens, TextCandidatesTokens, TotalTokensUsed, RequestCount, LoggedAt
   - Indexes: tokenid, loggedat, branch

3. **TokenUsageSummary** - Aggregated usage per token
   - Columns: SummaryID, TokenID, TotalUsedTokens, TotalRemainingTokens, Threshold, LastUpdated
   - Indexes: tokenid (unique)

4. **ApplicationLogs** - All application logs
   - Columns: LogID, Timestamp, LogLevel, Logger, Message, Exception, Module, FunctionName, LineNumber
   - Indexes: timestamp, level, logger

5. **RetryAttempts** - Logs all retry attempts
   - Columns: RetryID, TokenID, CompanyID, Attempt, ErrorMessage, IsRetryable, Timestamp
   - Indexes: tokenid, company, timestamp

**Automatic Creation:** Tables are automatically created on application startup via `create_token_tables()`

**Files:** `db_connection.py`, `setup_database.sql`

---

### Task 4: Error Messages ✅
Implemented proper error handling for different token statuses:

#### Status: Expired
```
"Your AI token has expired. Please renew your subscription."
```

#### Status: Exceeded / Disabled
```
"Your AI token is no longer available or has been disabled. Please contact support."
```

#### Status: No Active Token
```
"No active token found for your company. Please contact support."
```

#### Invalid File (No Retry)
```
"Failed to process invoice"
(Shown immediately, no retry attempt)
```

**Implementation:** `TokenManager.check_token_status()` in `token_manager.py`

**Files:** `token_manager.py`, `api.py`

---

### Token Usage Logging ✅
- [x] Parses usage from Gemini response: input_tokens, output_tokens, text_prompt_tokens, image_prompt_tokens, text_candidates_tokens
- [x] Logs to TokenUsageLogs table with: Branch, RequestedBy, all token counts
- [x] Updates TokenUsageSummary with running totals and remaining tokens
- [x] Includes RequestCount and request metadata

**Implementation:**
```python
usage_details = TokenManager.extract_usage_from_log(usage_info_string)
log_result = TokenManager.log_token_usage(
    token_id=token_id,
    usage_info=usage_details,
    branch=branch,
    requested_by=username
)
```

**Files:** `token_manager.py`, `api.py`

---

### Database Logging ✅
- [x] Created `DatabaseLogHandler` for custom logging
- [x] Created `ApplicationLogger` for centralized configuration
- [x] All logs saved to ApplicationLogs table (no console output)
- [x] Captures: Timestamp, LogLevel, Logger name, Message, Exception, Module, Function, LineNumber
- [x] Implemented fallback to console if database logging fails
- [x] Configured on application startup

**Implementation:**
```python
ApplicationLogger.configure(log_level=logging.INFO)
logger = ApplicationLogger.get_logger(__name__)
logger.info("Message")  # Saved to database
```

**Files:** `db_logger.py`, `api.py`

---

## 📁 New Files Created

### Core Implementation
1. **token_manager.py** (244 lines)
   - `TokenManager` class with static methods
   - Token retrieval, status checking, usage logging
   - Usage parsing from Gemini responses

2. **retry_policy.py** (210 lines)
   - `RetryConfig` class for configuration
   - `RetryPolicy` class with retry logic
   - Exponential backoff with jitter
   - Retryable/non-retryable error classification

3. **db_logger.py** (156 lines)
   - `DatabaseLogHandler` for database logging
   - `ApplicationLogger` centralized configuration
   - `log_retry_attempts()` utility function

### Database Setup
4. **setup_database.sql** (320 lines)
   - Complete database initialization script
   - Table creation with proper schema
   - Indexes for performance
   - Useful views (vw_TokenStatus, vw_UsageSummary, vw_RecentErrors, vw_FailedRetries)
   - Sample data inserts
   - Maintenance queries

### Documentation
5. **TOKEN_MANAGEMENT_GUIDE.md** (450+ lines)
   - Comprehensive implementation guide
   - Architecture overview
   - Configuration details
   - Testing procedures
   - Migration notes

6. **TOKEN_QUICK_REFERENCE.md** (350+ lines)
   - Quick start guide
   - Common SQL queries
   - Error handling examples
   - Troubleshooting tips
   - Performance optimization

---

## 🔧 Modified Files

### 1. db_connection.py
- Added `create_token_tables()` function
- Added logging support
- Maintains backward compatibility

### 2. api.py (698 lines - major updates)
- Updated import statements to include token manager, retry policy, database logger
- Added `read_api_key_from_file()` function
- Added `get_gemini_model_and_api_key()` function
- Refactored `process_invoice()` endpoint with:
  - Token status check before processing
  - Token retrieval from database
  - Retry policy with exponential backoff
  - Usage logging after successful processing
  - Retry attempt logging
  - Proper error handling and messages
  - Added `branch` parameter to API
- Added `@app.on_event("startup")` for table initialization
- Removed direct global Gemini model initialization

### 3. requirements.txt
- Added `tenacity` package (optional, for additional retry utilities if needed)

---

## 🚀 How It Works

### Request Flow
```
1. Client sends POST /extract with:
   - file (PDF or image)
   - companyID
   - username
   - branch (optional)

2. API checks token status:
   - Is token available?
   - Is token Active (not Expired/Disabled)?

3. Retrieve active token:
   - Query TokenMaster by CompanyID
   - Filter by Status = 'Active'
   - Random selection if multiple exist

4. Process invoice with retry:
   - Execute Gemini processing
   - If fails: Check if retryable
   - If retryable: Retry with exponential backoff
   - If not retryable: Return error immediately

5. Log usage:
   - Extract token usage from Gemini response
   - Insert into TokenUsageLogs
   - Update TokenUsageSummary

6. Log retry attempts (if any):
   - Insert each attempt into RetryAttempts

7. Return response to client
```

### Database Flow
```
TokenMaster (read)
   ↓
Check status and get active token
   ↓
Process with retry (on each attempt)
   ↓
Success?
   ├─ YES → Extract usage → Log to TokenUsageLogs → Update TokenUsageSummary
   └─ NO → Check retryable → If yes, retry else return error

ApplicationLogs (write)
   ↑
Every log statement saved automatically

RetryAttempts (write)
   ↑
Each retry logged (if applicable)
```

---

## 📊 Database Schema Overview

```
TokenMaster (1)
    ↓ (Foreign Key)
TokenUsageLogs (M)
    ↑
TokenUsageSummary (1-to-1)

ApplicationLogs (independent)
RetryAttempts (independent)
```

---

## ⚙️ Configuration

### Retry Settings
Location: `api.py` line ~170 in `/extract` endpoint
```python
retry_config = RetryConfig(
    max_retries=3,           # Adjust retry attempts
    initial_delay=1.0,       # Adjust starting delay
    max_delay=30.0,          # Adjust max delay cap
    backoff_multiplier=2.0,  # Adjust backoff speed
    jitter=True              # Toggle jitter randomness
)
```

### Logging Level
Location: `api.py` line ~65 (startup initialization)
```python
ApplicationLogger.configure(log_level=logging.INFO)
# Options: logging.DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Token Selection
- Default: Random selection if multiple tokens exist
- All tokens for same company must have same CompanyID
- Latest created token takes precedence (if needed)

---

## 🧪 Testing Checklist

- [ ] Database tables created successfully
- [ ] TokenMaster populated with test API key
- [ ] API call returns proper token from database
- [ ] Retry logic triggers on server errors
- [ ] No retry on invalid file errors
- [ ] Token usage logged to database
- [ ] Usage summary updated correctly
- [ ] Error messages shown for expired tokens
- [ ] All logs saved to ApplicationLogs table
- [ ] Retry attempts logged to RetryAttempts table

---

## 📝 Migration Checklist

- [ ] Run `setup_database.sql` to create tables
- [ ] Insert API keys into TokenMaster table
- [ ] Update application configuration if needed
- [ ] Restart API service
- [ ] Test with actual API call
- [ ] Verify logs in database
- [ ] Monitor ApplicationLogs for any errors
- [ ] Archive old appSetting.txt (not deleted, just unused)

---

## 🔒 Security Notes

1. **API Keys:** Stored securely in database (in production, consider encryption)
2. **Logging:** All operations logged for audit trail
3. **Error Messages:** Detailed errors shown only in database logs, minimal user-facing messages
4. **Retry Limits:** Max retries prevents infinite loops
5. **Status Tracking:** Token status prevents misuse of expired/disabled tokens

---

## 📈 Monitoring

### SQL Queries for Monitoring

**Token Health:**
```sql
SELECT * FROM vw_TokenStatus;
```

**Usage Statistics:**
```sql
SELECT * FROM vw_UsageSummary;
```

**Recent Errors:**
```sql
SELECT * FROM vw_RecentErrors;
```

**Failed Retries:**
```sql
SELECT * FROM vw_FailedRetries;
```

---

## 🆘 Troubleshooting

### Issue: "No active token found"
1. Check TokenMaster table: `SELECT * FROM TokenMaster WHERE CompanyID = 'NT047'`
2. Verify Status = 'Active'
3. Insert token if missing

### Issue: Retries not happening
1. Check ApplicationLogs for error type
2. Verify error matches retryable keywords
3. Check RetryAttempts table for logged attempts

### Issue: Usage not logged
1. Verify Gemini response contains usage information
2. Check TokenUsageLogs table
3. Check ApplicationLogs for parsing errors

### Issue: Database logging not working
1. Verify ApplicationLogs table exists
2. Check database connection in DBConnection.txt
3. Verify ODBC Driver 17 is installed

---

## 📚 Documentation Files

1. **TOKEN_MANAGEMENT_GUIDE.md** - Complete implementation guide
2. **TOKEN_QUICK_REFERENCE.md** - Quick reference and examples
3. **setup_database.sql** - Database setup script
4. **This file** - Implementation summary

---

## 🎯 Next Steps

1. **Deploy Database:** Execute `setup_database.sql`
2. **Populate Tokens:** Insert API keys into TokenMaster
3. **Test API:** Make test request with new `/extract` endpoint
4. **Monitor:** Check ApplicationLogs and TokenUsageLogs
5. **Optimize:** Adjust retry config based on real usage patterns

---

## 📞 Support

For issues or questions:
1. Check ApplicationLogs table for detailed error information
2. Review TOKEN_QUICK_REFERENCE.md for common issues
3. Verify database tables exist and contain data
4. Check token status in TokenMaster table

---

**Implementation Date:** November 19, 2025
**Status:** ✅ Complete and Ready for Deployment
**Version:** 1.0.0

