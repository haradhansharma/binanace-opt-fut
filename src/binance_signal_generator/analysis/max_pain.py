"""
Max Pain calculator for Options data.

This module calculates the Max Pain strike from Options data.
Max Pain is the strike price where option holders (buyers) would
experience the maximum financial loss, while option writers would
profit the most.

Max Pain Theory:
- Market makers have incentive to push price toward max pain
- Acts as a "magnet" for price near expiry
- Distance from max pain can indicate potential moves
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import math

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    MaxPainAnalysis,
    SignalDirection,
)
from binance_signal_generator.config import load_config, MaxPainAnalyzerConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


class MaxPainCalculator:
    """
    Calculates Max Pain from Options data.

    Max Pain Calculation:
    1. For each strike, calculate total pain (intrinsic value of all options)
    2. Find strike with maximum pain for option holders
    3. This strike is the "max pain" level

    Signal Generation:
    - Price below max pain + close to expiry = Bullish (price may rise to max pain)
    - Price above max pain + close to expiry = Bearish (price may fall to max pain)
    - Far from max pain = Weak signal

    Attributes:
        config: Max Pain calculation configuration (loaded from config.yaml)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Max Pain calculator.

        Config is loaded from config.yaml via load_config().
        Single source of truth - no fallback defaults.

        Args:
            config_path: Optional path to config file
        """
        loaded_config = load_config(config_path)
        self.config = loaded_config.analysis.max_pain_analyzer_config

        logger.info(
            "Max Pain calculator initialized",
            extra={
                "data": {
                    "distance_threshold": self.config.distance_threshold,
                }
            },
        )

    def calculate(self, chain: OptionsChain) -> MaxPainAnalysis:
        """
        Calculate Max Pain from options chain.

        Args:
            chain: Options chain data

        Returns:
            MaxPainAnalysis with max pain metrics and signal
        """
        if len(chain.strikes) < self.config.min_strikes:
            logger.warning(f"Insufficient strikes for Max Pain: {len(chain.strikes)}")
            return self._create_empty_analysis(chain.underlying, chain.spot_price)

        # Calculate pain at each strike
        pain_data = self._calculate_pain_by_strike(chain)

        # Find max pain strike
        max_pain_strike = max(pain_data, key=pain_data.get)
        max_pain_value = pain_data[max_pain_strike]

        # Calculate component pain values
        call_pain, put_pain = self._calculate_component_pain(chain, max_pain_strike)

        # Calculate distance
        distance_pct = (chain.spot_price - max_pain_strike) / max_pain_strike * 100

        # Calculate magnet strength
        magnet_strength = self._calculate_magnet_strength(
            max_pain_strike=max_pain_strike,
            spot_price=chain.spot_price,
            expiry=chain.expiry,
            total_oi=chain.total_call_oi + chain.total_put_oi,
        )

        # Generate signal
        signal, confidence = self._generate_signal(
            max_pain_strike=max_pain_strike,
            spot_price=chain.spot_price,
            distance_pct=distance_pct,
            magnet_strength=magnet_strength,
        )

        return MaxPainAnalysis(
            symbol=chain.underlying,
            timestamp=datetime.utcnow(),
            max_pain_strike=max_pain_strike,
            current_price=chain.spot_price,
            distance_pct=distance_pct,
            call_pain=call_pain,
            put_pain=put_pain,
            signal=signal,
            confidence=confidence,
            magnet_strength=magnet_strength,
        )

    def _calculate_pain_by_strike(
        self,
        chain: OptionsChain,
    ) -> Dict[float, float]:
        """
        Calculate pain value at each strike.

        Pain = Sum of intrinsic values of all options at that strike.
        Higher pain = more option holders lose money if price reaches that strike.

        Note: We limit test strikes to ±30% of spot price to avoid skewing
        the calculation with extreme OTM strikes that have minimal relevance
        for trading signals.

        Args:
            chain: Options chain

        Returns:
            Dictionary mapping strike to pain value
        """
        pain_by_strike = {}

        # Get sorted strikes
        all_strikes = sorted(chain.strikes.keys())

        if not all_strikes:
            return {}

        # Filter strikes to reasonable range around spot price (±30%)
        # This prevents extreme OTM strikes from skewing the max pain calculation
        spot = chain.spot_price
        min_strike = spot * 0.70  # 30% below spot
        max_strike = spot * 1.30  # 30% above spot

        test_strikes = [s for s in all_strikes if min_strike <= s <= max_strike]

        # If no strikes in range, fall back to all strikes
        if not test_strikes:
            test_strikes = all_strikes
            logger.warning(
                f"No strikes within ±30% of spot ({spot}) for max pain calculation. "
                f"Using all {len(all_strikes)} strikes."
            )

        logger.debug(
            f"Max pain: testing {len(test_strikes)}/{len(all_strikes)} strikes "
            f"(range: {min(test_strikes):.0f} - {max(test_strikes):.0f}, spot: {spot:.0f})"
        )

        # For each potential settlement price (each strike in range)
        for test_strike in test_strikes:
            total_pain = 0.0

            for strike_price, strike_data in chain.strikes.items():
                # Calculate call pain
                # Call holders lose if test_strike < strike_price
                # Pain = max(strike - test_strike, 0) * OI
                if test_strike < strike_price:
                    call_pain = (strike_price - test_strike) * strike_data.call.open_interest
                else:
                    call_pain = 0

                # Calculate put pain
                # Put holders lose if test_strike > strike_price
                # Pain = max(test_strike - strike, 0) * OI
                if test_strike > strike_price:
                    put_pain = (test_strike - strike_price) * strike_data.put.open_interest
                else:
                    put_pain = 0

                total_pain += call_pain + put_pain

            pain_by_strike[test_strike] = total_pain

        return pain_by_strike

    def _calculate_component_pain(
        self,
        chain: OptionsChain,
        max_pain_strike: float,
    ) -> Tuple[float, float]:
        """
        Calculate call and put pain components at max pain strike.

        Args:
            chain: Options chain
            max_pain_strike: The max pain strike

        Returns:
            Tuple of (call_pain, put_pain)
        """
        call_pain = 0.0
        put_pain = 0.0

        for strike_price, strike_data in chain.strikes.items():
            # Call pain at max pain strike
            if max_pain_strike < strike_price:
                call_pain += (strike_price - max_pain_strike) * strike_data.call.open_interest

            # Put pain at max pain strike
            if max_pain_strike > strike_price:
                put_pain += (max_pain_strike - strike_price) * strike_data.put.open_interest

        return call_pain, put_pain

    def _calculate_magnet_strength(
        self,
        max_pain_strike: float,
        spot_price: float,
        expiry: Optional[datetime],
        total_oi: int,
    ) -> float:
        """
        Calculate the strength of max pain as a price magnet.

        Factors:
        - Distance from spot (closer = stronger)
        - Time to expiry (closer = stronger)
        - Total OI (higher = stronger)

        Args:
            max_pain_strike: Max pain strike
            spot_price: Current spot price
            expiry: Option expiry date
            total_oi: Total open interest

        Returns:
            Magnet strength (0-1)
        """
        # Distance factor
        distance_pct = abs(spot_price - max_pain_strike) / spot_price
        # FIX: Scale distance factor to crypto ranges — BTC often trades 40%+ from max pain
        # Use exponential decay: strength = e^(-3 * distance) instead of linear cutoff at 10%
        distance_factor = math.exp(-3 * distance_pct)

        # Time factor
        if expiry:
            days_to_expiry = (expiry - datetime.utcnow()).days
            days_to_expiry = max(0, days_to_expiry)
            # Stronger as expiry approaches
            time_factor = 1 / (1 + days_to_expiry * 0.1)
        else:
            time_factor = 0.5

        # OI factor (normalize)
        # FIX: Use log scale for OI to handle BTC ($1B+ OI) vs small caps
        oi_factor = min(math.log10(max(total_oi, 10)) / 7, 1.0)  # log10 scale: 10M → 0.71, 1B → 1.0

        # Combined strength
        strength = distance_factor * 0.4 + time_factor * 0.4 + oi_factor * 0.2

        return min(strength, 1.0)

    def _generate_signal(
        self,
        max_pain_strike: float,
        spot_price: float,
        distance_pct: float,
        magnet_strength: float,
    ) -> Tuple[SignalDirection, float]:
        """
        Generate trading signal from Max Pain analysis.

        Signal Logic:
        - Price below max pain: Price may rise toward max pain (bullish)
        - Price above max pain: Price may fall toward max pain (bearish)
        - Closer distance = stronger signal

        Args:
            max_pain_strike: Max pain strike
            spot_price: Current spot price
            distance_pct: Distance from max pain (%)
            magnet_strength: Magnet strength factor

        Returns:
            Tuple of (SignalDirection, confidence)
        """
        distance_abs = abs(distance_pct)

        # Too far from max pain - weak signal
        if distance_abs > self.config.distance_threshold * 2:
            return SignalDirection.NEUTRAL, 0.1

        # Price below max pain - bullish (price may rise)
        if spot_price < max_pain_strike:
            # Scale confidence by distance and magnet strength
            if distance_abs <= self.config.distance_threshold:
                confidence = 0.5 + magnet_strength * 0.3
            else:
                confidence = 0.3 + magnet_strength * 0.2

            return SignalDirection.LONG, confidence

        # Price above max pain - bearish (price may fall)
        elif spot_price > max_pain_strike:
            if distance_abs <= self.config.distance_threshold:
                confidence = 0.5 + magnet_strength * 0.3
            else:
                confidence = 0.3 + magnet_strength * 0.2

            return SignalDirection.SHORT, confidence

        # At max pain - neutral
        else:
            return SignalDirection.NEUTRAL, 0.1

    def _create_empty_analysis(
        self,
        symbol: str,
        spot_price: float,
    ) -> MaxPainAnalysis:
        """Create empty Max Pain analysis for insufficient data."""
        return MaxPainAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            max_pain_strike=spot_price,
            current_price=spot_price,
            distance_pct=0.0,
            call_pain=0.0,
            put_pain=0.0,
            signal=SignalDirection.NEUTRAL,
            confidence=0.0,
            magnet_strength=0.0,
        )

    def get_pain_distribution(
        self,
        chain: OptionsChain,
    ) -> Dict[str, Any]:
        """
        Get pain distribution across all strikes.

        Args:
            chain: Options chain

        Returns:
            Dictionary with pain distribution
        """
        pain_data = self._calculate_pain_by_strike(chain)

        distribution = []
        for strike, pain in sorted(pain_data.items()):
            distribution.append(
                {
                    "strike": strike,
                    "pain": pain,
                    "distance_from_spot_pct": round(
                        (strike - chain.spot_price) / chain.spot_price * 100, 2
                    ),
                }
            )

        # Find max pain
        max_pain_strike = max(pain_data, key=pain_data.get) if pain_data else chain.spot_price

        return {
            "max_pain_strike": max_pain_strike,
            "max_pain_value": pain_data.get(max_pain_strike, 0),
            "spot_price": chain.spot_price,
            "distribution": distribution,
        }

    def get_max_pain_summary(self, analysis: MaxPainAnalysis) -> Dict[str, Any]:
        """
        Get summary of Max Pain analysis.

        Args:
            analysis: Max Pain analysis result

        Returns:
            Dictionary with Max Pain summary
        """
        return {
            "symbol": analysis.symbol,
            "max_pain_strike": round(analysis.max_pain_strike, 2),
            "current_price": round(analysis.current_price, 2),
            "distance_pct": round(analysis.distance_pct, 2),
            "call_pain": round(analysis.call_pain, 2),
            "put_pain": round(analysis.put_pain, 2),
            "magnet_strength": round(analysis.magnet_strength, 3),
            "signal": analysis.signal.value,
            "confidence": round(analysis.confidence, 2),
            "interpretation": self._interpret_max_pain(analysis),
        }

    def _interpret_max_pain(self, analysis: MaxPainAnalysis) -> str:
        """Interpret Max Pain analysis."""
        if analysis.distance_pct > 0:
            return f"Price {abs(analysis.distance_pct):.1f}% below max pain - potential upward magnet effect"
        elif analysis.distance_pct < 0:
            return f"Price {abs(analysis.distance_pct):.1f}% above max pain - potential downward magnet effect"
        else:
            return "Price at max pain - neutral"

    def calculate_pain_change(
        self,
        chain: OptionsChain,
        price_move_pct: float,
    ) -> Dict[str, Any]:
        """
        Calculate how pain changes with price movement.

        This shows which direction reduces total pain for option holders.

        Args:
            chain: Options chain
            price_move_pct: Hypothetical price move percentage

        Returns:
            Dictionary with pain change analysis
        """
        current_pain = self._calculate_pain_by_strike(chain)

        # Simulate price move
        new_price = chain.spot_price * (1 + price_move_pct / 100)

        # Find closest strike to new price
        strikes = sorted(chain.strikes.keys())
        closest_strike = min(strikes, key=lambda s: abs(s - new_price))

        pain_at_new_price = current_pain.get(closest_strike, 0)
        pain_at_current = current_pain.get(min(strikes, key=lambda s: abs(s - chain.spot_price)), 0)

        pain_change = pain_at_new_price - pain_at_current
        pain_change_pct = (pain_change / pain_at_current * 100) if pain_at_current > 0 else 0

        return {
            "current_price": chain.spot_price,
            "simulated_price": round(new_price, 2),
            "price_move_pct": price_move_pct,
            "current_pain": round(pain_at_current, 2),
            "new_pain": round(pain_at_new_price, 2),
            "pain_change": round(pain_change, 2),
            "pain_change_pct": round(pain_change_pct, 2),
            "benefits_holders": pain_change > 0,
        }
