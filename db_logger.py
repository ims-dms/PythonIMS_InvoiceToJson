"""
Database Logging Module
Handles all application logging directly to the database
"""
import logging
import logging.handlers
from datetime import datetime
from db_connection import get_connection


class DatabaseLogHandler(logging.Handler):
    """Custom logging handler that writes logs to database"""
    
    TABLE_NAME = 'ApplicationLogs'
    
    def __init__(self, connection=None):
        """
        Initialize database log handler.
        
        Args:
            connection: Database connection (creates new if None)
        """
        super().__init__()
        self.connection = connection
        self._in_emit = False  # Recursion guard
        self.ensure_table_exists()
    
    def ensure_table_exists(self):
        """Create ApplicationLogs table if it doesn't exist"""
        try:
            conn = self.connection or get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.TABLE_NAME}' AND xtype='U')
                CREATE TABLE {self.TABLE_NAME} (
                    LogID INT IDENTITY(1,1) PRIMARY KEY,
                    Timestamp DATETIME DEFAULT GETDATE(),
                    LogLevel VARCHAR(20),
                    Logger VARCHAR(255),
                    Message VARCHAR(MAX),
                    Exception VARCHAR(MAX),
                    Module VARCHAR(255),
                    FunctionName VARCHAR(255),
                    LineNumber INT
                )
            """)
            conn.commit()
            cursor.close()
        except Exception as e:
            # Log to console only if table creation fails
            logging.getLogger(__name__).debug(f"Table creation info: {e}")
    
    def emit(self, record: logging.LogRecord):
        """
        Emit a log record to the database.
        
        Args:
            record: LogRecord to emit
        """
        # Prevent recursion - if we're already in emit, skip
        if self._in_emit:
            return
        
        # Skip logging for db_connection module to prevent infinite recursion
        if record.module == 'db_connection':
            return
        
        try:
            self._in_emit = True
            conn = self.connection or get_connection()
            cursor = conn.cursor()
            
            log_level = record.levelname
            logger_name = record.name
            message = self.format(record)
            exception = ""
            
            if record.exc_info:
                import traceback
                exception = ''.join(traceback.format_exception(*record.exc_info))
            
            module = record.module
            func_name = record.funcName
            line_no = record.lineno
            
            cursor.execute(f"""
                INSERT INTO {self.TABLE_NAME}
                (LogLevel, Logger, Message, Exception, Module, FunctionName, LineNumber)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (log_level, logger_name, message, exception, module, func_name, line_no))
            
            conn.commit()
            cursor.close()
        
        except Exception as e:
            # Silently fail to prevent recursion - don't call handleError
            pass
        finally:
            self._in_emit = False


class ApplicationLogger:
    """Centralized logging configuration"""
    
    _instance = None
    _handlers_configured = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ApplicationLogger, cls).__new__(cls)
        return cls._instance
    
    @staticmethod
    def configure(connection=None, log_level=logging.INFO, console: bool = False):
        """
        Configure application-wide logging to database. By default this will NOT add
        a console StreamHandler to avoid verbose console output; pass `console=True`
        to enable console logging (useful for local development).

        Args:
            connection: Database connection (optional)
            log_level: Logging level (default: INFO)
            console: Whether to add a console StreamHandler (default: False)
        """
        if ApplicationLogger._handlers_configured:
            return

        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Remove existing handlers to avoid duplication
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Create formatter for database handler
        db_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Add database handler
        try:
            db_handler = DatabaseLogHandler(connection)
            db_handler.setLevel(logging.DEBUG)
            db_handler.setFormatter(db_formatter)
            root_logger.addHandler(db_handler)
        except Exception as e:
            # If DB logging fails, keep going but do not add a noisy console handler by default
            logging.warning(f"Failed to initialize database logging: {e}")

        # Optionally add a console handler (opt-in). When running in production or
        # long-lived processes, disabling console logging reduces console noise
        # and can prevent excessive memory usage associated with retained stream buffers.
        if console:
            console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # Reduce verbosity for commonly noisy loggers to avoid excess logging
        noisy_loggers = [
            'uvicorn', 'uvicorn.error', 'uvicorn.access',
            'httpx', 'menu_cache', 'fuzzy_matcher', 'token_manager', 'db_logger'
        ]
        for lname in noisy_loggers:
            try:
                logging.getLogger(lname).setLevel(logging.WARNING)
            except Exception:
                pass

        ApplicationLogger._handlers_configured = True
    
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """
        Get a logger instance.
        
        Args:
            name: Logger name (typically __name__)
            
        Returns:
            logging.Logger: Logger instance
        """
        return logging.getLogger(name)


def log_retry_attempts(retry_log: list, token_id: int = None, company_id: str = None):
    """
    Log retry attempts to database.
    
    Args:
        retry_log: List of retry attempts from RetryPolicy
        token_id: Token ID (optional)
        company_id: Company ID (optional)
    """
    logger = ApplicationLogger.get_logger(__name__)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Create retry logs table if not exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='RetryAttempts' AND xtype='U')
            CREATE TABLE RetryAttempts (
                RetryID INT IDENTITY(1,1) PRIMARY KEY,
                TokenID INT,
                CompanyID VARCHAR(50),
                Attempt INT,
                ErrorMessage VARCHAR(MAX),
                IsRetryable BIT,
                Timestamp DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()
        
        # Log each retry attempt
        for log_entry in retry_log:
            cursor.execute("""
                INSERT INTO RetryAttempts
                (TokenID, CompanyID, Attempt, ErrorMessage, IsRetryable)
                VALUES (?, ?, ?, ?, ?)
            """, (
                token_id,
                company_id,
                log_entry.get('attempt'),
                log_entry.get('error'),
                1 if log_entry.get('retryable') else 0
            ))
        
        conn.commit()
        cursor.close()
        
        logger.info(f"Logged {len(retry_log)} retry attempts")
    
    except Exception as e:
        logger.error(f"Failed to log retry attempts: {e}")
