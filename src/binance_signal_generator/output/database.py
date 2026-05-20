"""
Database storage module for trading signals.

This module provides SQLite-based signal storage with:
- Signal persistence
- History retrieval
- Automatic rotation
- Retention management
- Performance statistics
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

from binance_signal_generator.models import TradingSignal
from binance_signal_generator.config.loader import OutputConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


class SignalDatabase:
    """
    SQLite-based signal storage with rotation and retention.

    Features:
    - Store signals for history/backtesting
    - Query signals by symbol, date, direction
    - Automatic retention-based cleanup
    - Performance tracking

    Attributes:
        config: OutputConfig with database settings
    """

    def __init__(self, config: OutputConfig):
        """
        Initialize signal database.

        Args:
            config: OutputConfig with database settings
        """
        self.config = config
        self.db_path = Path(config.database_path)
        self.retention_weeks = config.database_retention_weeks

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        self._init_schema()

        logger.info(
            "Signal database initialized",
            extra={
                "data": {
                    "path": str(self.db_path),
                    "retention_weeks": self.retention_weeks,
                }
            },
        )

    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    signal_strength TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    risk_reward REAL,
                    whale_metrics TEXT,
                    options_metrics TEXT,
                    futures_metrics TEXT,
                    execution_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_symbol 
                ON signals(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_timestamp 
                ON signals(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_direction 
                ON signals(direction)
            """)

            # Performance tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    direction TEXT NOT NULL,
                    pnl_pct REAL,
                    status TEXT DEFAULT 'open',
                    notes TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
                )
            """)

            logger.debug("Database schema initialized")

    def store_signal(self, signal: TradingSignal, execution_id: str) -> int:
        """
        Store a trading signal in the database.

        Args:
            signal: TradingSignal to store
            execution_id: Execution ID for this run

        Returns:
            Row ID of inserted signal
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Extract take profit levels
            tp_prices = [tp.price for tp in signal.take_profit_levels]
            while len(tp_prices) < 3:
                tp_prices.append(None)

            cursor.execute(
                """
                INSERT OR REPLACE INTO signals (
                    signal_id, timestamp, symbol, direction, confidence,
                    signal_strength, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3,
                    risk_reward, whale_metrics, options_metrics,
                    futures_metrics, execution_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    signal.signal_id,
                    signal.timestamp.isoformat(),
                    signal.symbol,
                    signal.direction.value,
                    signal.confidence_score,
                    signal.signal_strength.value,
                    signal.entry_zone.ideal,
                    signal.stop_loss.price,
                    tp_prices[0],
                    tp_prices[1],
                    tp_prices[2],
                    signal.risk_reward_ratio,
                    json.dumps(signal.whale_metrics),
                    json.dumps(signal.options_metrics),
                    json.dumps(signal.futures_metrics),
                    execution_id,
                ),
            )

            row_id = cursor.lastrowid

            logger.debug(
                f"Stored signal {signal.signal_id}",
                extra={
                    "data": {
                        "symbol": signal.symbol,
                        "direction": signal.direction.value,
                        "confidence": signal.confidence_score,
                    }
                },
            )

            return row_id

    def store_signals(self, signals: List[TradingSignal], execution_id: str) -> List[int]:
        """
        Store multiple trading signals.

        Args:
            signals: List of TradingSignal objects
            execution_id: Execution ID for this run

        Returns:
            List of row IDs
        """
        row_ids = []
        for signal in signals:
            row_id = self.store_signal(signal, execution_id)
            row_ids.append(row_id)

        logger.info(
            f"Stored {len(signals)} signals", extra={"data": {"execution_id": execution_id}}
        )

        return row_ids

    def get_signal_history(
        self,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        days: int = 7,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get historical signals.

        Args:
            symbol: Filter by symbol (optional)
            direction: Filter by direction (optional)
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of signal dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM signals
                WHERE timestamp >= datetime('now', ?)
            """
            params = [f"-{days} days"]

            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)

            if direction:
                query += " AND direction = ?"
                params.append(direction)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            signals = []
            for row in rows:
                signal = dict(row)
                # Parse JSON fields
                if signal.get("whale_metrics"):
                    signal["whale_metrics"] = json.loads(signal["whale_metrics"])
                if signal.get("options_metrics"):
                    signal["options_metrics"] = json.loads(signal["options_metrics"])
                if signal.get("futures_metrics"):
                    signal["futures_metrics"] = json.loads(signal["futures_metrics"])
                signals.append(signal)

            return signals

    def get_latest_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent signal for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Signal dictionary or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM signals
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """,
                (symbol,),
            )

            row = cursor.fetchone()
            if row:
                signal = dict(row)
                if signal.get("whale_metrics"):
                    signal["whale_metrics"] = json.loads(signal["whale_metrics"])
                if signal.get("options_metrics"):
                    signal["options_metrics"] = json.loads(signal["options_metrics"])
                if signal.get("futures_metrics"):
                    signal["futures_metrics"] = json.loads(signal["futures_metrics"])
                return signal

            return None

    def cleanup_old_signals(self) -> int:
        """
        Remove signals older than retention period.

        Returns:
            Number of deleted rows
        """
        cutoff_date = datetime.utcnow() - timedelta(weeks=self.retention_weeks)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Delete old signals
            cursor.execute(
                """
                DELETE FROM signals
                WHERE timestamp < ?
            """,
                (cutoff_date.isoformat(),),
            )

            deleted = cursor.rowcount

            # Delete orphaned performance records
            cursor.execute("""
                DELETE FROM performance
                WHERE signal_id NOT IN (
                    SELECT signal_id FROM signals
                )
            """)

            if deleted > 0:
                logger.info(
                    f"Cleaned up {deleted} old signals",
                    extra={
                        "data": {
                            "retention_weeks": self.retention_weeks,
                            "cutoff_date": cutoff_date.isoformat(),
                        }
                    },
                )

            return deleted

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with statistics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total signals
            cursor.execute("SELECT COUNT(*) FROM signals")
            total_signals = cursor.fetchone()[0]

            # Signals by symbol
            cursor.execute("""
                SELECT symbol, COUNT(*) as count
                FROM signals
                GROUP BY symbol
                ORDER BY count DESC
            """)
            by_symbol = {row["symbol"]: row["count"] for row in cursor.fetchall()}

            # Signals by direction
            cursor.execute("""
                SELECT direction, COUNT(*) as count
                FROM signals
                GROUP BY direction
            """)
            by_direction = {row["direction"]: row["count"] for row in cursor.fetchall()}

            # Average confidence
            cursor.execute("SELECT AVG(confidence) FROM signals")
            avg_confidence = cursor.fetchone()[0] or 0.0

            # Date range
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM signals")
            row = cursor.fetchone()
            date_range = {
                "earliest": row[0],
                "latest": row[1],
            }

            # Performance stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(pnl_pct) as avg_pnl
                FROM performance
                WHERE status = 'closed'
            """)
            perf_row = cursor.fetchone()
            performance = {
                "total_trades": perf_row[0] or 0,
                "wins": perf_row[1] or 0,
                "win_rate": (perf_row[1] / perf_row[0]) if perf_row[0] else 0,
                "avg_pnl_pct": perf_row[2] or 0.0,
            }

            return {
                "total_signals": total_signals,
                "by_symbol": by_symbol,
                "by_direction": by_direction,
                "avg_confidence": round(avg_confidence, 3),
                "date_range": date_range,
                "performance": performance,
                "database_path": str(self.db_path),
                "retention_weeks": self.retention_weeks,
            }

    def update_performance(
        self,
        signal_id: str,
        exit_price: float,
        exit_time: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Update performance tracking for a signal.

        Args:
            signal_id: Signal ID to update
            exit_price: Exit price
            exit_time: Exit timestamp (default: now)
            notes: Optional notes

        Returns:
            True if updated successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get signal info
            cursor.execute(
                """
                SELECT entry_price, direction FROM signals WHERE signal_id = ?
            """,
                (signal_id,),
            )
            row = cursor.fetchone()

            if not row:
                logger.warning(f"Signal not found: {signal_id}")
                return False

            entry_price = row["entry_price"]
            direction = row["direction"]

            # Calculate PnL
            if direction == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - exit_price) / entry_price * 100

            # Update performance record
            cursor.execute(
                """
                INSERT OR REPLACE INTO performance (
                    signal_id, symbol, entry_time, exit_time,
                    entry_price, exit_price, direction, pnl_pct,
                    status, notes
                )
                SELECT 
                    ?, symbol, timestamp, ?, entry_price, ?, direction, ?, 'closed', ?
                FROM signals WHERE signal_id = ?
            """,
                (
                    signal_id,
                    (exit_time or datetime.utcnow()).isoformat(),
                    exit_price,
                    pnl_pct,
                    notes,
                    signal_id,
                ),
            )

            logger.debug(
                f"Updated performance for {signal_id}",
                extra={
                    "data": {
                        "exit_price": exit_price,
                        "pnl_pct": round(pnl_pct, 2),
                    }
                },
            )

            return True

    def close(self):
        """Close database connection (for cleanup)."""
        # Connections are closed automatically via context manager
        logger.debug("Signal database closed")
