"""
Utility helper functions.
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """Convert millisecond timestamp to datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def datetime_to_timestamp(dt: datetime) -> int:
    """Convert datetime to millisecond timestamp."""
    return int(dt.timestamp() * 1000)


def format_iso(dt: datetime) -> str:
    """Format datetime as ISO 8601 string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(iso_string: str) -> datetime:
    """Parse ISO 8601 string to datetime."""
    return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))


def generate_signal_id(symbol: str, direction: str, timestamp: Optional[datetime] = None) -> str:
    """
    Generate a unique signal ID.

    Format: SIG_YYYYMMDD_HHMM_SYMBOL_DIRECTION
    """
    ts = timestamp or utc_now()
    ts_str = ts.strftime("%Y%m%d_%H%M")
    return f"SIG_{ts_str}_{symbol}_{direction}"


def generate_execution_id(timestamp: Optional[datetime] = None) -> str:
    """
    Generate a unique execution ID.

    Format: EXEC_YYYYMMDD_HHMMSS
    """
    ts = timestamp or utc_now()
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    return f"EXEC_{ts_str}"
