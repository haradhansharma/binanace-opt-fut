"""
JSON output module for signal generation.

This module handles JSON serialization and output of trading signals.
It supports:
- Pretty printing for human readability
- Compact output for programmatic consumption
- File output for logging/archival
- stdout output for pipe integration
- Full OutputConfig integration
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from binance_signal_generator.models import (
    ExecutionResult,
    TradingSignal,
    OptionsSignal,
    IVAnalysis,
    PCRAnalysis,
    OIAnalysis,
    MaxPainAnalysis,
    WhaleAnalysis,
)
from binance_signal_generator.utils.logging import get_logger

if TYPE_CHECKING:
    from binance_signal_generator.config.loader import OutputConfig

logger = get_logger(__name__)


class JSONOutputEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for handling special types.
    
    Handles:
    - datetime objects
    - Enum values
    - Float precision
    - None values
    """
    
    def default(self, obj: Any) -> Any:
        """Convert special types to JSON-serializable format."""
        if isinstance(obj, datetime):
            return obj.isoformat() + "Z"
        
        if hasattr(obj, "value"):  # Enum
            return obj.value
        
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        
        if isinstance(obj, float):
            # Round to avoid floating point issues
            return round(obj, 8)
        
        return super().default(obj)


class JSONOutput:
    """
    Handles JSON output for signal generation results.
    
    Features:
    - Compact or pretty output
    - stdout or file output
    - Signal-specific formatting
    - Metadata enrichment
    - Full OutputConfig support
    
    Attributes:
        config: OutputConfig object with all settings
    """
    
    def __init__(
        self,
        pretty: bool = False,
        output_file: Optional[str] = None,
        include_metadata: bool = True,
        include_selected_assets: bool = True,
        config: Optional["OutputConfig"] = None,
    ):
        """
        Initialize JSON output handler.
        
        Args:
            pretty: Enable pretty printing with indentation
            output_file: Optional file path to write output
            include_metadata: Include execution metadata in output
            include_selected_assets: Include selected assets list in output
            config: OutputConfig object (overrides other parameters)
        """
        if config is not None:
            self.pretty = config.json_pretty_print
            self.output_file = None  # File output handled separately
            self.include_metadata = config.json_include_metadata
            self.include_selected_assets = config.json_include_selected_assets
            self.config = config
        else:
            self.pretty = pretty
            self.output_file = output_file
            self.include_metadata = include_metadata
            self.include_selected_assets = include_selected_assets
            self.config = None
        
        logger.debug(
            "JSON output initialized",
            extra={"data": {
                "pretty": self.pretty,
                "output_file": self.output_file,
                "include_metadata": self.include_metadata,
                "include_selected_assets": self.include_selected_assets,
            }}
        )
    
    def output(self, result: ExecutionResult) -> None:
        """
        Output execution result as JSON.
        
        Args:
            result: Execution result to output
        """
        json_str = self.serialize(result)
        
        if self.output_file:
            self._write_to_file(json_str)
        else:
            self._write_to_stdout(json_str)
    
    def serialize(self, result: ExecutionResult) -> str:
        """
        Serialize execution result to JSON string.
        
        Args:
            result: Execution result
            
        Returns:
            JSON string
        """
        data = self._prepare_output(result)
        
        indent = 2 if self.pretty else None
        return json.dumps(
            data,
            cls=JSONOutputEncoder,
            indent=indent,
            ensure_ascii=False,
        )
    
    def _prepare_output(self, result: ExecutionResult) -> Dict[str, Any]:
        """
        Prepare execution result for JSON output.
        
        Args:
            result: Execution result
            
        Returns:
            Dictionary ready for JSON serialization
        """
        output = {
            "execution_id": result.execution_id,
            "timestamp": result.timestamp.isoformat() + "Z",
            "execution_duration_seconds": round(result.execution_duration_seconds, 2),
            "assets_analyzed": result.assets_analyzed,
            "signals_generated": result.signals_generated,
            "signals": [self._format_signal(s) for s in result.signals],
        }
        
        if self.include_metadata:
            output["metadata"] = {
                "config_file": result.config_path,
                "api_calls_made": result.api_calls_made,
                "data_freshness_seconds": result.data_freshness_seconds,
                "errors": result.errors,
            }
        
        if self.include_selected_assets:
            output["selected_assets"] = result.selected_assets
        
        return output
    
    def _format_signal(self, signal: TradingSignal) -> Dict[str, Any]:
        """
        Format a trading signal for JSON output.
        
        Args:
            signal: Trading signal
            
        Returns:
            Formatted dictionary
        """
        return {
            "signal_id": signal.signal_id,
            "timestamp": signal.timestamp.isoformat() + "Z",
            "symbol": signal.symbol,
            "asset_rank": signal.asset_rank,
            "activity_score": round(signal.activity_score, 3),
            
            # Direction and confidence
            "direction": signal.direction.value,
            "confidence_score": round(signal.confidence_score, 3),
            "signal_strength": signal.signal_strength.value,
            
            # Entry zone
            "entry_zone": {
                "min": round(signal.entry_zone.min, 4),
                "max": round(signal.entry_zone.max, 4),
                "ideal": round(signal.entry_zone.ideal, 4),
            },
            
            # Stop loss
            "stop_loss": {
                "price": round(signal.stop_loss.price, 4),
                "type": signal.stop_loss.type,
                "distance_pct": round(signal.stop_loss.distance_pct, 2),
                "source_strike": signal.stop_loss.source_strike,
                "confidence": round(signal.stop_loss.confidence, 2),
            },
            
            # Take profit levels
            "take_profit_levels": [
                {
                    "level": tp.level,
                    "price": round(tp.price, 4),
                    "ratio": round(tp.ratio, 2),
                    "distance_pct": round(tp.distance_pct, 2),
                    "type": tp.type,
                    "source": tp.source,
                }
                for tp in signal.take_profit_levels
            ],
            
            # Support and resistance
            "support_levels": signal.support_levels,
            "resistance_levels": signal.resistance_levels,
            
            # Metrics
            "whale_metrics": signal.whale_metrics,
            "options_metrics": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in signal.options_metrics.items()
            },
            "futures_metrics": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in signal.futures_metrics.items()
            },
            
            # Risk/reward
            "risk_reward_ratio": round(signal.risk_reward_ratio, 2),
        }
    
    def _write_to_stdout(self, json_str: str) -> None:
        """
        Write JSON to stdout.
        
        Args:
            json_str: JSON string to write
        """
        print(json_str)
        logger.debug("Output written to stdout")
    
    def _write_to_file(self, json_str: str) -> None:
        """
        Write JSON to file.
        
        Args:
            json_str: JSON string to write
        """
        path = Path(self.output_file)
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        path.write_text(json_str, encoding="utf-8")
        
        logger.info(f"Output written to {self.output_file}")
    
    @staticmethod
    def format_signal_compact(signal: TradingSignal) -> Dict[str, Any]:
        """
        Format signal in compact form for quick viewing.
        
        Args:
            signal: Trading signal
            
        Returns:
            Compact dictionary
        """
        return {
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "confidence": round(signal.confidence_score, 2),
            "entry": round(signal.entry_zone.ideal, 4),
            "sl": round(signal.stop_loss.price, 4),
            "tp1": round(signal.take_profit_levels[0].price, 4) if signal.take_profit_levels else None,
            "rr": round(signal.risk_reward_ratio, 2),
        }
    
    @staticmethod
    def format_signals_table(signals: List[TradingSignal]) -> str:
        """
        Format signals as a text table for console display.
        
        Args:
            signals: List of trading signals
            
        Returns:
            Formatted table string
        """
        if not signals:
            return "No signals generated"
        
        lines = []
        lines.append("=" * 80)
        lines.append(f"{'Symbol':<12} {'Dir':<6} {'Conf':<6} {'Entry':<12} {'SL':<12} {'TP1':<12} {'RR':<5}")
        lines.append("-" * 80)
        
        for s in signals:
            tp1 = s.take_profit_levels[0].price if s.take_profit_levels else 0
            lines.append(
                f"{s.symbol:<12} "
                f"{s.direction.value:<6} "
                f"{s.confidence_score:<6.2f} "
                f"{s.entry_zone.ideal:<12.4f} "
                f"{s.stop_loss.price:<12.4f} "
                f"{tp1:<12.4f} "
                f"{s.risk_reward_ratio:<5.2f}"
            )
        
        lines.append("=" * 80)
        
        return "\n".join(lines)


def output_signals(
    result: ExecutionResult,
    pretty: bool = False,
    output_file: Optional[str] = None,
    compact: bool = False,
    config: Optional["OutputConfig"] = None,
) -> None:
    """
    Convenience function to output signals.
    
    Args:
        result: Execution result
        pretty: Pretty print JSON
        output_file: Optional file path
        compact: Output compact format
        config: OutputConfig object (overrides other parameters)
    """
    if compact:
        # Output compact one signal per line
        for signal in result.signals:
            compact_data = JSONOutput.format_signal_compact(signal)
            print(json.dumps(compact_data, cls=JSONOutputEncoder))
    else:
        output = JSONOutput(pretty=pretty, output_file=output_file, config=config)
        output.output(result)


def get_output_summary(result: ExecutionResult) -> Dict[str, Any]:
    """
    Get a summary of the output for logging.
    
    Args:
        result: Execution result
        
    Returns:
        Summary dictionary
    """
    return {
        "execution_id": result.execution_id,
        "duration_seconds": round(result.execution_duration_seconds, 2),
        "assets_analyzed": result.assets_analyzed,
        "signals_generated": result.signals_generated,
        "api_calls": result.api_calls_made,
        "has_errors": len(result.errors) > 0,
        "symbols": [s.symbol for s in result.signals],
        "directions": [s.direction.value for s in result.signals],
    }
