"""
Retry Mechanism Module
Implements fallback and retry logic similar to Polly for Python
"""
import asyncio
import logging
import random
import time
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior"""
    
    def __init__(self, 
                 max_retries: int = 3,
                 initial_delay: float = 1.0,
                 max_delay: float = 30.0,
                 backoff_multiplier: float = 2.0,
                 jitter: bool = True):
        """
        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds before first retry
            max_delay: Maximum delay in seconds between retries
            backoff_multiplier: Multiplier for exponential backoff
            jitter: Whether to add random jitter to delay
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter


class RetryPolicy:
    """Handles retry logic with exponential backoff"""
    
    def __init__(self, config: RetryConfig = None):
        """
        Args:
            config: RetryConfig object (uses defaults if None)
        """
        self.config = config or RetryConfig()
        self.retry_count = 0
        self.retry_log = []
    
    def is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.
        
        Non-retryable errors:
        - ValueError (invalid input)
        - FileNotFoundError
        
        Retryable errors:
        - Connection errors
        - Timeout errors
        - Server errors (5xx)
        - Rate limit errors
        
        Args:
            error: The exception to check
            
        Returns:
            bool: True if error is retryable
        """
        error_str = str(error).lower()
        
        # Non-retryable errors
        non_retryable_keywords = [
            'invalid file',
            'not an invoice',
            'unsupported',
            'malformed',
            'invalid format'
        ]
        
        for keyword in non_retryable_keywords:
            if keyword in error_str:
                return False
        
        # Retryable errors
        retryable_keywords = [
            'connection',
            'timeout',
            'temporarily',
            'exceed',
            'rate limit',
            'quota',
            'service unavailable',
            'internal server error',
            'bad gateway',
            '502', '503', '504',
            'try again'
        ]
        
        for keyword in retryable_keywords:
            if keyword in error_str:
                return True
        
        # Default: retry on most errors except validation errors
        return not isinstance(error, (ValueError, FileNotFoundError))
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for next retry using exponential backoff with optional jitter.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            float: Delay in seconds
        """
        delay = self.config.initial_delay * (self.config.backoff_multiplier ** attempt)
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            # Add random jitter: 0 to 25% of delay
            jitter = random.uniform(0, delay * 0.25)
            delay += jitter
        
        return delay
    
    async def execute_with_retry(self, 
                                  func: Callable, 
                                  *args, 
                                  **kwargs) -> Any:
        """
        Execute an async function with retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Any: Result from func
            
        Raises:
            Exception: The last exception if all retries fail
        """
        self.retry_count = 0
        self.retry_log = []
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt}/{self.config.max_retries}")
                
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"Success after {attempt} retries")
                
                return result
            
            except Exception as e:
                last_error = e
                error_msg = str(e)
                is_retryable = self.is_retryable_error(e)
                
                log_entry = {
                    'attempt': attempt + 1,
                    'error': error_msg,
                    'retryable': is_retryable,
                    'timestamp': time.time()
                }
                self.retry_log.append(log_entry)
                
                logger.warning(f"Attempt {attempt + 1} failed: {error_msg}. Retryable: {is_retryable}")
                
                if not is_retryable:
                    logger.error(f"Non-retryable error encountered: {error_msg}")
                    raise
                
                if attempt < self.config.max_retries:
                    delay = self.calculate_delay(attempt)
                    logger.info(f"Waiting {delay:.2f}s before retry...")
                    await asyncio.sleep(delay)
                    self.retry_count = attempt + 1
        
        # All retries exhausted
        logger.error(f"All {self.config.max_retries + 1} attempts failed")
        raise last_error
    
    def execute_with_retry_sync(self, 
                                 func: Callable, 
                                 *args, 
                                 **kwargs) -> Any:
        """
        Execute a sync function with retry logic.
        
        Args:
            func: Sync function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Any: Result from func
            
        Raises:
            Exception: The last exception if all retries fail
        """
        self.retry_count = 0
        self.retry_log = []
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt}/{self.config.max_retries}")
                
                result = func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"Success after {attempt} retries")
                
                return result
            
            except Exception as e:
                last_error = e
                error_msg = str(e)
                is_retryable = self.is_retryable_error(e)
                
                log_entry = {
                    'attempt': attempt + 1,
                    'error': error_msg,
                    'retryable': is_retryable,
                    'timestamp': time.time()
                }
                self.retry_log.append(log_entry)
                
                logger.warning(f"Attempt {attempt + 1} failed: {error_msg}. Retryable: {is_retryable}")
                
                if not is_retryable:
                    logger.error(f"Non-retryable error encountered: {error_msg}")
                    raise
                
                if attempt < self.config.max_retries:
                    delay = self.calculate_delay(attempt)
                    logger.info(f"Waiting {delay:.2f}s before retry...")
                    time.sleep(delay)
                    self.retry_count = attempt + 1
        
        # All retries exhausted
        logger.error(f"All {self.config.max_retries + 1} attempts failed")
        raise last_error
    
    def get_retry_log(self) -> list:
        """
        Get log of all retry attempts.
        
        Returns:
            list: List of retry log entries
        """
        return self.retry_log
