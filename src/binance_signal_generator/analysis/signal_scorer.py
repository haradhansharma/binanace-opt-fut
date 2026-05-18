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
    GammaAnalysis,
    SentimentAnalysis,
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
    # Core weights for each signal type (total must equal 1.0)
    # Adjusted to include advanced metrics
    iv_weight: float = 0.15           # Reduced from 0.18
    pcr_weight: float = 0.18          # Reduced from 0.22
    oi_weight: float = 0.15           # Reduced from 0.18
    max_pain_weight: float = 0.10     # Reduced from 0.12
    sentiment_weight: float = 0.15    # Reduced from 0.18
    gamma_weight: float = 0.10        # Reduced from 0.12
    
    # Advanced metrics weights (NEW - Section 6.5 implementation)
    # IMPROVED: OI-001 - Increased OI flow weight from 5% to 12% (critical signal)
    oi_flow_weight: float = 0.12      # OI flow direction (BUILDING/UNWINDING) - PRIMARY signal
    wall_concentration_weight: float = 0.04   # Wall concentration from whale analysis
    # IMPROVED: PCR-004 - Increased PCR strike alignment weight from 3% to 8%
    pcr_strike_alignment_weight: float = 0.08  # PCR strike alignment - enhanced significance
    whale_flow_weight: float = 0.05   # Whale money flow analysis
    # IMPROVED: IV-003 - Added IV term structure weight
    iv_term_structure_weight: float = 0.03  # IV term structure signal
    
    # Minimum confidence for valid signal
    min_confidence: float = 0.4
    
    # Agreement threshold
    agreement_threshold: float = 0.6  # % of signals agreeing
    
    # IV value thresholds for crypto (Section 6.5 Priority 2)
    iv_high_value: float = 0.80       # 80% annualized = HIGH
    iv_low_value: float = 0.40        # 40% annualized = LOW


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
                    "sentiment": self.config.sentiment_weight,
                    "gamma": self.config.gamma_weight,
                },
            }}
        )
    
    def analyze(
        self,
        chain: OptionsChain,
        sentiment_analysis: Optional[SentimentAnalysis] = None,
        gamma_analysis: Optional[GammaAnalysis] = None,
        advanced_metrics: Optional[Dict[str, Any]] = None,
        whale_volume_analysis: Optional[Dict[str, Any]] = None,
        wall_analysis: Optional[Any] = None,
    ) -> OptionsSignal:
        """
        Perform complete analysis and generate combined signal.
        
        Args:
            chain: Options chain data
            sentiment_analysis: Optional sentiment analysis from L/S ratios
            gamma_analysis: Optional gamma exposure analysis for dealer hedging
            advanced_metrics: Optional dict with pcr_by_strike, oi_distribution, oi_flow, etc.
            whale_volume_analysis: Optional whale volume analysis from WhaleVolumeAnalyzer
            wall_analysis: Optional wall analysis from WallDetector
            
        Returns:
            OptionsSignal with combined analysis
        """
        # Extract price change from advanced metrics for trend-aware analysis
        price_change_pct = None
        if advanced_metrics and advanced_metrics.get("oi_flow"):
            price_change_pct = advanced_metrics["oi_flow"].get("price_change_pct")
        
        # Run all analyzers
        iv_analysis = self.iv_analyzer.analyze(chain)
        # BUG FIX: Pass price_change_pct to PCR analyzer so it can use
        # trend-aware logic instead of always using contrarian flipping
        pcr_analysis = self.pcr_analyzer.analyze(chain, price_change_pct=price_change_pct)
        # BUG FIX: Pass price_change_pct to OI analyzer for trend-aware logic
        oi_analysis = self.oi_analyzer.analyze(chain, price_change_pct=price_change_pct)
        max_pain_analysis = self.max_pain_calculator.calculate(chain)
        
        # Derive gamma signal if analysis provided
        # BUG FIX: Pass price_change_pct to gamma signal for trend-aware logic
        gamma_signal, gamma_confidence = self._derive_gamma_signal(
            gamma_analysis, chain.spot_price, price_change_pct=price_change_pct
        )
        
        # Derive advanced metric signals (NEW - Section 6.5 implementation)
        oi_flow_signal, oi_flow_confidence = self._derive_oi_flow_signal(advanced_metrics)
        wall_conc_signal, wall_conc_confidence = self._derive_wall_concentration_signal(wall_analysis, whale_volume_analysis)
        pcr_strike_signal, pcr_strike_confidence = self._derive_pcr_strike_signal(advanced_metrics, chain.spot_price)
        whale_flow_signal, whale_flow_confidence = self._derive_whale_flow_signal(whale_volume_analysis)
        # IMPROVED: IV-003 - Derive IV term structure signal
        iv_term_signal, iv_term_confidence = self._derive_iv_term_structure_signal(advanced_metrics)
        
        # Debug logging
        sentiment_str = ""
        if sentiment_analysis:
            sentiment_str = f", Sentiment={sentiment_analysis.signal.value}({sentiment_analysis.signal_confidence:.2f})"
        gamma_str = f", Gamma={gamma_signal.value}({gamma_confidence:.2f})" if gamma_analysis else ""
        oi_flow_str = f", OIFlow={oi_flow_signal.value}({oi_flow_confidence:.2f})"
        whale_str = f", Whale={whale_flow_signal.value}({whale_flow_confidence:.2f})"
        logger.debug(
            f"Signal components for {chain.underlying}: "
            f"IV={iv_analysis.signal.value}({iv_analysis.confidence:.2f}), "
            f"PCR={pcr_analysis.signal.value}({pcr_analysis.confidence:.2f}), "
            f"OI={oi_analysis.signal.value}({oi_analysis.confidence:.2f}), "
            f"MaxPain={max_pain_analysis.signal.value}({max_pain_analysis.confidence:.2f})"
            f"{sentiment_str}{gamma_str}{oi_flow_str}{whale_str}"
        )
        
        # Combine signals
        # BUG FIX (Bug #6): Pass price_change_pct to _combine_signals for
        # trend validation — counter-trend signals get a confidence penalty
        direction, confidence, raw_score = self._combine_signals(
            iv_analysis=iv_analysis,
            pcr_analysis=pcr_analysis,
            oi_analysis=oi_analysis,
            max_pain_analysis=max_pain_analysis,
            sentiment_analysis=sentiment_analysis,
            gamma_signal=gamma_signal,
            gamma_confidence=gamma_confidence,
            oi_flow_signal=oi_flow_signal,
            oi_flow_confidence=oi_flow_confidence,
            wall_conc_signal=wall_conc_signal,
            wall_conc_confidence=wall_conc_confidence,
            pcr_strike_signal=pcr_strike_signal,
            pcr_strike_confidence=pcr_strike_confidence,
            whale_flow_signal=whale_flow_signal,
            whale_flow_confidence=whale_flow_confidence,
            # IMPROVED: IV-003 - Added IV term structure signal
            iv_term_signal=iv_term_signal,
            iv_term_confidence=iv_term_confidence,
            price_change_pct=price_change_pct,
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
            gamma_analysis=gamma_analysis,
        )
    
    def _derive_gamma_signal(
        self,
        gamma_analysis: Optional[GammaAnalysis],
        spot_price: float,
        price_change_pct: Optional[float] = None,
    ) -> tuple:
        """
        Derive trading signal from gamma exposure analysis.
        
        Gamma Exposure (GEX) Signal Logic:
        
        Theory:
        - Positive GEX: Dealers are short puts → must buy underlying to hedge
          This creates support behavior (dealers buy when price drops)
          → Generally BULLISH, but NOT always LONG
          
        - Negative GEX: Dealers are short calls → must sell underlying to hedge
          This creates resistance behavior (dealers sell when price rises)
          → BEARISH, good for SHORT signals
        
        BUG FIX: In POSITIVE GEX regime, the code previously ALWAYS returned
        LONG regardless of price action. However, positive GEX only means
        dealers provide SUPPORT at lower levels — it does NOT mean the market
        cannot go down. When price is actively dropping through support levels,
        a SHORT signal should be allowed.
        
        Updated Signal Generation:
        - POSITIVE GEX + price above gamma flip → LONG (support working)
        - POSITIVE GEX + price near/below gamma flip + price rising → LONG (support bounce)
        - POSITIVE GEX + price dropping through flip → SHORT (support failing, momentum bearish)
        - NEGATIVE GEX + price below gamma flip → SHORT (resistance working)
        - NEGATIVE GEX + price above gamma flip + price falling → SHORT (resistance pushing down)
        - NEGATIVE GEX + price rising through flip → LONG (resistance failing, momentum bullish)
        - DTE weight affects confidence (higher near expiry = stronger signal)
        
        Args:
            gamma_analysis: Gamma exposure analysis result
            spot_price: Current spot price
            price_change_pct: Price change percentage for trend context.
                Positive = price rising, Negative = price falling.
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        if not gamma_analysis:
            return SignalDirection.NEUTRAL, 0.0
        
        signal = SignalDirection.NEUTRAL
        confidence = 0.0
        flip_score = 0.0
        
        # Extract key metrics
        gex_regime = gamma_analysis.gex_regime
        gamma_flip = gamma_analysis.gamma_flip
        gamma_risk_score = gamma_analysis.gamma_risk_score
        dte_weight = gamma_analysis.dte_weight
        total_gex = gamma_analysis.total_gex
        
        # Determine price direction for trend-aware logic
        price_dropping = price_change_pct is not None and price_change_pct < -0.1
        price_rising = price_change_pct is not None and price_change_pct > 0.1
        
        # Determine signal based on GEX regime
        if gex_regime == "POSITIVE":
            # Dealers provide support (buy dips)
            # Generally LONG bias, but NOT always
            if gamma_flip and spot_price:
                if spot_price < gamma_flip:
                    # Price below gamma flip - support zone
                    if price_dropping:
                        # BUG FIX: Price dropping THROUGH support → SHORT
                        # Support is failing, momentum is bearish
                        signal = SignalDirection.SHORT
                        flip_distance = (gamma_flip - spot_price) / spot_price if spot_price > 0 else 0
                        flip_score = min(flip_distance * 10, 0.5)
                        logger.debug(
                            f"Gamma signal: +GEX, price BELOW flip + DROPPING={price_change_pct:.2f}% "
                            f"→ support failing → SHORT"
                        )
                    else:
                        # Price in support zone but stable/rising → LONG (bounce expected)
                        signal = SignalDirection.LONG
                        flip_distance = (gamma_flip - spot_price) / spot_price if spot_price > 0 else 0
                        flip_score = min(flip_distance * 10, 0.5)
                else:
                    # Price above gamma flip
                    if price_dropping:
                        # Price above flip but dropping → can still be SHORT
                        # Momentum is bearish even though regime is positive
                        signal = SignalDirection.SHORT
                        flip_score = 0.2
                        logger.debug(
                            f"Gamma signal: +GEX, price above flip + DROPPING={price_change_pct:.2f}% "
                            f"→ bearish momentum → SHORT (reduced confidence)"
                        )
                    else:
                        # Price above flip and stable/rising → LONG
                        signal = SignalDirection.LONG
                        flip_score = 0.2
            else:
                # No gamma flip available
                if price_dropping:
                    # No flip data but price is actively dropping → SHORT
                    signal = SignalDirection.SHORT
                    flip_score = 0.15
                    logger.debug(
                        f"Gamma signal: +GEX, no flip + DROPPING={price_change_pct:.2f}% "
                        f"→ bearish momentum overrides → SHORT"
                    )
                else:
                    # No flip, positive regime, price not dropping → LONG
                    signal = SignalDirection.LONG
                    flip_score = 0.3
            
            # Base confidence from gamma risk and DTE
            base_confidence = min(gamma_risk_score * 0.5 + 0.3, 0.8)
            
            # Reduce confidence for counter-regime signals
            if signal == SignalDirection.SHORT:
                base_confidence *= 0.7  # SHORT in positive GEX is weaker
            
        elif gex_regime == "NEGATIVE":
            # Dealers provide resistance (sell rallies)
            # Generally SHORT bias, but NOT always
            if gamma_flip and spot_price:
                if spot_price > gamma_flip:
                    # Price above gamma flip - resistance zone
                    if price_rising:
                        # Price rising THROUGH resistance → LONG
                        # Resistance is failing, momentum is bullish
                        signal = SignalDirection.LONG
                        flip_distance = (spot_price - gamma_flip) / spot_price if spot_price > 0 else 0
                        flip_score = min(flip_distance * 10, 0.5)
                        logger.debug(
                            f"Gamma signal: -GEX, price ABOVE flip + RISING={price_change_pct:.2f}% "
                            f"→ resistance failing → LONG"
                        )
                    else:
                        # Price in resistance zone but stable/falling → SHORT
                        signal = SignalDirection.SHORT
                        flip_distance = (spot_price - gamma_flip) / spot_price if spot_price > 0 else 0
                        flip_score = min(flip_distance * 10, 0.5)
                else:
                    # Price below gamma flip
                    if price_rising:
                        # Price below flip but rising → can still be LONG
                        signal = SignalDirection.LONG
                        flip_score = 0.2
                        logger.debug(
                            f"Gamma signal: -GEX, price below flip + RISING={price_change_pct:.2f}% "
                            f"→ bullish momentum → LONG (reduced confidence)"
                        )
                    else:
                        # Price below flip and falling → SHORT
                        signal = SignalDirection.SHORT
                        flip_score = 0.2
            else:
                # No gamma flip available
                if price_rising:
                    # No flip data but price is rising → LONG
                    signal = SignalDirection.LONG
                    flip_score = 0.15
                    logger.debug(
                        f"Gamma signal: -GEX, no flip + RISING={price_change_pct:.2f}% "
                        f"→ bullish momentum overrides → LONG"
                    )
                else:
                    # No flip, negative regime, price not rising → SHORT
                    signal = SignalDirection.SHORT
                    flip_score = 0.3
            
            base_confidence = min(gamma_risk_score * 0.5 + 0.3, 0.8)
            
            # Reduce confidence for counter-regime signals
            if signal == SignalDirection.LONG:
                base_confidence *= 0.7  # LONG in negative GEX is weaker
            
        else:  # NEUTRAL regime
            return SignalDirection.NEUTRAL, 0.3
        
        # Apply DTE weight to confidence
        # Higher DTE weight (near expiry) = more impactful gamma
        dte_adjusted_confidence = base_confidence * (0.5 + 0.5 * min(dte_weight, 2.0))
        
        # Final confidence
        confidence = min(dte_adjusted_confidence + flip_score, 0.9)
        
        return signal, round(confidence, 3)
    
    def _derive_oi_flow_signal(
        self,
        advanced_metrics: Optional[Dict[str, Any]],
    ) -> tuple:
        """
        Derive trading signal from OI flow analysis.
        
        OI Flow Signal Logic (Section 6.5 Priority 1):
        Uses the flow_type from oi_flow which combines both OI direction
        and price direction to correctly classify the flow:
        
        - LONG_BUILDUP:   OI↑ + Price↑ → New longs being created   → LONG signal
        - SHORT_BUILDUP:  OI↑ + Price↓ → New shorts being created  → SHORT signal
        - SHORT_COVERING: OI↓ + Price↑ → Shorts closing out        → LONG signal
        - LONG_UNWINDING: OI↓ + Price↓ → Longs liquidating         → SHORT signal
        - NEUTRAL:        No significant flow pattern                → NEUTRAL signal
        
        Confidence is based on the magnitude of OI change (larger OI change
        = stronger conviction in the flow direction).
        
        Args:
            advanced_metrics: Dict with oi_flow data (including flow_type and price_change_pct)
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        if not advanced_metrics:
            return SignalDirection.NEUTRAL, 0.0
        
        oi_flow = advanced_metrics.get("oi_flow")
        if not oi_flow:
            return SignalDirection.NEUTRAL, 0.0
        
        oi_change = oi_flow.get("oi_change_estimated", 0.0)
        
        # BUG FIX: Use flow_type (which incorporates price direction) instead of
        # only flow_direction. Previously, BUILDING was always hardcoded to LONG,
        # ignoring that OI building + price falling = SHORT_BUILDUP (bearish).
        flow_type = oi_flow.get("flow_type")
        
        if flow_type:
            # Use the detailed flow_type that combines OI + price direction
            if flow_type == "LONG_BUILDUP":
                # OI↑ + Price↑ → New long positions → BULLISH
                signal = SignalDirection.LONG
                confidence = min(abs(oi_change) / 20.0, 0.8)
            elif flow_type == "SHORT_BUILDUP":
                # OI↑ + Price↓ → New short positions → BEARISH
                signal = SignalDirection.SHORT
                confidence = min(abs(oi_change) / 20.0, 0.8)
            elif flow_type == "SHORT_COVERING":
                # OI↓ + Price↑ → Shorts closing → BULLISH (price rising from covering)
                signal = SignalDirection.LONG
                confidence = min(abs(oi_change) / 20.0, 0.8)
            elif flow_type == "LONG_UNWINDING":
                # OI↓ + Price↓ → Longs liquidating → BEARISH (price falling from selling)
                signal = SignalDirection.SHORT
                confidence = min(abs(oi_change) / 20.0, 0.8)
            else:
                signal = SignalDirection.NEUTRAL
                confidence = 0.0
        else:
            # Fallback: legacy path when flow_type is not available
            # Uses price_change_pct to determine direction
            flow_direction = oi_flow.get("flow_direction", "STABLE")
            price_change_pct = oi_flow.get("price_change_pct", 0.0)
            
            if flow_direction == "BUILDING":
                if price_change_pct > 0:
                    # OI building + price rising = LONG buildup
                    signal = SignalDirection.LONG
                else:
                    # OI building + price falling = SHORT buildup
                    signal = SignalDirection.SHORT
                confidence = min(abs(oi_change) / 20.0, 0.8)
            elif flow_direction == "UNWINDING":
                if price_change_pct > 0:
                    # OI falling + price rising = SHORT covering (bullish)
                    signal = SignalDirection.LONG
                else:
                    # OI falling + price falling = LONG unwinding (bearish)
                    signal = SignalDirection.SHORT
                confidence = min(abs(oi_change) / 20.0, 0.8)
            else:
                signal = SignalDirection.NEUTRAL
                confidence = 0.0
        
        return signal, round(confidence, 3)
    
    def _derive_wall_concentration_signal(
        self,
        wall_analysis: Optional[Any],
        whale_volume_analysis: Optional[Dict[str, Any]],
    ) -> tuple:
        """
        Derive trading signal from wall concentration analysis.
        
        Wall Concentration Signal Logic (Section 6.5 Priority 1):
        - High wall imbalance (put walls > call walls) = Support at lower strikes = LONG bias
        - High wall imbalance (call walls > put walls) = Resistance above = SHORT bias
        - Concentrated whale activity at specific strikes = directional conviction
        
        Args:
            wall_analysis: Wall detection analysis
            whale_volume_analysis: Whale volume analysis
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        signal = SignalDirection.NEUTRAL
        confidence = 0.0
        
        # Check wall imbalance
        if wall_analysis and hasattr(wall_analysis, 'wall_imbalance'):
            imbalance = wall_analysis.wall_imbalance
            
            # wall_imbalance > 0 = more put walls (support) = LONG bias
            # wall_imbalance < 0 = more call walls (resistance) = SHORT bias
            if imbalance > 0.3:
                signal = SignalDirection.LONG
                confidence = min(imbalance, 0.7)
            elif imbalance < -0.3:
                signal = SignalDirection.SHORT
                confidence = min(abs(imbalance), 0.7)
        
        # Boost confidence if whale concentration aligns
        if whale_volume_analysis:
            concentration = whale_volume_analysis.get("concentration", {})
            is_concentrated = concentration.get("is_concentrated", False)
            if is_concentrated and confidence > 0:
                confidence = min(confidence * 1.3, 0.85)  # Boost by 30%
        
        return signal, round(confidence, 3)
    
    def _derive_pcr_strike_signal(
        self,
        advanced_metrics: Optional[Dict[str, Any]],
        spot_price: float,
    ) -> tuple:
        """
        Derive trading signal from PCR by strike alignment.
        
        PCR Strike Alignment Logic (Section 6.5 Priority 1):
        - Put-heavy strikes near spot = potential support = LONG bias
        - Call-heavy strikes near spot = potential resistance = SHORT bias
        - Alignment with signal direction boosts confidence
        
        Args:
            advanced_metrics: Dict with pcr_by_strike data
            spot_price: Current spot price
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        if not advanced_metrics or not spot_price:
            return SignalDirection.NEUTRAL, 0.0
        
        pcr_by_strike = advanced_metrics.get("pcr_by_strike")
        if not pcr_by_strike:
            return SignalDirection.NEUTRAL, 0.0
        
        put_heavy_count = pcr_by_strike.get("put_heavy_count", 0)
        call_heavy_count = pcr_by_strike.get("call_heavy_count", 0)
        
        # Determine signal based on which strikes dominate
        if put_heavy_count > call_heavy_count * 1.5:
            # More put-heavy strikes = potential support = LONG bias
            signal = SignalDirection.LONG
            confidence = min((put_heavy_count - call_heavy_count) * 0.15, 0.6)
        elif call_heavy_count > put_heavy_count * 1.5:
            # More call-heavy strikes = potential resistance = SHORT bias
            signal = SignalDirection.SHORT
            confidence = min((call_heavy_count - put_heavy_count) * 0.15, 0.6)
        else:
            signal = SignalDirection.NEUTRAL
            confidence = 0.0
        
        return signal, round(confidence, 3)
    
    def _derive_whale_flow_signal(
        self,
        whale_volume_analysis: Optional[Dict[str, Any]],
    ) -> tuple:
        """
        Derive trading signal from whale money flow analysis.
        
        Whale Flow Signal Logic (Section 6.5 Priority 1):
        - Net positive call flow = whales buying calls = BULLISH
        - Net positive put flow = whales buying puts = BEARISH
        - Aggressive buyers/sellers indicate conviction
        - Time pattern (INCREASING_BUYING/SELLING) indicates momentum
        
        Args:
            whale_volume_analysis: Whale volume analysis from WhaleVolumeAnalyzer
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        if not whale_volume_analysis:
            return SignalDirection.NEUTRAL, 0.0
        
        summary = whale_volume_analysis.get("summary", {})
        flow = whale_volume_analysis.get("flow", {})
        
        # Extract key metrics
        overall_sentiment = summary.get("overall_sentiment", "NEUTRAL")
        time_pattern = summary.get("time_pattern", "UNKNOWN")
        aggressive_side = summary.get("aggressive_side", "UNKNOWN")
        
        call_flow_net = flow.get("call_flow", {}).get("net", 0)
        put_flow_net = flow.get("put_flow", {}).get("net", 0)
        
        # Determine signal
        signal = SignalDirection.NEUTRAL
        confidence = 0.0
        
        if overall_sentiment == "BULLISH":
            signal = SignalDirection.LONG
            # Base confidence from sentiment
            confidence = 0.5
            
            # Boost if increasing buying pattern
            if time_pattern in ["INCREASING_BUYING", "CONSISTENT_BUYING"]:
                confidence += 0.2
            
            # Boost if buyers are aggressive
            if aggressive_side == "BUYERS":
                confidence += 0.1
                
        elif overall_sentiment == "BEARISH":
            signal = SignalDirection.SHORT
            confidence = 0.5
            
            if time_pattern in ["INCREASING_SELLING", "CONSISTENT_SELLING"]:
                confidence += 0.2
            
            if aggressive_side == "SELLERS":
                confidence += 0.1
        
        # Scale confidence by flow magnitude (if available)
        total_flow = abs(call_flow_net) + abs(put_flow_net)
        if total_flow > 0:
            flow_ratio = (abs(call_flow_net) - abs(put_flow_net)) / total_flow
            confidence = confidence * (1 + abs(flow_ratio) * 0.3)
        
        return signal, round(min(confidence, 0.85), 3)
    
    def _derive_iv_term_structure_signal(
        self,
        advanced_metrics: Optional[Dict[str, Any]],
    ) -> tuple:
        """
        IMPROVED: IV-003 - Derive trading signal from IV term structure analysis.
        
        IV Term Structure Signal Logic:
        - INVERTED (Short IV > Long IV): Near-term volatility expected
          - Strong inversion: Prepare for significant price move
          - Direction determined by other signals
        - UPWARD (Long IV > Short IV): Normal term structure
          - Standard market conditions
        - FLAT: Uniform IV expectations
        
        Signal Weight:
        - IV term structure is primarily a volatility indicator
        - Direction is typically NEUTRAL (use other signals for direction)
        - Confidence indicates expected volatility magnitude
        
        Args:
            advanced_metrics: Dict with iv_term_structure data
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        if not advanced_metrics:
            return SignalDirection.NEUTRAL, 0.0
        
        iv_term_structure = advanced_metrics.get("iv_term_structure")
        if not iv_term_structure:
            return SignalDirection.NEUTRAL, 0.0
        
        shape = iv_term_structure.get("shape", "INSUFFICIENT_DATA")
        term_structure = iv_term_structure.get("term_structure", [])
        
        if shape == "INSUFFICIENT_DATA" or shape == "SINGLE_EXPIRY" or shape == "AGGREGATE":
            return SignalDirection.NEUTRAL, 0.0
        
        # Calculate inversion ratio if we have multiple expiries
        if len(term_structure) >= 2:
            short_iv = term_structure[0].get("atm_iv", 0)
            long_iv = term_structure[-1].get("atm_iv", 0)
            
            if long_iv > 0:
                inversion_ratio = (short_iv - long_iv) / long_iv
            else:
                inversion_ratio = 0.0
            
            if shape == "INVERTED":
                # Inverted term indicate near-term volatility
                # Use inversion magnitude for confidence
                if inversion_ratio > 0.3:
                    return SignalDirection.NEUTRAL, 0.5  # High volatility expected
                elif inversion_ratio > 0.15:
                    return SignalDirection.NEUTRAL, 0.35
                else:
                    return SignalDirection.NEUTRAL, 0.2
            
            elif shape == "UPWARD":
                # Normal upward sloping
                if long_iv > short_iv * 1.3:
                    return SignalDirection.NEUTRAL, 0.15
                else:
                    return SignalDirection.NEUTRAL, 0.1
            
            else:  # FLAT
                return SignalDirection.NEUTRAL, 0.05
        
        return SignalDirection.NEUTRAL, 0.0
    
    def _combine_signals(
        self,
        iv_analysis: IVAnalysis,
        pcr_analysis: PCRAnalysis,
        oi_analysis: OIAnalysis,
        max_pain_analysis: MaxPainAnalysis,
        sentiment_analysis: Optional[SentimentAnalysis] = None,
        gamma_signal: SignalDirection = SignalDirection.NEUTRAL,
        gamma_confidence: float = 0.0,
        oi_flow_signal: SignalDirection = SignalDirection.NEUTRAL,
        oi_flow_confidence: float = 0.0,
        wall_conc_signal: SignalDirection = SignalDirection.NEUTRAL,
        wall_conc_confidence: float = 0.0,
        pcr_strike_signal: SignalDirection = SignalDirection.NEUTRAL,
        pcr_strike_confidence: float = 0.0,
        whale_flow_signal: SignalDirection = SignalDirection.NEUTRAL,
        whale_flow_confidence: float = 0.0,
        # IMPROVED: IV-003 - Added IV term structure signal parameters
        iv_term_signal: SignalDirection = SignalDirection.NEUTRAL,
        iv_term_confidence: float = 0.0,
        # BUG FIX (Bug #6): Price trend for signal validation
        price_change_pct: Optional[float] = None,
    ) -> tuple:
        """
        Combine multiple signals into one.
        
        BUG FIX (Bug #6): Added price trend validation. Previously, the raw_score
        threshold was symmetric (+/-0.15), but the LONG bias from other bugs meant
        the score easily exceeded +0.15 while rarely reaching -0.15. Even after
        fixing Bugs #1-#5, a trend validation step is added as a safety net:
        - If the combined signal is LONG but price is actively dropping, apply a
          confidence penalty (the market disagrees with the signal).
        - If the combined signal is SHORT but price is actively rising, apply a
          confidence penalty.
        - If the signal aligns with the price trend, apply a small confidence boost.
        
        Args:
            iv_analysis: IV analysis result
            pcr_analysis: PCR analysis result
            oi_analysis: OI analysis result
            max_pain_analysis: Max Pain analysis result
            sentiment_analysis: Optional sentiment analysis from L/S ratios
            gamma_signal: Signal derived from gamma exposure
            gamma_confidence: Confidence of gamma signal
            oi_flow_signal: Signal from OI flow analysis (NEW)
            oi_flow_confidence: Confidence of OI flow signal
            wall_conc_signal: Signal from wall concentration (NEW)
            wall_conc_confidence: Confidence of wall concentration signal
            pcr_strike_signal: Signal from PCR strike alignment (NEW)
            pcr_strike_confidence: Confidence of PCR strike signal
            whale_flow_signal: Signal from whale money flow (NEW)
            whale_flow_confidence: Confidence of whale flow signal
            iv_term_signal: Signal from IV term structure (IV-003)
            iv_term_confidence: Confidence of IV term structure signal
            price_change_pct: Optional price change % for trend validation.
                Positive = price rising, Negative = price falling.
            
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
        
        # Add sentiment signal if available
        # BUG FIX: Removed contrarian flip — sentiment.py's _determine_signal() already
        # produces the correct trading direction. When L/S ratio > 3.0 (extreme long
        # positioning), it correctly returns SHORT with is_contrarian=True. Flipping
        # it back here (-(-1.0) = +1.0) would make it contribute as LONG, which is
        # wrong. The contrarian flag is informational only; the signal direction is
        # already the correct trading direction.
        if sentiment_analysis:
            sentiment_numeric = self._signal_to_numeric(sentiment_analysis.signal)
            signals["sentiment"] = sentiment_numeric * sentiment_analysis.signal_confidence
        else:
            signals["sentiment"] = 0.0
        
        # Add gamma signal
        signals["gamma"] = self._signal_to_numeric(gamma_signal) * gamma_confidence
        
        # Add advanced metric signals (NEW - Section 6.5 implementation)
        signals["oi_flow"] = self._signal_to_numeric(oi_flow_signal) * oi_flow_confidence
        signals["wall_conc"] = self._signal_to_numeric(wall_conc_signal) * wall_conc_confidence
        signals["pcr_strike"] = self._signal_to_numeric(pcr_strike_signal) * pcr_strike_confidence
        signals["whale_flow"] = self._signal_to_numeric(whale_flow_signal) * whale_flow_confidence
        # IMPROVED: IV-003 - Add IV term structure signal
        signals["iv_term"] = self._signal_to_numeric(iv_term_signal) * iv_term_confidence
        
        # Apply weights (core + advanced)
        weighted_signals = {
            "iv": signals["iv"] * self.config.iv_weight,
            "pcr": signals["pcr"] * self.config.pcr_weight,
            "oi": signals["oi"] * self.config.oi_weight,
            "max_pain": signals["max_pain"] * self.config.max_pain_weight,
            "sentiment": signals["sentiment"] * self.config.sentiment_weight,
            "gamma": signals["gamma"] * self.config.gamma_weight,
            # Advanced metrics weights (NEW)
            "oi_flow": signals["oi_flow"] * self.config.oi_flow_weight,
            "wall_conc": signals["wall_conc"] * self.config.wall_concentration_weight,
            "pcr_strike": signals["pcr_strike"] * self.config.pcr_strike_alignment_weight,
            "whale_flow": signals["whale_flow"] * self.config.whale_flow_weight,
            # IMPROVED: IV-003 - Add IV term structure weight
            "iv_term": signals["iv_term"] * self.config.iv_term_structure_weight,
        }
        
        # Calculate raw score
        raw_score = sum(weighted_signals.values())
        
        # Calculate agreement (include all signals including advanced)
        signal_list = [
            iv_analysis.signal,
            pcr_analysis.signal,
            oi_analysis.signal,
            max_pain_analysis.signal,
        ]
        if sentiment_analysis:
            signal_list.append(sentiment_analysis.signal)
        if gamma_signal != SignalDirection.NEUTRAL:
            signal_list.append(gamma_signal)
        # Add advanced signals to agreement calculation
        if oi_flow_signal != SignalDirection.NEUTRAL:
            signal_list.append(oi_flow_signal)
        if wall_conc_signal != SignalDirection.NEUTRAL:
            signal_list.append(wall_conc_signal)
        if pcr_strike_signal != SignalDirection.NEUTRAL:
            signal_list.append(pcr_strike_signal)
        if whale_flow_signal != SignalDirection.NEUTRAL:
            signal_list.append(whale_flow_signal)
        
        agreement = self._calculate_agreement(*signal_list)
        
        # Determine direction
        if raw_score > 0.15:
            direction = SignalDirection.LONG
        elif raw_score < -0.15:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL
        
        # Calculate confidence (Section 6.6 formula with enhancements)
        # Base confidence from signal strength
        base_confidence = min(abs(raw_score) * 2, 1.0)
        
        # Adjust by agreement (more agreement = higher confidence)
        confidence = base_confidence * (0.5 + 0.5 * agreement)
        
        # BUG FIX (Bug #6): Trend validation filter
        # If the combined signal direction opposes the clear price trend,
        # apply a confidence penalty. This acts as a safety net against
        # residual LONG bias that may remain even after fixing Bugs #1-#5.
        #
        # Logic:
        # - LONG signal + price dropping hard → penalize confidence (market says otherwise)
        # - SHORT signal + price rising hard → penalize confidence (market says otherwise)
        # - LONG signal + price rising → slight boost (trend confirms)
        # - SHORT signal + price dropping → slight boost (trend confirms)
        # - No trend data → no adjustment
        if price_change_pct is not None and direction != SignalDirection.NEUTRAL:
            # Define clear trend thresholds
            strong_drop = price_change_pct < -0.3   # > 0.3% drop = clear bearish
            strong_rise = price_change_pct > 0.3    # > 0.3% rise = clear bullish
            moderate_drop = price_change_pct < -0.1  # > 0.1% drop
            moderate_rise = price_change_pct > 0.1   # > 0.1% rise
            
            if direction == SignalDirection.LONG:
                if strong_drop:
                    # Strong opposition: LONG signal but market clearly bearish
                    confidence *= 0.5
                    logger.debug(
                        f"Trend validation: LONG signal opposes strong price drop "
                        f"({price_change_pct:.2f}%) → confidence penalized by 50%"
                    )
                elif moderate_drop:
                    # Moderate opposition
                    confidence *= 0.7
                    logger.debug(
                        f"Trend validation: LONG signal opposes moderate price drop "
                        f"({price_change_pct:.2f}%) → confidence penalized by 30%"
                    )
                elif moderate_rise:
                    # Trend confirms
                    confidence = min(confidence * 1.1, 1.0)
                    logger.debug(
                        f"Trend validation: LONG signal confirmed by price rising "
                        f"({price_change_pct:.2f}%) → confidence boosted by 10%"
                    )
            
            elif direction == SignalDirection.SHORT:
                if strong_rise:
                    # Strong opposition: SHORT signal but market clearly bullish
                    confidence *= 0.5
                    logger.debug(
                        f"Trend validation: SHORT signal opposes strong price rise "
                        f"({price_change_pct:.2f}%) → confidence penalized by 50%"
                    )
                elif moderate_rise:
                    # Moderate opposition
                    confidence *= 0.7
                    logger.debug(
                        f"Trend validation: SHORT signal opposes moderate price rise "
                        f"({price_change_pct:.2f}%) → confidence penalized by 30%"
                    )
                elif moderate_drop:
                    # Trend confirms
                    confidence = min(confidence * 1.1, 1.0)
                    logger.debug(
                        f"Trend validation: SHORT signal confirmed by price dropping "
                        f"({price_change_pct:.2f}%) → confidence boosted by 10%"
                    )
        
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
        
        if signal.gamma_analysis:
            breakdown["components"]["gamma"] = {
                "gex_regime": signal.gamma_analysis.gex_regime,
                "dealer_hedge_pressure": signal.gamma_analysis.dealer_hedge_pressure,
                "gamma_flip": round(signal.gamma_analysis.gamma_flip, 2) if signal.gamma_analysis.gamma_flip else None,
                "gamma_risk_score": round(signal.gamma_analysis.gamma_risk_score, 3),
                "dte_days": round(signal.gamma_analysis.dte_days, 1),
                "dte_weight": round(signal.gamma_analysis.dte_weight, 2),
                "expiry_imminent": signal.gamma_analysis.expiry_imminent,
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
