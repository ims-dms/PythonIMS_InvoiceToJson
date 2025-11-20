import json
import pyodbc
import logging
from encryption_util import decrypt_if_encrypted

logger = logging.getLogger(__name__)

# Mapping of possible keys to standard keys
KEY_MAPPING = {
    "server": ["data source", "server", "data_source"],
    "database": ["initial catalog", "database", "initial_catalog", "inital"],
    "user": ["user", "user id", "userid", "user_id", "id", "uid", "userId", "User_Id", "UserId"],
    "password": ["password", "pwd", "pass", "PASSWORD", "Password"]
}

def normalize_keys(config: dict) -> dict:
    normalized = {}
    lower_config = {k.lower(): v for k, v in config.items()}
    for std_key, aliases in KEY_MAPPING.items():
        for alias in aliases:
            if alias.lower() in lower_config:
                normalized[std_key] = lower_config[alias.lower()]
                break
    return normalized

def get_connection(connection_params: dict = None):
    if connection_params is None:
        # Read connection details from DBConnection.txt
        with open('DBConnection.txt', 'r') as f:
            # Read all lines and skip comment lines (starting with #)
            lines = f.readlines()
            json_content = ''.join(line for line in lines if not line.strip().startswith('#'))
            config = json.loads(json_content.strip())
    else:
        config = connection_params

    normalized_config = normalize_keys(config)

    server = normalized_config.get("server")
    database = normalized_config.get("database")
    user = normalized_config.get("user")
    password = normalized_config.get("password")
    password = decrypt_if_encrypted(password)

    # Build connection string for SQL Server using pyodbc
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password}"
    )

    try:
        connection = pyodbc.connect(conn_str)
        return connection
    except Exception as e:
        # Use print instead of logger to avoid infinite recursion with db_logger
        print(f"ERROR: Database connection failed - {e}", flush=True)
        raise

def create_token_tables(connection=None):
    """Create TokenMaster, TokenUsageLogs, and TokenUsageSummary tables if they don't exist."""
    if connection is None:
        connection = get_connection()
    
    cursor = connection.cursor()
    
    try:
        # Create TokenMaster table
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TokenMaster' AND xtype='U')
            CREATE TABLE [docUpload].TokenMaster (
                TokenID INT IDENTITY(1,1) PRIMARY KEY,
                CompanyID VARCHAR(50),
                CompanyName VARCHAR(200),
                ApiKey VARCHAR(500),
                Provider VARCHAR(100),
                TotalTokenLimit INT,
                Status VARCHAR(50),
                CreatedAt DATETIME DEFAULT GETDATE()
            )
        """)
        connection.commit()
        
        # Create TokenUsageLogs table
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TokenUsageLogs' AND xtype='U')
            CREATE TABLE [docUpload].TokenUsageLogs (
                UsageID INT IDENTITY(1,1) PRIMARY KEY,
                TokenID INT FOREIGN KEY REFERENCES [docUpload].TokenMaster(TokenID),
                Branch VARCHAR(50),
                RequestedBy VARCHAR(100),
                InputTokens INT,
                OutputTokens INT,
                TextPromptTokens INT,
                ImagePromptTokens INT,
                TextCandidatesTokens INT,
                TotalTokensUsed INT,
                RequestCount INT,
                LoggedAt DATETIME DEFAULT GETDATE()
            )
        """)
        connection.commit()
        
        # Create TokenUsageSummary table
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TokenUsageSummary' AND xtype='U')
            CREATE TABLE [docUpload].TokenUsageSummary (
                SummaryID INT IDENTITY(1,1) PRIMARY KEY,
                TokenID INT FOREIGN KEY REFERENCES [docUpload].TokenMaster(TokenID),
                TotalUsedTokens INT DEFAULT 0,
                TotalRemainingTokens INT,
                Threshold INT DEFAULT 3000,
                LastUpdated DATETIME DEFAULT GETDATE()
            )
        """)
        connection.commit()
        
    except Exception as e:
        logger.debug(f"Table creation info: {e}")
    finally:
        cursor.close()

if __name__ == "__main__":
    # Test the connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    print("SQL Server version:", row[0])
    conn.close()

