"""
Whale detection module.

Provides whale trade detection and volume analysis for Options market.
"""

from binance_signal_generator.whale.whale_detector import WhaleDetector
from binance_signal_generator.whale.volume_analyzer import WhaleVolumeAnalyzer

__all__ = [
    "WhaleDetector",
    "WhaleVolumeAnalyzer",
]
