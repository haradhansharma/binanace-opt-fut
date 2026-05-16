"""
Logging configuration for the Binance Signal Generator.

This module provides a centralized logging configuration that supports:
- JSON structured logging
- File and console handlers
- Sensitive data masking
- Configurable log levels
"""

import logging
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any, Set
from pathlib import Path
from logging.handlers import RotatingFileHandler


# Sensitive keys to mask in logs
SENSITIVE_KEYS: Set[str] = {
    "api_key",
    "api_secret", 
    "secret",
    "password",
    "token",
    "authorization",
    "credential",
}


def mask_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively mask sensitive values in a dictionary.
    
    Args:
        data: Dictionary to mask
        
    Returns:
        Dictionary with sensitive values replaced by '***MASKED***'
    """
    if not isinstance(data, dict):
        return data
    
    masked = {}
    for key, value in data.items():
        lower_key = key.lower()
        
        # Check if this key should be masked
        if any(sensitive in lower_key for sensitive in SENSITIVE_KEYS):
            masked[key] = "***MASKED***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive(value)
        elif isinstance(value, list):
            masked[key] = [
                mask_sensitive(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            masked[key] = value
    
    return masked


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Outputs log records as JSON objects with consistent structure:
    {
        "timestamp": "2024-01-15T14:30:00Z",
        "level": "INFO",
        "logger": "binance_signal_generator.data.fetcher",
        "message": "Fetching options chain for BTCUSDT",
        "extra": {...}
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "data") and record.data:
            log_data["data"] = mask_sensitive(record.data)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add source location for debug level
        if record.levelno == logging.DEBUG:
            log_data["source"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }
        
        return json.dumps(log_data)


class StandardFormatter(logging.Formatter):
    """
    Standard text formatter for console output.
    
    Format: [TIMESTAMP] LEVEL - LOGGER - MESSAGE
    """
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        base = f"[{timestamp}] {record.levelname:8s} - {record.name} - {record.getMessage()}"
        
        if hasattr(record, "data") and record.data:
            masked_data = mask_sensitive(record.data)
            base += f" | {json.dumps(masked_data)}"
        
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        
        return base


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_size_mb: int = 10,
    backup_count: int = 5,
    console_enabled: bool = False,
    json_format: bool = True,
    mask_sensitive_data: bool = True,
) -> logging.Logger:
    """
    Set up logging configuration for the signal generator.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        max_size_mb: Maximum size of each log file in MB
        backup_count: Number of backup files to keep
        console_enabled: Whether to output to console
        json_format: Whether to use JSON format (True) or text format (False)
        mask_sensitive_data: Whether to mask sensitive data in logs
        
    Returns:
        Configured logger for the signal generator package
    """
    # Get the root logger for the package
    logger = logging.getLogger("binance_signal_generator")
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Set the log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Choose formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = StandardFormatter()
    
    # File handler (always enabled if path provided)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Console handler (optional)
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(log_level)
        # Console always uses standard format for readability
        console_handler.setFormatter(StandardFormatter())
        logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.
    
    Args:
        name: Module name (typically __name__)
        
    Returns:
        Logger instance
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Starting data fetch", extra={"data": {"symbol": "BTCUSDT"}})
    """
    return logging.getLogger(name)


class LogAdapter:
    """
    Adapter for adding context to log messages.
    
    Usage:
        logger = get_logger(__name__)
        adapter = LogAdapter(logger, {"symbol": "BTCUSDT"})
        adapter.info("Fetching data")  # Includes symbol in log
    """
    
    def __init__(self, logger: logging.Logger, context: Dict[str, Any]):
        self.logger = logger
        self.context = context
    
    def _log(self, level: int, message: str, **kwargs):
        """Log with context."""
        data = {**self.context, **kwargs.pop("data", {})}
        self.logger.log(level, message, extra={"data": data}, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        data = {**self.context, **kwargs.pop("data", {})}
        self.logger.exception(message, extra={"data": data}, **kwargs)


# Module-level logger for convenience
logger = get_logger(__name__)
