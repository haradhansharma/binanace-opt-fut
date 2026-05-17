"""
Logging configuration for the Binance Signal Generator.

This module provides a centralized logging configuration that supports:
- JSON structured logging
- File and console handlers with rotation
- Sensitive data masking
- Configurable log levels
- Full LoggingConfig integration
"""

import logging
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any, Set, TYPE_CHECKING
from pathlib import Path
from logging.handlers import RotatingFileHandler

if TYPE_CHECKING:
    from binance_signal_generator.config.loader import LoggingConfig


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
    
    def __init__(self, mask_sensitive_data: bool = True):
        """
        Initialize JSON formatter.
        
        Args:
            mask_sensitive_data: Whether to mask sensitive data
        """
        super().__init__()
        self.mask_sensitive_data = mask_sensitive_data
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "data") and record.data:
            if self.mask_sensitive_data:
                log_data["data"] = mask_sensitive(record.data)
            else:
                log_data["data"] = record.data
        
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
    
    def __init__(self, mask_sensitive_data: bool = True, colorize: bool = False):
        """
        Initialize standard formatter.
        
        Args:
            mask_sensitive_data: Whether to mask sensitive data
            colorize: Whether to colorize output with ANSI codes
        """
        super().__init__()
        self.mask_sensitive_data = mask_sensitive_data
        self.colorize = colorize
        
        # ANSI color codes
        self.COLORS = {
            "DEBUG": "\033[36m",     # Cyan
            "INFO": "\033[32m",      # Green
            "WARNING": "\033[33m",   # Yellow
            "ERROR": "\033[31m",     # Red
            "CRITICAL": "\033[35m",  # Magenta
            "RESET": "\033[0m",      # Reset
        }
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        # Colorize level if enabled
        level = record.levelname
        if self.colorize:
            level = f"{self.COLORS.get(record.levelname, '')}{record.levelname:8s}{self.COLORS['RESET']}"
        else:
            level = f"{record.levelname:8s}"
        
        base = f"[{timestamp}] {level} - {record.name} - {record.getMessage()}"
        
        if hasattr(record, "data") and record.data:
            if self.mask_sensitive_data:
                masked_data = mask_sensitive(record.data)
            else:
                masked_data = record.data
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
    console_colorize: bool = False,
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
        console_colorize: Whether to colorize console output
        
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
        formatter = JSONFormatter(mask_sensitive_data=mask_sensitive_data)
    else:
        formatter = StandardFormatter(
            mask_sensitive_data=mask_sensitive_data,
            colorize=console_colorize
        )
    
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
        # Console uses standard format with optional colorization
        console_formatter = StandardFormatter(
            mask_sensitive_data=mask_sensitive_data,
            colorize=console_colorize
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def setup_logging_from_config(config: "LoggingConfig") -> logging.Logger:
    """
    Set up logging from LoggingConfig object.
    
    This is the preferred way to initialize logging when using
    the configuration system.
    
    Args:
        config: LoggingConfig object with all settings
        
    Returns:
        Configured logger for the signal generator package
    """
    return setup_logging(
        level=config.level,
        log_file=config.file_path if config.file_enabled else None,
        max_size_mb=config.file_max_size_mb,
        backup_count=config.file_backup_count,
        console_enabled=config.console_enabled,
        json_format=(config.format == "json"),
        mask_sensitive_data=config.mask_sensitive,
        console_colorize=config.console_colorize,
    )


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
