# Deployment Checklist - Token Management System

## Pre-Deployment Review

### ✅ Code Changes
- [x] `api.py` - Updated with token management and retry logic
- [x] `db_connection.py` - Added table creation functions
- [x] `token_manager.py` - New token management module
- [x] `retry_policy.py` - New retry mechanism module
- [x] `db_logger.py` - New database logging module
- [x] `requirements.txt` - Updated with dependencies
- [x] No breaking changes to existing functionality
- [x] All error handling implemented
- [x] Database logging configured

### ✅ Database Setup
- [x] `setup_database.sql` - Complete database setup script
- [x] Tables created: TokenMaster, TokenUsageLogs, TokenUsageSummary, ApplicationLogs, RetryAttempts
- [x] Indexes added for performance
- [x] Views created for monitoring
- [x] Script handles idempotent table creation

### ✅ Documentation
- [x] `TOKEN_MANAGEMENT_GUIDE.md` - Comprehensive implementation guide
- [x] `TOKEN_QUICK_REFERENCE.md` - Quick reference and troubleshooting
- [x] `API_USAGE_EXAMPLES.md` - API usage and integration examples
- [x] `IMPLEMENTATION_SUMMARY.md` - High-level summary
- [x] `DEPLOYMENT_CHECKLIST.md` - This file

---

## Step-by-Step Deployment Guide

### Phase 1: Pre-Deployment Preparation (Day 1)

#### 1.1 Backup Current System
- [ ] Backup current `api.py`
  ```bash
  cp api.py api.py.backup.$(date +%Y%m%d)
  ```
- [ ] Backup `appSetting.txt`
  ```bash
  cp appSetting.txt appSetting.txt.backup
  ```
- [ ] Backup current database
  ```sql
  BACKUP DATABASE YourDatabaseName 
  TO DISK = 'C:\Backups\ocr_backup_20251119.bak'
  ```

#### 1.2 Code Review
- [ ] Review `api.py` changes
- [ ] Review `token_manager.py` implementation
- [ ] Review `retry_policy.py` logic
- [ ] Review error messages
- [ ] Verify imports and dependencies

#### 1.3 Environment Preparation
- [ ] Verify Python version (3.7+)
- [ ] Verify pip packages available
- [ ] Check disk space for database
- [ ] Verify database connectivity
- [ ] Test `pyodbc` connection

---

### Phase 2: Development Environment Testing (Day 1)

#### 2.1 Install Dependencies
- [ ] Update pip: `pip install --upgrade pip`
- [ ] Install new dependencies:
  ```bash
  pip install tenacity
  ```
- [ ] Or reinstall all:
  ```bash
  pip install -r requirements.txt
  ```
- [ ] Verify installations:
  ```bash
  python -c "import tenacity; print('OK')"
  ```

#### 2.2 Database Setup
- [ ] Run setup script:
  ```sql
  -- In SQL Server Management Studio:
  -- Open setup_database.sql and execute
  ```
- [ ] Verify tables created:
  ```sql
  SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
  WHERE TABLE_SCHEMA = 'dbo'
  ```
- [ ] Verify views created:
  ```sql
  SELECT * FROM vw_TokenStatus
  ```

#### 2.3 Insert Test Data
- [ ] Insert test token:
  ```sql
  INSERT INTO TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
  VALUES ('NT047', 'RUBI TRADERS Pvt ltd', 'AIzaSyB7gYAy_0OzJp22NygC0i_nxeSzVDFefnM', 'Gemini', 100000, 'Active');
  ```
- [ ] Verify token inserted:
  ```sql
  SELECT * FROM TokenMaster WHERE CompanyID = 'NT047'
  ```

#### 2.4 Code Testing
- [ ] Start API service:
  ```bash
  python -m uvicorn api:app --reload
  ```
- [ ] Check startup logs:
  ```
  INFO: Uvicorn running on http://0.0.0.0:8000
  ```
- [ ] Test health check:
  ```bash
  curl http://localhost:8000/
  ```
- [ ] Verify tables created (check startup event):
  ```sql
  SELECT * FROM TokenMaster
  SELECT * FROM ApplicationLogs ORDER BY Timestamp DESC
  ```

#### 2.5 API Testing
- [ ] Test valid invoice processing:
  ```bash
  curl -X POST http://localhost:8000/extract \
    -F "file=@test_invoice.pdf" \
    -F "companyID=NT047" \
    -F "username=tester" \
    -F "branch=TEST"
  ```
- [ ] Verify response structure
- [ ] Check token usage logged:
  ```sql
  SELECT * FROM TokenUsageLogs ORDER BY LoggedAt DESC
  ```
- [ ] Check ApplicationLogs:
  ```sql
  SELECT * FROM ApplicationLogs ORDER BY Timestamp DESC LIMIT 20
  ```

#### 2.6 Error Handling Testing
- [ ] Test with invalid file
  - Expected: Error with no retry
- [ ] Test with expired token status
  - Expected: "Token expired" message
  - First: `UPDATE TokenMaster SET Status = 'Expired' WHERE TokenID = 1`
- [ ] Test with no token
  - Expected: "No active token found" message
- [ ] Test token status recovery:
  ```sql
  UPDATE TokenMaster SET Status = 'Active' WHERE TokenID = 1
  ```

#### 2.7 Retry Logic Testing
- [ ] Mock Gemini timeout (advanced)
  - Could use proxy/VCR to simulate timeouts
- [ ] Verify retry logged:
  ```sql
  SELECT * FROM RetryAttempts ORDER BY Timestamp DESC
  ```

---

### Phase 3: Staging Environment Testing (Day 2)

#### 3.1 Deploy to Staging
- [ ] Copy code to staging server
- [ ] Update `DBConnection.txt` for staging database
- [ ] Run database setup script on staging DB
- [ ] Insert test tokens for staging
- [ ] Start API service

#### 3.2 Staging Validation
- [ ] Test API endpoints
- [ ] Test token retrieval
- [ ] Test error handling
- [ ] Monitor ApplicationLogs
- [ ] Check token usage logging
- [ ] Verify retry logic

#### 3.3 Load Testing (Optional)
- [ ] Test with multiple concurrent requests
- [ ] Monitor token selection (should be random)
- [ ] Monitor database performance
- [ ] Check for any deadlocks

---

### Phase 4: Production Deployment (Day 3)

#### 4.1 Production Preparation
- [ ] Final backup of production database
- [ ] Review production token list
- [ ] Prepare production API keys
- [ ] Notify stakeholders
- [ ] Schedule maintenance window if needed

#### 4.2 Deploy Code
- [ ] Copy new code files to production:
  - [ ] `api.py`
  - [ ] `token_manager.py`
  - [ ] `retry_policy.py`
  - [ ] `db_logger.py`
  - [ ] Updated `db_connection.py`
  - [ ] Updated `requirements.txt`
- [ ] Backup old code

#### 4.3 Deploy Database
- [ ] Run `setup_database.sql` on production:
  - [ ] Create tables (if not exist)
  - [ ] Create indexes
  - [ ] Create views
- [ ] Verify tables exist:
  ```sql
  SELECT COUNT(*) as TableCount FROM INFORMATION_SCHEMA.TABLES 
  WHERE TABLE_SCHEMA = 'dbo' 
  AND TABLE_NAME IN ('TokenMaster', 'TokenUsageLogs', 'TokenUsageSummary', 'ApplicationLogs', 'RetryAttempts')
  ```

#### 4.4 Populate Production Tokens
- [ ] Insert all company tokens:
  ```sql
  INSERT INTO TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
  VALUES ('NT047', 'RUBI TRADERS Pvt ltd', '[YOUR_API_KEY]', 'Gemini', 100000, 'Active');
  ```
- [ ] Insert additional tokens if available:
  - [ ] Backup tokens (same company, different key)
  - [ ] Tokens for other companies
- [ ] Verify all tokens inserted:
  ```sql
  SELECT * FROM TokenMaster WHERE Status = 'Active'
  ```

#### 4.5 Install Dependencies
- [ ] Update pip on production server
- [ ] Install new dependencies:
  ```bash
  pip install -r requirements.txt
  ```

#### 4.6 Start API Service
- [ ] Stop current API service
- [ ] Start new API service
- [ ] Verify startup successful:
  ```bash
  curl http://localhost:8000/
  ```
- [ ] Check ApplicationLogs for startup messages:
  ```sql
  SELECT * FROM ApplicationLogs ORDER BY Timestamp DESC LIMIT 10
  ```

#### 4.7 Production Validation
- [ ] Test health check endpoint
- [ ] Test with real invoice file
- [ ] Verify token was selected from database
- [ ] Check TokenUsageLogs for entry
- [ ] Check ApplicationLogs for processing logs
- [ ] Monitor error rates

#### 4.8 Rollback Plan (If Issues)
- [ ] Stop API service
- [ ] Restore old `api.py`
- [ ] Restore old `db_connection.py`
- [ ] Remove new modules (`token_manager.py`, `retry_policy.py`, `db_logger.py`)
- [ ] Start old API service
- [ ] Verify system operational
- [ ] Investigate issues

---

### Phase 5: Post-Deployment Monitoring (Week 1)

#### 5.1 Daily Monitoring (First 3 Days)
- [ ] Monitor ApplicationLogs for errors
  ```sql
  SELECT LogLevel, COUNT(*) as Count FROM ApplicationLogs 
  GROUP BY LogLevel
  ```
- [ ] Monitor token usage:
  ```sql
  SELECT * FROM vw_TokenStatus
  ```
- [ ] Check for API errors:
  ```bash
  curl http://localhost:8000/cache/status
  ```
- [ ] Monitor server resources (CPU, Memory, Disk)

#### 5.2 Weekly Review (First Week)
- [ ] Analyze usage patterns:
  ```sql
  SELECT * FROM vw_UsageSummary
  ```
- [ ] Review retry attempts:
  ```sql
  SELECT COUNT(*) as TotalRetries FROM RetryAttempts
  ```
- [ ] Check error logs:
  ```sql
  SELECT * FROM vw_RecentErrors
  ```
- [ ] Verify no data anomalies
- [ ] Get user feedback

#### 5.3 Performance Tuning (As Needed)
- [ ] Add indexes if needed
- [ ] Archive old logs if space issues
- [ ] Adjust retry configuration if needed
- [ ] Update token limits if needed

---

## Verification Checklist

### Before Going Live

#### Code Verification
- [ ] All files present and correct
- [ ] No syntax errors
- [ ] Imports working
- [ ] Dependencies installed
- [ ] No breaking changes to existing functionality

#### Database Verification
- [ ] All tables created
- [ ] All indexes created
- [ ] All views created
- [ ] Test data inserted
- [ ] Database connection working
- [ ] Proper permissions set

#### API Verification
- [ ] API starts without errors
- [ ] Health check responds
- [ ] Token retrieval works
- [ ] Usage logging works
- [ ] Error handling works
- [ ] Retry logic works
- [ ] Database logging works

#### Documentation Verification
- [ ] All guides present
- [ ] All examples current
- [ ] No broken links
- [ ] SQL scripts tested
- [ ] Configuration documented

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Stop API service
systemctl stop ocr-api

# 2. Restore old code
cp api.py.backup api.py
cp db_connection.py.backup db_connection.py
rm token_manager.py
rm retry_policy.py
rm db_logger.py

# 3. Restore old dependencies (optional)
pip install -r requirements.txt.old

# 4. Restart API
systemctl start ocr-api

# 5. Verify
curl http://localhost:8000/

# 6. Restore database (if needed)
RESTORE DATABASE YourDatabaseName
FROM DISK = 'C:\Backups\ocr_backup_20251119.bak'
```

---

## Support Contacts

### During Deployment
- **Database Issues:** Database Administrator
- **API Issues:** DevOps / System Administrator
- **Code Issues:** Development Team
- **User Issues:** Customer Support

### Post-Deployment
- **Monitoring:** DevOps Team
- **Issues:** Create GitHub Issue
- **Questions:** Review documentation or contact team

---

## Sign-Off

### Pre-Deployment Sign-Off
- [ ] Development Lead: _________________ Date: _______
- [ ] QA Lead: _________________ Date: _______
- [ ] DevOps/System Admin: _________________ Date: _______

### Deployment Sign-Off
- [ ] Deployed by: _________________ Date: _______
- [ ] Verified by: _________________ Date: _______
- [ ] Go-live approved: _________________ Date: _______

### Post-Deployment Sign-Off
- [ ] Monitoring established: _________________ Date: _______
- [ ] Production stable: _________________ Date: _______
- [ ] Handoff complete: _________________ Date: _______

---

## Appendix: Quick Commands

### Start API
```bash
cd /path/to/FinalPython
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

### Run Tests
```bash
python -m pytest tests/ -v
```

### Check Logs
```sql
SELECT TOP 100 * FROM ApplicationLogs ORDER BY Timestamp DESC
SELECT TOP 50 * FROM TokenUsageLogs ORDER BY LoggedAt DESC
SELECT TOP 50 * FROM RetryAttempts ORDER BY Timestamp DESC
```

### Reset Database (Testing Only)
```sql
DELETE FROM RetryAttempts
DELETE FROM TokenUsageLogs
DELETE FROM TokenUsageSummary
DELETE FROM ApplicationLogs
DELETE FROM TokenMaster
```

### Monitor Service
```bash
# On Linux/Mac
watch -n 1 'curl -s http://localhost:8000/ | jq .'

# On Windows
powershell -Command 'while($true) { Invoke-RestMethod http://localhost:8000/ | ConvertTo-Json; Start-Sleep 1 }'
```

---

**Deployment Checklist Version:** 1.0
**Last Updated:** November 19, 2025
**Status:** Ready for Deployment ✅

