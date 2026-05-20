"""
Open Interest (OI) analyzer for Options data.

This module analyzes Open Interest from Options data to understand
market positioning and potential price moves.

OI Analysis:
- OI concentration at strikes = Price magnets
- OI changes = New positions being opened/closed
- Call vs Put OI imbalance = Directional bias

Signal Logic (Trend-Aware):
- Put OI dominance + price falling: Trend confirms bearish → SHORT (follow trend)
- Put OI dominance + price rising: Trend opposes → LONG (contrarian, reduced confidence)
- Call OI dominance + price rising: Trend confirms bullish → LONG (follow trend)
- Call OI dominance + price falling: Trend opposes → SHORT (contrarian, reduced confidence)
- Without price trend data: Falls back to contrarian logic (legacy)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    OIAnalysis,
    SignalDirection,
)
from binance_signal_generator.config import load_config, OIAnalyzerConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


class OIAnalyzer:
    """
    Analyzes Open Interest from Options data.

    OI Analysis Methods:
    1. Total OI: Overall market participation
    2. OI by Strike: Concentration levels
    3. Call/Put OI: Directional bias
    4. OI Changes: Position flow (requires historical data)

    Signal Generation (Trend-Aware):
    - When price trend CONFIRMS OI imbalance: Follow the trend (crowd is right)
    - When price trend OPPOSES OI imbalance: Contrarian signal with reduced confidence
    - Without price data: Falls back to pure contrarian logic

    The trend-aware approach prevents the systematic LONG bias that occurred
    when contrarian logic always flipped put-heavy OI to LONG, even when
    the market was actively trending down.

    Attributes:
        config: OI analysis configuration (loaded from config.yaml)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize OI analyzer.

        Config is loaded from config.yaml via load_config().
        Single source of truth - no fallback defaults.

        Args:
            config_path: Optional path to config file
        """
        loaded_config = load_config(config_path)
        self.config = loaded_config.analysis.oi_analyzer_config

        logger.info(
            "OI analyzer initialized",
            extra={
                "data": {
                    "high_oi_concentration": self.config.high_oi_concentration,
                }
            },
        )

    def analyze(
        self,
        chain: OptionsChain,
        price_change_pct: Optional[float] = None,
    ) -> OIAnalysis:
        """
        Analyze OI from options chain.

        Args:
            chain: Options chain data
            price_change_pct: Optional price change percentage for trend context.
                When provided, the signal logic adjusts between contrarian and
                trend-following based on whether price trend confirms or opposes
                the OI imbalance direction.

        Returns:
            OIAnalysis with OI metrics and signal
        """
        total_oi = chain.total_call_oi + chain.total_put_oi

        if total_oi < self.config.min_total_oi:
            logger.warning(f"Insufficient OI for analysis: {total_oi}")
            return self._create_empty_analysis(chain.underlying)

        # Calculate OI concentrations
        call_concentration = chain.total_call_oi / total_oi if total_oi > 0 else 0.5
        put_concentration = chain.total_put_oi / total_oi if total_oi > 0 else 0.5

        # Find OI walls
        call_walls, put_walls = self._find_oi_walls(chain)

        # Generate signal with trend context
        signal, confidence = self._generate_signal(
            call_concentration=call_concentration,
            put_concentration=put_concentration,
            call_walls=call_walls,
            put_walls=put_walls,
            spot_price=chain.spot_price,
            price_change_pct=price_change_pct,
            num_strikes=len(chain.strikes),
        )

        return OIAnalysis(
            symbol=chain.underlying,
            timestamp=datetime.utcnow(),
            total_oi=float(total_oi),
            oi_change_24h=0.0,  # Requires historical data
            call_oi_concentration=call_concentration,
            put_oi_concentration=put_concentration,
            signal=signal,
            confidence=confidence,
        )

    def _find_oi_walls(
        self,
        chain: OptionsChain,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Find OI walls (strikes with high concentration).

        Args:
            chain: Options chain

        Returns:
            Tuple of (call_walls, put_walls)
        """
        total_oi = chain.total_call_oi + chain.total_put_oi

        call_walls = []
        put_walls = []

        for strike_price, strike_data in chain.strikes.items():
            # Calculate concentration
            call_oi_pct = strike_data.call.open_interest / total_oi if total_oi > 0 else 0
            put_oi_pct = strike_data.put.open_interest / total_oi if total_oi > 0 else 0

            # Check for call walls
            if call_oi_pct >= self.config.high_oi_concentration:
                call_walls.append(
                    {
                        "strike": strike_price,
                        "oi": strike_data.call.open_interest,
                        "concentration": call_oi_pct,
                        "distance_from_spot": (strike_price - chain.spot_price) / chain.spot_price,
                    }
                )

            # Check for put walls
            if put_oi_pct >= self.config.high_oi_concentration:
                put_walls.append(
                    {
                        "strike": strike_price,
                        "oi": strike_data.put.open_interest,
                        "concentration": put_oi_pct,
                        "distance_from_spot": (strike_price - chain.spot_price) / chain.spot_price,
                    }
                )

        # Sort by concentration
        call_walls.sort(key=lambda x: x["concentration"], reverse=True)
        put_walls.sort(key=lambda x: x["concentration"], reverse=True)

        return call_walls, put_walls

    def _generate_signal(
        self,
        call_concentration: float,
        put_concentration: float,
        call_walls: List[Dict],
        put_walls: List[Dict],
        spot_price: float,
        price_change_pct: Optional[float] = None,
        num_strikes: int = 20,
    ) -> Tuple[SignalDirection, float]:
        """
        Generate trading signal from OI analysis with trend context.

        Signal Logic (Trend-Aware):

        OI imbalance alone is traditionally a contrarian indicator:
        - More put OI (imbalance > 0.15): Bearish positioning → Contrarian LONG
        - More call OI (imbalance < -0.15): Bullish positioning → Contrarian SHORT

        BUG FIX: When price trend CONFIRMS the OI imbalance (e.g., put-heavy
        + price falling), the crowd is RIGHT and contrarian logic is wrong.
        In a trending market, contrarian signals should be suppressed and
        replaced with trend-following signals.

        Decision matrix:
        ┌───────────────────┬───────────────┬──────────────────────────────────┐
        │ OI Imbalance      │ Price Trend   │ Action                           │
        ├───────────────────┼───────────────┼──────────────────────────────────┤
        │ Put-heavy (bear)  │ Price DOWN    │ Trend confirms → SHORT (follow)  │
        │ Put-heavy (bear)  │ Price UP      │ Trend opposes → LONG (contrarian)│
        │ Put-heavy (bear)  │ No trend data → LONG (contrarian, legacy)   │
        │ Call-heavy (bull) │ Price UP      │ Trend confirms → LONG (follow)   │
        │ Call-heavy (bull) │ Price DOWN    │ Trend opposes → SHORT (contrarian)│
        │ Call-heavy (bull) │ No trend data → SHORT (contrarian, legacy)  │
        └───────────────────┴───────────────┴──────────────────────────────────┘

        Confidence adjustment:
        - Trend-following: confidence based on imbalance + trend strength
        - Contrarian (trend opposes): confidence reduced by 40%
        - No trend data: uses legacy contrarian logic (unchanged)

        Args:
            call_concentration: Call OI as % of total
            put_concentration: Put OI as % of total
            call_walls: List of call OI walls
            put_walls: List of put OI walls
            spot_price: Current spot price
            price_change_pct: Price change percentage for trend context.
                Positive = price rising, Negative = price falling.

        Returns:
            Tuple of (SignalDirection, confidence)
        """
        # Calculate imbalance
        imbalance = put_concentration - call_concentration

        # Check for walls near spot (within 5%)
        nearby_call_walls = [w for w in call_walls if abs(w["distance_from_spot"]) < 0.05]
        nearby_put_walls = [w for w in put_walls if abs(w["distance_from_spot"]) < 0.05]

        # Determine if OI has significant imbalance
        # FIX: Make imbalance threshold adaptive based on number of strikes
        # With 70+ strikes, 15% imbalance is extreme; with 10 strikes, 15% is normal
        # Scale: more strikes → lower threshold (more distributed OI)
        adaptive_imbalance = max(0.05, 0.20 - num_strikes * 0.002)  # e.g., 70 strikes → 0.06
        put_heavy = imbalance > adaptive_imbalance
        call_heavy = imbalance < -adaptive_imbalance

        # Calculate base confidence from imbalance magnitude
        if put_heavy or call_heavy:
            base_confidence = min(0.5 + abs(imbalance), 0.8)
        else:
            base_confidence = 0.0

        # Apply trend-aware signal logic for significant imbalances
        # FIX: Use ATR-based thresholds instead of hardcoded 0.01%
        trend_threshold = 0.15  # Conservative for crypto
        if put_heavy or call_heavy:
            if price_change_pct is not None and abs(price_change_pct) > trend_threshold:
                # We have price trend data - use trend-aware logic
                price_trending_down = price_change_pct < -trend_threshold
                price_trending_up = price_change_pct > trend_threshold

                if put_heavy:
                    # More puts = bearish positioning
                    if price_trending_down:
                        # Price IS falling → crowd is RIGHT → trend-following SHORT
                        trend_strength = min(abs(price_change_pct) / 3.0, 0.3)
                        confidence = min(base_confidence + trend_strength, 0.85)
                        logger.debug(
                            f"OI signal: PUT-heavy={imbalance:.2f} + price DOWN={price_change_pct:.2f}% "
                            f"→ trend confirms bearish → SHORT (follow trend)"
                        )
                        return SignalDirection.SHORT, confidence
                    else:
                        # Price is rising → crowd may be wrong → contrarian LONG
                        # FIX: Scale penalty with trend strength
                        penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.3)
                        confidence = base_confidence * penalty
                        logger.debug(
                            f"OI signal: PUT-heavy={imbalance:.2f} + price UP={price_change_pct:.2f}% "
                            f"→ trend opposes bearish → LONG (contrarian, reduced confidence)"
                        )
                        return SignalDirection.LONG, confidence

                elif call_heavy:
                    # More calls = bullish positioning
                    if price_trending_up:
                        # Price IS rising → crowd is RIGHT → trend-following LONG
                        trend_strength = min(abs(price_change_pct) / 3.0, 0.3)
                        confidence = min(base_confidence + trend_strength, 0.85)
                        logger.debug(
                            f"OI signal: CALL-heavy={imbalance:.2f} + price UP={price_change_pct:.2f}% "
                            f"→ trend confirms bullish → LONG (follow trend)"
                        )
                        return SignalDirection.LONG, confidence
                    else:
                        # Price is falling → crowd may be wrong → contrarian SHORT
                        # FIX: Scale penalty with trend strength
                        penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.3)
                        confidence = base_confidence * penalty
                        logger.debug(
                            f"OI signal: CALL-heavy={imbalance:.2f} + price DOWN={price_change_pct:.2f}% "
                            f"→ trend opposes bullish → SHORT (contrarian, reduced confidence)"
                        )
                        return SignalDirection.SHORT, confidence

            # No trend data → use legacy contrarian logic
            if put_heavy:
                return SignalDirection.LONG, base_confidence
            elif call_heavy:
                return SignalDirection.SHORT, base_confidence

        # Check for wall effects (no significant imbalance)
        if nearby_call_walls and not nearby_put_walls:
            # Call wall nearby - resistance
            return SignalDirection.SHORT, 0.4

        elif nearby_put_walls and not nearby_call_walls:
            # Put wall nearby - support
            return SignalDirection.LONG, 0.4

        else:
            return SignalDirection.NEUTRAL, 0.2

    def _create_empty_analysis(self, symbol: str) -> OIAnalysis:
        """Create empty OI analysis for insufficient data."""
        return OIAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            total_oi=0.0,
            oi_change_24h=0.0,
            call_oi_concentration=0.5,
            put_oi_concentration=0.5,
            signal=SignalDirection.NEUTRAL,
            confidence=0.0,
        )

    def get_oi_distribution(
        self,
        chain: OptionsChain,
    ) -> Dict[str, Any]:
        """
        Get OI distribution across strikes.

        Args:
            chain: Options chain

        Returns:
            Dictionary with OI distribution
        """
        distribution = []
        total_oi = chain.total_call_oi + chain.total_put_oi

        for strike_price, strike_data in chain.strikes.items():
            call_oi = strike_data.call.open_interest
            put_oi = strike_data.put.open_interest

            distribution.append(
                {
                    "strike": strike_price,
                    "call_oi": call_oi,
                    "put_oi": put_oi,
                    "total_oi": call_oi + put_oi,
                    "call_pct": call_oi / total_oi if total_oi > 0 else 0,
                    "put_pct": put_oi / total_oi if total_oi > 0 else 0,
                    "distance_from_spot_pct": round(
                        (strike_price - chain.spot_price) / chain.spot_price * 100, 2
                    ),
                }
            )

        # Sort by strike
        distribution.sort(key=lambda x: x["strike"])

        return {
            "total_oi": total_oi,
            "total_call_oi": chain.total_call_oi,
            "total_put_oi": chain.total_put_oi,
            "strikes": distribution,
        }

    def find_max_pain_strike(self, chain: OptionsChain) -> float:
        """
        Find the max pain strike from OI data.

        Max Pain is the strike where option holders have the most pain
        (least profit), which tends to act as a magnet.

        Args:
            chain: Options chain

        Returns:
            Estimated max pain strike
        """
        if not chain.strikes:
            return chain.spot_price

        # Calculate pain at each strike
        pain_by_strike = {}

        for test_strike in chain.strikes.keys():
            total_pain = 0

            for strike_price, strike_data in chain.strikes.items():
                # Pain for calls (strike - test_strike if positive)
                if test_strike < strike_price:
                    call_pain = strike_data.call.open_interest * (strike_price - test_strike)
                else:
                    call_pain = 0

                # Pain for puts (test_strike - strike if positive)
                if test_strike > strike_price:
                    put_pain = strike_data.put.open_interest * (test_strike - strike_price)
                else:
                    put_pain = 0

                total_pain += call_pain + put_pain

            pain_by_strike[test_strike] = total_pain

        # Find strike with max pain
        max_pain_strike = max(pain_by_strike, key=pain_by_strike.get)

        return max_pain_strike

    def get_oi_summary(self, analysis: OIAnalysis) -> Dict[str, Any]:
        """
        Get summary of OI analysis.

        Args:
            analysis: OI analysis result

        Returns:
            Dictionary with OI summary
        """
        return {
            "symbol": analysis.symbol,
            "total_oi": int(analysis.total_oi),
            "call_oi_concentration": round(analysis.call_oi_concentration, 3),
            "put_oi_concentration": round(analysis.put_oi_concentration, 3),
            "oi_imbalance": round(
                analysis.put_oi_concentration - analysis.call_oi_concentration, 3
            ),
            "signal": analysis.signal.value,
            "confidence": round(analysis.confidence, 2),
        }

    def analyze_oi_flow(
        self,
        current_oi: float,
        previous_oi: float,
        current_price: float,
        previous_price: float,
    ) -> Dict[str, Any]:
        """
        Analyze OI flow for trend signals.

        Args:
            current_oi: Current total OI
            previous_oi: Previous total OI
            current_price: Current price
            previous_price: Previous price

        Returns:
            Dictionary with OI flow analysis
        """
        oi_change = current_oi - previous_oi
        oi_change_pct = (oi_change / previous_oi) * 100 if previous_oi > 0 else 0

        price_change = current_price - previous_price
        price_change_pct = (price_change / previous_price) * 100 if previous_price > 0 else 0

        # Determine flow type
        if oi_change > 0 and price_change > 0:
            flow_type = "LONG_BUILDUP"
            interpretation = "New long positions being created - bullish"
        elif oi_change > 0 and price_change < 0:
            flow_type = "SHORT_BUILDUP"
            interpretation = "New short positions being created - bearish"
        elif oi_change < 0 and price_change > 0:
            flow_type = "SHORT_COVERING"
            interpretation = "Shorts closing - bearish unwinding"
        elif oi_change < 0 and price_change < 0:
            flow_type = "LONG_UNWINDING"
            interpretation = "Longs closing - bullish unwinding"
        else:
            flow_type = "NEUTRAL"
            interpretation = "No significant flow pattern"

        return {
            "oi_change": int(oi_change),
            "oi_change_pct": round(oi_change_pct, 2),
            "price_change": round(price_change, 4),
            "price_change_pct": round(price_change_pct, 2),
            "flow_type": flow_type,
            "interpretation": interpretation,
        }
