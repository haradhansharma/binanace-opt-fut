"""
Put-Call Ratio (PCR) analyzer for Options data.

This module analyzes the Put-Call Ratio from Options data to generate
trading signals. PCR is a sentiment indicator that shows the balance
between put and call options.

PCR Interpretation:
- PCR > 1.2: Put-heavy, potentially bearish sentiment
- PCR < 0.8: Call-heavy, potentially bullish sentiment
- PCR around 1.0: Balanced market

Signal Logic (Trend-Aware):
- High PCR + price falling: Trend confirms bearish → SHORT (follow trend)
- High PCR + price rising: Trend opposes → LONG (contrarian, reduced confidence)
- Low PCR + price rising: Trend confirms bullish → LONG (follow trend)
- Low PCR + price falling: Trend opposes → SHORT (contrarian, reduced confidence)
- Without price trend data: Falls back to contrarian logic (legacy)
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
    
    # BUG FIX (Bug #12): Weight for notional PCR vs OI PCR.
    # Previously called "volume_weight" but now uses notional (USDT) PCR.
    # The 40% weight for notional PCR captures short-term capital flow
    # (where big money is trading), while 60% OI PCR captures structural
    # positioning. This restores the distinction lost when Bug #4 changed
    # total_call_volume/total_put_volume from notional to contract count.
    volume_weight: float = 0.4         # 40% notional PCR, 60% OI PCR
    
    # Minimum OI for valid analysis
    min_total_oi: int = 100


class PCRAnalyzer:
    """
    Analyzes Put-Call Ratio from Options data.
    
    PCR Analysis Methods:
    1. OI-based PCR: Total Put OI / Total Call OI
    2. Volume-based PCR: Total Put Volume / Total Call Volume
    3. Weighted PCR: Combination of both
    
    Signal Generation (Trend-Aware):
    - When price trend CONFIRMS PCR: Follow the trend (crowd is right)
    - When price trend OPPOSES PCR: Contrarian signal with reduced confidence
    - Without price data: Falls back to pure contrarian logic
    
    The trend-aware approach prevents the systematic LONG bias that occurred
    when contrarian logic always flipped bearish PCR signals to LONG, even
    when the market was actively trending down.
    
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
    
    def analyze(
        self,
        chain: OptionsChain,
        price_change_pct: Optional[float] = None,
    ) -> PCRAnalysis:
        """
        Analyze PCR from options chain.
        
        BUG FIX (Bug #12): Volume PCR now uses notional (USDT) based PCR instead
        of contract count PCR. After Bug #4 fix changed total_call_volume/total_put_volume
        to contract count, volume PCR (put_contracts / call_contracts) became essentially
        the same as OI PCR (put_OI / call_OI) — both measure the put/call ratio by
        contract count. Notional PCR (put_USDT / call_USDT) captures capital flow:
        where the big money is trading. Deep ITM options have much higher notional per
        contract, so notional PCR reveals different information than contract count PCR.
        
        Args:
            chain: Options chain data
            price_change_pct: Optional price change percentage for trend context.
                When provided, the signal logic adjusts between contrarian and
                trend-following based on whether price trend confirms or opposes
                the PCR signal direction.
            
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
        # BUG FIX (Bug #12): Use notional-based PCR for the volume component.
        # After Bug #4, chain.get_volume_pcr() returns put_contracts/call_contracts
        # which is redundant with OI PCR. Notional PCR (put_USDT / call_USDT) captures
        # short-term capital flow direction, distinct from structural OI positioning.
        pcr_volume = chain.get_notional_pcr()
        
        # Calculate combined PCR
        pcr_combined = self._calculate_combined_pcr(pcr_oi, pcr_volume)
        
        # Determine PCR state
        pcr_state = self._determine_pcr_state(pcr_combined)
        
        # Generate signal with trend context
        signal, confidence = self._generate_signal(pcr_combined, price_change_pct)
        
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
    
    def _generate_signal(
        self,
        pcr: float,
        price_change_pct: Optional[float] = None,
    ) -> tuple:
        """
        Generate trading signal from PCR with trend context.
        
        Signal Logic (Trend-Aware):
        
        PCR alone is traditionally a contrarian indicator:
        - High PCR (> 1.2): Crowd is bearish -> Contrarian bullish signal
        - Low PCR (< 0.8): Crowd is bullish -> Contrarian bearish signal
        
        BUG FIX: When price trend CONFIRMS the PCR reading (e.g., high PCR
        + price falling), the crowd is RIGHT and contrarian logic is wrong.
        In a trending market, contrarian signals should be suppressed and
        replaced with trend-following signals.
        
        Decision matrix:
        ┌─────────────┬───────────────┬─────────────────────────────────┐
        │ PCR Signal  │ Price Trend   │ Action                          │
        ├─────────────┼───────────────┼─────────────────────────────────┤
        │ High (bear) │ Price DOWN    │ Trend confirms → SHORT (follow) │
        │ High (bear) │ Price UP      │ Trend opposes → LONG (contrarian)│
        │ High (bear) │ No trend data → LONG (contrarian, legacy)    │
        │ Low (bull)  │ Price UP      │ Trend confirms → LONG (follow)  │
        │ Low (bull)  │ Price DOWN    │ Trend opposes → SHORT (contrarian)│
        │ Low (bull)  │ No trend data → SHORT (contrarian, legacy)   │
        └─────────────┴───────────────┴─────────────────────────────────┘
        
        Confidence adjustment:
        - Trend-following: confidence based on PCR extremity + trend strength
        - Contrarian (trend opposes): confidence reduced by 40% since the
          market is actively moving against the contrarian view
        - No trend data: uses legacy contrarian logic (unchanged)
        
        Args:
            pcr: Combined PCR value
            price_change_pct: Price change percentage for trend context.
                Positive = price rising, Negative = price falling.
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        # Determine the raw PCR direction (before contrarian/trend-following)
        pcr_bearish = pcr >= self.config.pcr_high_threshold  # High PCR = bearish sentiment
        pcr_bullish = pcr <= self.config.pcr_low_threshold   # Low PCR = bullish sentiment
        
        # Calculate base confidence from PCR extremity
        if pcr >= self.config.pcr_extreme_high:
            base_confidence = 0.8
        elif pcr >= self.config.pcr_high_threshold:
            excess = (pcr - self.config.pcr_high_threshold) / (
                self.config.pcr_extreme_high - self.config.pcr_high_threshold
            )
            base_confidence = 0.5 + 0.3 * min(excess, 1.0)
        elif pcr <= self.config.pcr_extreme_low:
            base_confidence = 0.8
        elif pcr <= self.config.pcr_low_threshold:
            deficit = (self.config.pcr_low_threshold - pcr) / (
                self.config.pcr_low_threshold - self.config.pcr_extreme_low
            )
            base_confidence = 0.5 + 0.3 * min(deficit, 1.0)
        else:
            return SignalDirection.NEUTRAL, 0.2
        
        # Apply trend-aware signal logic
        # BUG FIX (Bug #10): Lowered threshold from 0.15% to 0.05%.
        # Previously, when price_change_pct was between -0.15% and +0.15%, the
        # code fell back to legacy contrarian logic where high PCR → LONG. Since
        # PCR is typically > 1.0 in crypto (more puts as protection), this
        # fallback systematically contributed LONG signal, adding to structural
        # LONG bias. The 0.05% threshold activates trend-aware logic for almost
        # all non-flat periods, reducing the contrarian LONG fallback frequency.
        trend_threshold = 0.05
        if price_change_pct is not None and abs(price_change_pct) > trend_threshold:
            # We have price trend data - use trend-aware logic
            price_trending_down = price_change_pct < -trend_threshold
            price_trending_up = price_change_pct > trend_threshold
            
            if pcr_bearish:
                # High PCR = crowd is bearish
                if price_trending_down:
                    # Price IS falling → crowd is RIGHT → trend-following SHORT
                    # Stronger confidence when trend confirms PCR
                    trend_strength = min(abs(price_change_pct) / 3.0, 0.3)
                    confidence = min(base_confidence + trend_strength, 0.85)
                    logger.debug(
                        f"PCR signal: HIGH={pcr:.2f} + price DOWN={price_change_pct:.2f}% "
                        f"→ trend confirms bearish → SHORT (follow trend)"
                    )
                    return SignalDirection.SHORT, confidence
                else:
                    # Price is rising → crowd may be wrong → contrarian LONG
                    # FIX: Scale penalty with trend strength instead of flat 0.6
                    penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.3)
                    confidence = base_confidence * penalty
                    logger.debug(
                        f"PCR signal: HIGH={pcr:.2f} + price UP={price_change_pct:.2f}% "
                        f"→ trend opposes bearish → LONG (contrarian, reduced confidence)"
                    )
                    return SignalDirection.LONG, confidence
            
            elif pcr_bullish:
                # Low PCR = crowd is bullish
                if price_trending_up:
                    # Price IS rising → crowd is RIGHT → trend-following LONG
                    trend_strength = min(abs(price_change_pct) / 3.0, 0.3)
                    confidence = min(base_confidence + trend_strength, 0.85)
                    logger.debug(
                        f"PCR signal: LOW={pcr:.2f} + price UP={price_change_pct:.2f}% "
                        f"→ trend confirms bullish → LONG (follow trend)"
                    )
                    return SignalDirection.LONG, confidence
                else:
                    # Price is falling → crowd may be wrong → contrarian SHORT
                    # FIX: Scale penalty with trend strength
                    penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.3)
                    confidence = base_confidence * penalty
                    logger.debug(
                        f"PCR signal: LOW={pcr:.2f} + price DOWN={price_change_pct:.2f}% "
                        f"→ trend opposes bullish → SHORT (contrarian, reduced confidence)"
                    )
                    return SignalDirection.SHORT, confidence
        
        # No trend data available → use legacy contrarian logic
        if pcr >= self.config.pcr_extreme_high:
            return SignalDirection.LONG, base_confidence
        elif pcr >= self.config.pcr_high_threshold:
            return SignalDirection.LONG, base_confidence
        elif pcr <= self.config.pcr_extreme_low:
            return SignalDirection.SHORT, base_confidence
        elif pcr <= self.config.pcr_low_threshold:
            return SignalDirection.SHORT, base_confidence
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
            return "Extreme put bias - very bearish crowd - trend-aware: follow if price falling, contrarian if rising"
        elif pcr >= self.config.pcr_high_threshold:
            return "High put bias - bearish crowd - trend-aware: follow if price falling, contrarian if rising"
        elif pcr <= self.config.pcr_extreme_low:
            return "Extreme call bias - very bullish crowd - trend-aware: follow if price rising, contrarian if falling"
        elif pcr <= self.config.pcr_low_threshold:
            return "High call bias - bullish crowd - trend-aware: follow if price rising, contrarian if falling"
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
