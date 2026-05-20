"""
Options analysis module.

Provides analyzers for IV, PCR, OI, Max Pain calculations,
wall detection, gamma exposure, sentiment analysis, and signal scoring
from Options and Futures market data.
"""

# Import config classes from config module (single source of truth)
from binance_signal_generator.config import (
    IVConfig,
    PCRAnalyzerConfig,
    OIAnalyzerConfig,
    MaxPainAnalyzerConfig,
    WallDetectorAnalyzerConfig,
    GammaExposureAnalyzerConfig,
    SignalScorerAnalyzerConfig,
    SentimentConfig,
)

from binance_signal_generator.analysis.iv_analyzer import IVAnalyzer
from binance_signal_generator.analysis.pcr_analyzer import PCRAnalyzer
from binance_signal_generator.analysis.oi_analyzer import OIAnalyzer
from binance_signal_generator.analysis.max_pain import MaxPainCalculator
from binance_signal_generator.analysis.wall_detector import WallDetector
from binance_signal_generator.analysis.gamma_exposure import GammaExposureCalculator
from binance_signal_generator.analysis.sentiment import SentimentAnalyzer
from binance_signal_generator.analysis.signal_scorer import SignalScorer

__all__ = [
    "IVAnalyzer",
    "IVConfig",
    "PCRAnalyzer",
    "PCRAnalyzerConfig",
    "OIAnalyzer",
    "OIAnalyzerConfig",
    "MaxPainCalculator",
    "MaxPainAnalyzerConfig",
    "WallDetector",
    "WallDetectorAnalyzerConfig",
    "GammaExposureCalculator",
    "GammaExposureAnalyzerConfig",
    "SentimentAnalyzer",
    "SentimentConfig",
    "SignalScorer",
    "SignalScorerAnalyzerConfig",
]
