"""
Signal scorer for combining multiple analysis signals.

This module combines signals from IV, PCR, OI, and Max Pain analysis
to generate a unified trading signal with confidence scoring.

Signal Combination:
- Each analyzer provides a signal direction and confidence
- Signals are weighted based on reliability
- Final signal is the weighted combination
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from binance_signal_generator.models import (
    OptionsChain,
    OptionsSignal,
    IVAnalysis,
    PCRAnalysis,
    OIAnalysis,
    MaxPainAnalysis,
    SignalDirection,
)
from binance_signal_generator.analysis.iv_analyzer import IVAnalyzer, IVConfig
from binance_signal_generator.analysis.pcr_analyzer import PCRAnalyzer, PCRConfig
from binance_signal_generator.analysis.oi_analyzer import OIAnalyzer, OIConfig
from binance_signal_generator.analysis.max_pain import MaxPainCalculator, MaxPainConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SignalScorerConfig:
    """Configuration for signal scoring."""
    # Weights for each signal type
    iv_weight: float = 0.25
    pcr_weight: float = 0.30
    oi_weight: float = 0.25
    max_pain_weight: float = 0.20
    
    # Minimum confidence for valid signal
    min_confidence: float = 0.4
    
    # Agreement threshold
    agreement_threshold: float = 0.6  # % of signals agreeing


class SignalScorer:
    """
    Combines multiple analysis signals into a unified trading signal.
    
    Signal Combination Method:
    1. Convert each signal to numeric (-1, 0, 1)
    2. Weight by confidence and signal type
    3. Sum weighted signals
    4. Normalize to final direction and confidence
    
    Attributes:
        config: Signal scoring configuration
        iv_analyzer: IV analyzer instance
        pcr_analyzer: PCR analyzer instance
        oi_analyzer: OI analyzer instance
        max_pain_calculator: Max Pain calculator instance
    """
    
    def __init__(
        self,
        config: Optional[SignalScorerConfig] = None,
        iv_config: Optional[IVConfig] = None,
        pcr_config: Optional[PCRConfig] = None,
        oi_config: Optional[OIConfig] = None,
        max_pain_config: Optional[MaxPainConfig] = None,
    ):
        """
        Initialize signal scorer.
        
        Args:
            config: Signal scoring configuration
            iv_config: IV analyzer configuration
            pcr_config: PCR analyzer configuration
            oi_config: OI analyzer configuration
            max_pain_config: Max Pain calculator configuration
        """
        self.config = config or SignalScorerConfig()
        
        # Initialize analyzers
        self.iv_analyzer = IVAnalyzer(iv_config)
        self.pcr_analyzer = PCRAnalyzer(pcr_config)
        self.oi_analyzer = OIAnalyzer(oi_config)
        self.max_pain_calculator = MaxPainCalculator(max_pain_config)
        
        logger.info(
            "Signal scorer initialized",
            extra={"data": {
                "weights": {
                    "iv": self.config.iv_weight,
                    "pcr": self.config.pcr_weight,
                    "oi": self.config.oi_weight,
                    "max_pain": self.config.max_pain_weight,
                },
            }}
        )
    
    def analyze(self, chain: OptionsChain) -> OptionsSignal:
        """
        Perform complete analysis and generate combined signal.
        
        Args:
            chain: Options chain data
            
        Returns:
            OptionsSignal with combined analysis
        """
        # Run all analyzers
        iv_analysis = self.iv_analyzer.analyze(chain)
        pcr_analysis = self.pcr_analyzer.analyze(chain)
        oi_analysis = self.oi_analyzer.analyze(chain)
        max_pain_analysis = self.max_pain_calculator.calculate(chain)
        
        # Debug logging
        logger.debug(
            f"Signal components for {chain.underlying}: "
            f"IV={iv_analysis.signal.value}({iv_analysis.confidence:.2f}), "
            f"PCR={pcr_analysis.signal.value}({pcr_analysis.confidence:.2f}), "
            f"OI={oi_analysis.signal.value}({oi_analysis.confidence:.2f}), "
            f"MaxPain={max_pain_analysis.signal.value}({max_pain_analysis.confidence:.2f})"
        )
        
        # Combine signals
        direction, confidence, raw_score = self._combine_signals(
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
        )
        
        return OptionsSignal(
            symbol=chain.underlying,
            timestamp=datetime.utcnow(),
            direction=direction,
            confidence=confidence,
            raw_score=raw_score,
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
        )
    
    def _combine_signals(
        self,
        iv_analysis: IVAnalysis,
        pcr_analysis: PCRAnalysis,
        oi_analysis: OIAnalysis,
        max_pain_analysis: MaxPainAnalysis,
    ) -> tuple:
        """
        Combine multiple signals into one.
        
        Args:
            iv_analysis: IV analysis result
            pcr_analysis: PCR analysis result
            oi_analysis: OI analysis result
            max_pain_analysis: Max Pain analysis result
            
        Returns:
            Tuple of (SignalDirection, confidence, raw_score)
        """
        # Convert signals to numeric
        signals = {
            "iv": self._signal_to_numeric(iv_analysis.signal) * iv_analysis.confidence,
            "pcr": self._signal_to_numeric(pcr_analysis.signal) * pcr_analysis.confidence,
            "oi": self._signal_to_numeric(oi_analysis.signal) * oi_analysis.confidence,
            "max_pain": self._signal_to_numeric(max_pain_analysis.signal) * max_pain_analysis.confidence,
        }
        
        # Apply weights
        weighted_signals = {
            "iv": signals["iv"] * self.config.iv_weight,
            "pcr": signals["pcr"] * self.config.pcr_weight,
            "oi": signals["oi"] * self.config.oi_weight,
            "max_pain": signals["max_pain"] * self.config.max_pain_weight,
        }
        
        # Calculate raw score
        raw_score = sum(weighted_signals.values())
        
        # Calculate agreement
        agreement = self._calculate_agreement(
            iv_analysis.signal,
            pcr_analysis.signal,
            oi_analysis.signal,
            max_pain_analysis.signal,
        )
        
        # Determine direction
        if raw_score > 0.15:
            direction = SignalDirection.LONG
        elif raw_score < -0.15:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL
        
        # Calculate confidence
        # Base confidence from signal strength
        base_confidence = min(abs(raw_score) * 2, 1.0)
        
        # Adjust by agreement
        confidence = base_confidence * (0.5 + 0.5 * agreement)
        
        return direction, round(confidence, 3), round(raw_score, 3)
    
    def _signal_to_numeric(self, signal: SignalDirection) -> float:
        """Convert signal direction to numeric value."""
        if signal == SignalDirection.LONG:
            return 1.0
        elif signal == SignalDirection.SHORT:
            return -1.0
        else:
            return 0.0
    
    def _calculate_agreement(
        self,
        *signals: SignalDirection,
    ) -> float:
        """
        Calculate how much signals agree.
        
        Args:
            *signals: Signal directions
            
        Returns:
            Agreement score (0-1)
        """
        if not signals:
            return 0.0
        
        # Count non-neutral signals
        non_neutral = [s for s in signals if s != SignalDirection.NEUTRAL]
        
        if not non_neutral:
            return 0.0
        
        # Count longs and shorts
        longs = sum(1 for s in non_neutral if s == SignalDirection.LONG)
        shorts = sum(1 for s in non_neutral if s == SignalDirection.SHORT)
        
        # Agreement is the proportion of the majority
        majority = max(longs, shorts)
        total = len(non_neutral)
        
        return majority / total if total > 0 else 0.0
    
    def get_signal_breakdown(self, signal: OptionsSignal) -> Dict[str, Any]:
        """
        Get detailed breakdown of signal components.
        
        Args:
            signal: Options signal
            
        Returns:
            Dictionary with signal breakdown
        """
        breakdown = {
            "symbol": signal.symbol,
            "final_direction": signal.direction.value,
            "final_confidence": signal.confidence,
            "raw_score": signal.raw_score,
            "components": {},
        }
        
        if signal.iv_analysis:
            breakdown["components"]["iv"] = {
                "direction": signal.iv_analysis.signal.value,
                "confidence": signal.iv_analysis.confidence,
                "iv_state": signal.iv_analysis.iv_state,
                "current_iv": round(signal.iv_analysis.current_iv, 4),
            }
        
        if signal.pcr_analysis:
            breakdown["components"]["pcr"] = {
                "direction": signal.pcr_analysis.signal.value,
                "confidence": signal.pcr_analysis.confidence,
                "pcr_state": signal.pcr_analysis.pcr_state,
                "pcr_combined": round(signal.pcr_analysis.pcr_combined, 3),
            }
        
        if signal.oi_analysis:
            breakdown["components"]["oi"] = {
                "direction": signal.oi_analysis.signal.value,
                "confidence": signal.oi_analysis.confidence,
                "call_concentration": round(signal.oi_analysis.call_oi_concentration, 3),
                "put_concentration": round(signal.oi_analysis.put_oi_concentration, 3),
            }
        
        if signal.max_pain_analysis:
            breakdown["components"]["max_pain"] = {
                "direction": signal.max_pain_analysis.signal.value,
                "confidence": signal.max_pain_analysis.confidence,
                "max_pain_strike": round(signal.max_pain_analysis.max_pain_strike, 2),
                "distance_pct": round(signal.max_pain_analysis.distance_pct, 2),
                "magnet_strength": round(signal.max_pain_analysis.magnet_strength, 3),
            }
        
        return breakdown
    
    def validate_signal(self, signal: OptionsSignal) -> Dict[str, Any]:
        """
        Validate signal quality.
        
        Args:
            signal: Options signal to validate
            
        Returns:
            Dictionary with validation result
        """
        issues = []
        
        # Check confidence
        if signal.confidence < self.config.min_confidence:
            issues.append(f"Low confidence: {signal.confidence:.2f}")
        
        # Check if signals conflict
        if signal.iv_analysis and signal.pcr_analysis:
            iv_dir = signal.iv_analysis.signal
            pcr_dir = signal.pcr_analysis.signal
            
            if iv_dir != SignalDirection.NEUTRAL and pcr_dir != SignalDirection.NEUTRAL:
                if iv_dir != pcr_dir:
                    issues.append("IV and PCR signals conflict")
        
        # Check raw score magnitude
        if abs(signal.raw_score) < 0.1:
            issues.append("Weak raw score - signals cancel out")
        
        is_valid = len(issues) == 0
        
        return {
            "is_valid": is_valid,
            "issues": issues,
            "quality_score": signal.confidence if is_valid else signal.confidence * 0.5,
        }
