-- ============================================================================
-- Token Management System - Database Setup Script
-- Execute this script to initialize all token management tables
-- ============================================================================

-- ============================================================================
-- 1. TokenMaster Table - Stores API tokens for each company
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TokenMaster' AND xtype='U')
CREATE TABLE [docUpload].TokenMaster (
    TokenID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID VARCHAR(50) NOT NULL,
    CompanyName VARCHAR(200),
    ApiKey VARCHAR(500) NOT NULL,
    Provider VARCHAR(100) NOT NULL,          -- Gemini / OpenAI / etc
    TotalTokenLimit INT DEFAULT 100000,      -- Internal limit you set
    Status VARCHAR(50) DEFAULT 'Active',     -- Active / Expired / Exceeded / Disabled / BelowThreshold
    CreatedAt DATETIME DEFAULT GETDATE(),
    CONSTRAINT idx_company_token UNIQUE (CompanyID, TokenID)
);

-- Add index for faster lookups
CREATE INDEX idx_tokenmaster_company_status ON [docUpload].TokenMaster(CompanyID, Status);
CREATE INDEX idx_tokenmaster_created ON [docUpload].TokenMaster(CreatedAt DESC);

-- ============================================================================
-- 2. TokenUsageLogs Table - Records every token usage
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TokenUsageLogs' AND xtype='U')
CREATE TABLE [docUpload].TokenUsageLogs (
    UsageID INT IDENTITY(1,1) PRIMARY KEY,
    TokenID INT NOT NULL FOREIGN KEY REFERENCES [docUpload].TokenMaster(TokenID),
    Branch VARCHAR(50) DEFAULT 'Default',      -- Which branch/division used the token
    RequestedBy VARCHAR(100) DEFAULT 'System', -- Username who made the request
    InputTokens INT DEFAULT 0,
    OutputTokens INT DEFAULT 0,
    TextPromptTokens INT DEFAULT 0,
    ImagePromptTokens INT DEFAULT 0,
    TextCandidatesTokens INT DEFAULT 0,
    TotalTokensUsed INT DEFAULT 0,
    RequestCount INT DEFAULT 1,
    LoggedAt DATETIME DEFAULT GETDATE()
);

-- Add indexes for performance
CREATE INDEX idx_usage_tokenid ON [docUpload].TokenUsageLogs(TokenID);
CREATE INDEX idx_usage_loggedat ON [docUpload].TokenUsageLogs(LoggedAt DESC);
CREATE INDEX idx_usage_branch ON [docUpload].TokenUsageLogs(Branch);

-- ============================================================================
-- 3. TokenUsageSummary Table - Aggregated usage data per token
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TokenUsageSummary' AND xtype='U')
CREATE TABLE [docUpload].TokenUsageSummary (
    SummaryID INT IDENTITY(1,1) PRIMARY KEY,
    TokenID INT NOT NULL UNIQUE FOREIGN KEY REFERENCES [docUpload].TokenMaster(TokenID),
    TotalUsedTokens INT DEFAULT 0,            -- Total tokens consumed
    TotalRemainingTokens INT DEFAULT 100000,  -- Tokens left
    Threshold INT DEFAULT 3000,               -- Below this = warning
    LastUpdated DATETIME DEFAULT GETDATE()
);

-- Add index
CREATE INDEX idx_summary_tokenid ON [docUpload].TokenUsageSummary(TokenID);

-- ============================================================================
-- 4. ApplicationLogs Table - All application logs saved to database
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ApplicationLogs' AND xtype='U')
CREATE TABLE ApplicationLogs (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    Timestamp DATETIME DEFAULT GETDATE(),
    LogLevel VARCHAR(20),                     -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    Logger VARCHAR(255),                      -- Module name
    Message VARCHAR(MAX),                     -- Log message
    Exception VARCHAR(MAX),                   -- Stack trace if applicable
    Module VARCHAR(255),                      -- Module name
    FunctionName VARCHAR(255),                -- Function name
    LineNumber INT
);

-- Add indexes
CREATE INDEX idx_logs_timestamp ON ApplicationLogs(Timestamp DESC);
CREATE INDEX idx_logs_level ON ApplicationLogs(LogLevel);
CREATE INDEX idx_logs_logger ON ApplicationLogs(Logger);

-- ============================================================================
-- 5. RetryAttempts Table - Records failed retry attempts
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='RetryAttempts' AND xtype='U')
CREATE TABLE RetryAttempts (
    RetryID INT IDENTITY(1,1) PRIMARY KEY,
    TokenID INT,                              -- Token used (nullable for non-token errors)
    CompanyID VARCHAR(50),                    -- Company that made request
    Attempt INT,                              -- Attempt number
    ErrorMessage VARCHAR(MAX),                -- Error message
    IsRetryable BIT DEFAULT 1,                -- Whether error was retryable
    Timestamp DATETIME DEFAULT GETDATE()
);

-- Add indexes
CREATE INDEX idx_retry_tokenid ON RetryAttempts(TokenID);
CREATE INDEX idx_retry_company ON RetryAttempts(CompanyID);
CREATE INDEX idx_retry_timestamp ON RetryAttempts(Timestamp DESC);

-- ============================================================================
-- 6. Sample Data - Insert test tokens (OPTIONAL - Edit before inserting)
-- ============================================================================

-- Uncomment and edit below to insert test data
/*
-- Sample token for RUBI TRADERS
INSERT INTO [docUpload].TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
VALUES 
(
    'NT047',
    'RUBI TRADERS Pvt ltd',
    'AIzaSyB7gYAy_0OzJp22NygC0i_nxeSzVDFefnM',  -- EDIT: Replace with actual API key
    'Gemini',
    100000,
    'Active'
);

-- Sample token for another company (create backup token)
INSERT INTO TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
VALUES 
(
    'NT047',
    'RUBI TRADERS Pvt ltd',
    'YOUR_BACKUP_API_KEY_HERE',  -- EDIT: Replace with backup API key
    'Gemini',
    100000,
    'Active'
);

-- Initialize summary for tokens
INSERT INTO [docUpload].TokenUsageSummary (TokenID, TotalUsedTokens, TotalRemainingTokens, Threshold)
SELECT TokenID, 0, TotalTokenLimit, 3000
FROM [docUpload].TokenMaster
WHERE TokenID NOT IN (SELECT TokenID FROM [docUpload].TokenUsageSummary);
*/

-- ============================================================================
-- 7. Useful Views and Queries
-- ============================================================================

-- View: Token Status Overview
CREATE OR ALTER VIEW vw_TokenStatus AS
SELECT 
    t.TokenID,
    t.CompanyID,
    t.CompanyName,
    t.Provider,
    t.Status,
    s.TotalUsedTokens,
    s.TotalRemainingTokens,
    s.Threshold,
    CASE 
        WHEN s.TotalRemainingTokens < s.Threshold THEN 'WARNING'
        WHEN s.TotalRemainingTokens <= 0 THEN 'EXCEEDED'
        ELSE 'OK'
    END as HealthStatus,
    t.CreatedAt,
    s.LastUpdated
FROM [docUpload].TokenMaster t
LEFT JOIN [docUpload].TokenUsageSummary s ON t.TokenID = s.TokenID
ORDER BY t.CompanyID, t.CreatedAt DESC;

-- View: Usage Summary by Company
CREATE OR ALTER VIEW vw_UsageSummary AS
SELECT 
    t.CompanyID,
    t.CompanyName,
    COUNT(DISTINCT u.Branch) as Branches,
    COUNT(DISTINCT u.RequestedBy) as Users,
    COUNT(u.UsageID) as TotalRequests,
    SUM(u.TotalTokensUsed) as TotalTokensUsed,
    AVG(u.TotalTokensUsed) as AvgTokensPerRequest,
    MAX(u.LoggedAt) as LastUsed,
    DATEDIFF(DAY, MIN(u.LoggedAt), MAX(u.LoggedAt)) as DaysActive
FROM [docUpload].TokenMaster t
LEFT JOIN [docUpload].TokenUsageLogs u ON t.TokenID = u.TokenID
WHERE t.Status = 'Active'
GROUP BY t.CompanyID, t.CompanyName
ORDER BY TotalTokensUsed DESC;

-- View: Recent Errors
CREATE OR ALTER VIEW vw_RecentErrors AS
SELECT TOP 100
    LogID,
    Timestamp,
    LogLevel,
    Logger,
    Message,
    Module,
    FunctionName,
    LineNumber,
    DATEDIFF(MINUTE, Timestamp, GETDATE()) as MinutesAgo
FROM ApplicationLogs
WHERE LogLevel IN ('ERROR', 'CRITICAL')
ORDER BY Timestamp DESC;

-- View: Failed Retry Attempts
CREATE OR ALTER VIEW vw_FailedRetries AS
SELECT 
    r.RetryID,
    r.TokenID,
    r.CompanyID,
    MAX(r.Attempt) as MaxAttempts,
    COUNT(*) as TotalAttempts,
    CAST(SUM(CASE WHEN r.IsRetryable = 1 THEN 1 ELSE 0 END) as FLOAT) / COUNT(*) * 100 as RetryablePercentage,
    MAX(r.Timestamp) as LastAttempt
FROM RetryAttempts r
GROUP BY r.RetryID, r.TokenID, r.CompanyID
HAVING MAX(r.Attempt) >= 3  -- Only show those that had 3+ attempts
ORDER BY MAX(r.Timestamp) DESC;

-- ============================================================================
-- 8. Cleanup/Maintenance Queries
-- ============================================================================

/*
-- Archive logs older than 90 days
INSERT INTO ApplicationLogs_Archive
SELECT * FROM ApplicationLogs
WHERE Timestamp < DATEADD(DAY, -90, GETDATE());

DELETE FROM ApplicationLogs
WHERE Timestamp < DATEADD(DAY, -90, GETDATE());

-- Reset usage for testing
DELETE FROM [docUpload].TokenUsageLogs;
DELETE FROM [docUpload].TokenUsageSummary;
DELETE FROM RetryAttempts;

-- Update token status
UPDATE [docUpload].TokenMaster SET Status = 'Expired' WHERE TokenID = 1;
UPDATE [docUpload].TokenMaster SET Status = 'Active' WHERE TokenID = 1;

-- Check database size
SELECT 
    TABLE_NAME,
    (CAST(FILEPROPERTY(PARSENAME(TABLE_NAME,1), 'SpaceUsed') AS BIGINT) * 8) / 1024.0 as SizeMB
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
ORDER BY SizeMB DESC;
*/

-- ============================================================================
-- 9. Verify Tables Created
-- ============================================================================
PRINT '=== Database Setup Completed ===';
PRINT '';
PRINT 'Tables Created:';
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME IN 
('TokenMaster', 'TokenUsageLogs', 'TokenUsageSummary', 'ApplicationLogs', 'RetryAttempts')
ORDER BY TABLE_NAME;

PRINT '';
PRINT 'Views Created:';
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS 
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME LIKE 'vw_%'
ORDER BY TABLE_NAME;

PRINT '';
PRINT 'Current Tokens:';
SELECT * FROM vw_TokenStatus;

PRINT '';
PRINT 'Setup complete. Insert your API keys into TokenMaster table.';
