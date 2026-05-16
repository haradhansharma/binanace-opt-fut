"""
Put-Call Ratio (PCR) analyzer for Options data.

This module analyzes the Put-Call Ratio from Options data to generate
trading signals. PCR is a sentiment indicator that shows the balance
between put and call options.

PCR Interpretation:
- PCR > 1.2: Put-heavy, potentially bearish sentiment (contrarian: bullish)
- PCR < 0.8: Call-heavy, potentially bullish sentiment (contrarian: bearish)
- PCR around 1.0: Balanced market

Signal Logic (Contrarian):
- High PCR (> 1.2): Market is bearish, contrarian bullish signal
- Low PCR (< 0.8): Market is bullish, contrarian bearish signal
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    PCRAnalysis,
    SignalDirection,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PCRConfig:
    """Configuration for PCR analysis."""
    # PCR thresholds
    pcr_high_threshold: float = 1.2    # Put-heavy
    pcr_low_threshold: float = 0.8     # Call-heavy
    pcr_extreme_high: float = 1.5      # Very put-heavy
    pcr_extreme_low: float = 0.5       # Very call-heavy
    
    # Weight for volume PCR vs OI PCR
    volume_weight: float = 0.4         # 40% volume, 60% OI
    
    # Minimum OI for valid analysis
    min_total_oi: int = 100


class PCRAnalyzer:
    """
    Analyzes Put-Call Ratio from Options data.
    
    PCR Analysis Methods:
    1. OI-based PCR: Total Put OI / Total Call OI
    2. Volume-based PCR: Total Put Volume / Total Call Volume
    3. Weighted PCR: Combination of both
    
    Signal Generation (Contrarian):
    - High PCR = Bearish sentiment = Bullish contrarian signal
    - Low PCR = Bullish sentiment = Bearish contrarian signal
    
    Note: This is a contrarian indicator - when the crowd is
    positioned one way, the market often moves the opposite.
    
    Attributes:
        config: PCR analysis configuration
    """
    
    def __init__(self, config: Optional[PCRConfig] = None):
        """
        Initialize PCR analyzer.
        
        Args:
            config: PCR analysis configuration
        """
        self.config = config or PCRConfig()
        
        logger.info(
            "PCR analyzer initialized",
            extra={"data": {
                "pcr_high": self.config.pcr_high_threshold,
                "pcr_low": self.config.pcr_low_threshold,
            }}
        )
    
    def analyze(self, chain: OptionsChain) -> PCRAnalysis:
        """
        Analyze PCR from options chain.
        
        Args:
            chain: Options chain data
            
        Returns:
            PCRAnalysis with PCR metrics and signal
        """
        total_oi = chain.total_call_oi + chain.total_put_oi
        
        if total_oi < self.config.min_total_oi:
            logger.warning(
                f"Insufficient OI for PCR analysis: {total_oi}"
            )
            return self._create_empty_analysis(chain.underlying)
        
        # Calculate PCR values
        pcr_oi = chain.get_pcr()
        pcr_volume = chain.get_volume_pcr()
        
        # Calculate combined PCR
        pcr_combined = self._calculate_combined_pcr(pcr_oi, pcr_volume)
        
        # Determine PCR state
        pcr_state = self._determine_pcr_state(pcr_combined)
        
        # Generate signal
        signal, confidence = self._generate_signal(pcr_combined)
        
        return PCRAnalysis(
            symbol=chain.underlying,
            timestamp=datetime.utcnow(),
            pcr_oi=pcr_oi,
            pcr_volume=pcr_volume,
            pcr_combined=pcr_combined,
            signal=signal,
            confidence=confidence,
            pcr_state=pcr_state,
        )
    
    def _calculate_combined_pcr(
        self,
        pcr_oi: float,
        pcr_volume: float,
    ) -> float:
        """
        Calculate weighted combined PCR.
        
        Args:
            pcr_oi: OI-based PCR
            pcr_volume: Volume-based PCR
            
        Returns:
            Combined weighted PCR
        """
        vol_weight = self.config.volume_weight
        oi_weight = 1 - vol_weight
        
        # Handle infinite values
        if pcr_oi == float('inf'):
            pcr_oi = 10.0  # Cap at 10
        if pcr_volume == float('inf'):
            pcr_volume = 10.0
        
        return pcr_oi * oi_weight + pcr_volume * vol_weight
    
    def _determine_pcr_state(self, pcr: float) -> str:
        """
        Determine PCR state from value.
        
        Args:
            pcr: Combined PCR value
            
        Returns:
            PCR state string
        """
        if pcr >= self.config.pcr_high_threshold:
            return "PUT_HEAVY"
        elif pcr <= self.config.pcr_low_threshold:
            return "CALL_HEAVY"
        else:
            return "NEUTRAL"
    
    def _generate_signal(self, pcr: float) -> tuple:
        """
        Generate trading signal from PCR.
        
        Contrarian Logic:
        - High PCR (> 1.2): Crowd is bearish -> Bullish signal
        - Low PCR (< 0.8): Crowd is bullish -> Bearish signal
        - Extreme values get higher confidence
        
        Args:
            pcr: Combined PCR value
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        # Very high PCR (extreme bearishness) - Strong bullish contrarian
        if pcr >= self.config.pcr_extreme_high:
            return SignalDirection.LONG, 0.8
        
        # High PCR (bearish sentiment) - Bullish contrarian
        elif pcr >= self.config.pcr_high_threshold:
            # Scale confidence based on how extreme
            excess = (pcr - self.config.pcr_high_threshold) / (
                self.config.pcr_extreme_high - self.config.pcr_high_threshold
            )
            confidence = 0.5 + 0.3 * min(excess, 1.0)
            return SignalDirection.LONG, confidence
        
        # Very low PCR (extreme bullishness) - Strong bearish contrarian
        elif pcr <= self.config.pcr_extreme_low:
            return SignalDirection.SHORT, 0.8
        
        # Low PCR (bullish sentiment) - Bearish contrarian
        elif pcr <= self.config.pcr_low_threshold:
            # Scale confidence based on how extreme
            deficit = (self.config.pcr_low_threshold - pcr) / (
                self.config.pcr_low_threshold - self.config.pcr_extreme_low
            )
            confidence = 0.5 + 0.3 * min(deficit, 1.0)
            return SignalDirection.SHORT, confidence
        
        # Neutral PCR
        else:
            return SignalDirection.NEUTRAL, 0.2
    
    def _create_empty_analysis(self, symbol: str) -> PCRAnalysis:
        """Create empty PCR analysis for insufficient data."""
        return PCRAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            pcr_oi=1.0,
            pcr_volume=1.0,
            pcr_combined=1.0,
            signal=SignalDirection.NEUTRAL,
            confidence=0.0,
            pcr_state="NEUTRAL",
        )
    
    def analyze_pcr_by_strike(
        self,
        chain: OptionsChain,
    ) -> Dict[str, Any]:
        """
        Analyze PCR distribution across strikes.
        
        This shows where the put/call imbalance is concentrated.
        
        Args:
            chain: Options chain
            
        Returns:
            Dictionary with strike-by-strike PCR
        """
        strike_pcrs = []
        
        for strike_price, strike_data in chain.strikes.items():
            call_oi = strike_data.call.open_interest
            put_oi = strike_data.put.open_interest
            
            if call_oi > 0:
                strike_pcr = put_oi / call_oi
            else:
                strike_pcr = float('inf') if put_oi > 0 else 1.0
            
            strike_pcrs.append({
                "strike": strike_price,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "pcr": min(strike_pcr, 10.0),  # Cap for display
                "distance_from_spot": round(
                    (strike_price - chain.spot_price) / chain.spot_price * 100, 2
                ),
            })
        
        # Sort by distance from spot
        strike_pcrs.sort(key=lambda x: abs(x["distance_from_spot"]))
        
        # Find extreme PCR strikes
        put_heavy_strikes = [
            s for s in strike_pcrs
            if s["pcr"] >= self.config.pcr_high_threshold
        ]
        call_heavy_strikes = [
            s for s in strike_pcrs
            if s["pcr"] <= self.config.pcr_low_threshold
        ]
        
        return {
            "strike_pcrs": strike_pcrs,
            "put_heavy_count": len(put_heavy_strikes),
            "call_heavy_count": len(call_heavy_strikes),
            "avg_pcr": sum(s["pcr"] for s in strike_pcrs if s["pcr"] < 10) / max(1, len([s for s in strike_pcrs if s["pcr"] < 10])),
        }
    
    def get_pcr_summary(self, analysis: PCRAnalysis) -> Dict[str, Any]:
        """
        Get summary of PCR analysis.
        
        Args:
            analysis: PCR analysis result
            
        Returns:
            Dictionary with PCR summary
        """
        return {
            "symbol": analysis.symbol,
            "pcr_oi": round(analysis.pcr_oi, 3),
            "pcr_volume": round(analysis.pcr_volume, 3),
            "pcr_combined": round(analysis.pcr_combined, 3),
            "pcr_state": analysis.pcr_state,
            "signal": analysis.signal.value,
            "confidence": round(analysis.confidence, 2),
            "interpretation": self._interpret_pcr(analysis.pcr_combined),
        }
    
    def _interpret_pcr(self, pcr: float) -> str:
        """Interpret PCR value."""
        if pcr >= self.config.pcr_extreme_high:
            return "Extreme put bias - very bearish crowd - contrarian bullish"
        elif pcr >= self.config.pcr_high_threshold:
            return "High put bias - bearish crowd - contrarian bullish"
        elif pcr <= self.config.pcr_extreme_low:
            return "Extreme call bias - very bullish crowd - contrarian bearish"
        elif pcr <= self.config.pcr_low_threshold:
            return "High call bias - bullish crowd - contrarian bearish"
        else:
            return "Balanced market - neutral"
    
    def calculate_pcr_change(
        self,
        current_pcr: float,
        previous_pcr: float,
    ) -> Dict[str, Any]:
        """
        Calculate PCR change for trend analysis.
        
        Args:
            current_pcr: Current PCR value
            previous_pcr: Previous PCR value
            
        Returns:
            Dictionary with change analysis
        """
        if previous_pcr == 0:
            return {"change": 0, "change_pct": 0, "trend": "UNKNOWN"}
        
        change = current_pcr - previous_pcr
        change_pct = (change / previous_pcr) * 100
        
        # Determine trend
        if change_pct > 10:
            trend = "PUT_INCREASING"  # More bearish positioning
        elif change_pct < -10:
            trend = "CALL_INCREASING"  # More bullish positioning
        else:
            trend = "STABLE"
        
        return {
            "current_pcr": round(current_pcr, 3),
            "previous_pcr": round(previous_pcr, 3),
            "change": round(change, 3),
            "change_pct": round(change_pct, 2),
            "trend": trend,
        }
