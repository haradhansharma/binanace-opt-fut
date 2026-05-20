"""
Signal output module.

Provides JSON output, S/R level calculation, and signal formatting
for trading signals.
"""

from binance_signal_generator.output.json_output import (
    JSONOutput,
    JSONOutputEncoder,
    output_signals,
    get_output_summary,
)
from binance_signal_generator.output.sr_levels import SRLevelCalculator

__all__ = [
    "JSONOutput",
    "JSONOutputEncoder",
    "output_signals",
    "get_output_summary",
    "SRLevelCalculator",
]
