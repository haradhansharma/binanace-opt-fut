"""
Gamma Exposure Calculator for Dealer Hedging Levels.

This module calculates the Gamma Exposure (GEX) of options positions to identify
where market makers (dealers) must hedge aggressively, creating price inflection points.

Key Concepts:
- Gamma Exposure (GEX): Measures how much delta changes as price moves
- Positive GEX: Dealers buy dips (support behavior)
- Negative GEX: Dealers sell rallies (resistance behavior)
- Gamma Flip: Price level where GEX changes from positive to negative

Dealer Hedging Logic:
- When dealers sell options, they must delta-hedge
- As price moves, delta changes (gamma), requiring hedge adjustment
- Large GEX concentrations create price "magnets" or "walls"

Reference:
- https://squeezemetrics.com/monitor/download/pdf/white_paper.pdf
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import math

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    GammaLevel,
    GammaAnalysis,
)
from binance_signal_generator.config import load_config, GammaExposureAnalyzerConfig
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


class GammaExposureCalculator:
    """
    Calculates Gamma Exposure for options positions.

    Purpose:
        Identify price levels where dealers must hedge aggressively,
        creating support/resistance zones based on options positioning.

    Theory:
        Dealers who sell options must delta-hedge their positions.
        - Selling calls: Must buy underlying to hedge → creates support
        - Selling puts: Must sell underlying to hedge → creates resistance

        Gamma measures how much delta changes with price movement.
        Large gamma concentrations create "hedging pressure" zones.

    Attributes:
        config: Gamma exposure configuration (loaded from config.yaml)
    """

    # Standard normal distribution percentiles for delta approximation
    # These approximate N(d1) for Black-Scholes delta
    DELTA_APPROX = {
        "deep_otm": 0.05,  # < 0.7 delta moneyness
        "otm": 0.15,  # 0.7-0.85 delta moneyness
        "near_atm": 0.50,  # 0.85-1.15 delta moneyness
        "itm": 0.70,  # 1.15-1.30 delta moneyness
        "deep_itm": 0.90,  # > 1.30 delta moneyness
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize gamma exposure calculator.

        Config is loaded from config.yaml via load_config().
        Single source of truth - no fallback defaults.

        Args:
            config_path: Optional path to config file
        """
        loaded_config = load_config(config_path)
        self.config = loaded_config.analysis.gamma_exposure_config

        logger.info(
            "Gamma exposure calculator initialized",
            extra={
                "data": {
                    "significant_threshold": self.config.significant_level_threshold,
                }
            },
        )

    def calculate(self, chain: OptionsChain) -> GammaAnalysis:
        """
        Calculate gamma exposure for an options chain.

        Args:
            chain: Options chain data

        Returns:
            GammaAnalysis with all GEX metrics
        """
        spot = chain.spot_price

        # Calculate DTE (Days to Expiry)
        dte = self._calculate_dte(chain.expiry)
        dte_weight = self._calculate_dte_weight(dte)

        logger.info(
            f"Calculating gamma exposure for {chain.underlying}: "
            f"strikes={len(chain.strikes)}, spot={spot}, DTE={dte:.1f} days, DTE_weight={dte_weight:.2f}"
        )

        # Calculate GEX at each strike with DTE weighting
        strike_gex = self._calculate_strike_gex(chain, spot, dte_weight, dte_days=dte)

        # Calculate aggregate metrics
        total_call_gex = sum(g["call_gex"] for g in strike_gex.values())
        total_put_gex = sum(g["put_gex"] for g in strike_gex.values())
        total_gex = total_call_gex + total_put_gex

        # Note: Put GEX is typically negative (dealers are short puts = long delta)
        # But for GEX calculation, we consider the hedging impact
        # Short puts = dealers are short puts = must buy to hedge = positive GEX impact
        # Short calls = dealers are short calls = must sell to hedge = negative GEX impact

        # Adjust sign: Call GEX is negative (dealers short calls = sell pressure)
        # Put GEX is positive (dealers short puts = buy pressure)
        net_gex = -total_call_gex + total_put_gex

        # Calculate absolute gamma surface
        abs_gex_surface = sum(abs(g["call_gex"]) + abs(g["put_gex"]) for g in strike_gex.values())

        # Find gamma flip level
        gamma_flip = self._find_gamma_flip(strike_gex, spot)

        # Identify significant levels
        support_levels, resistance_levels = self._identify_gex_levels(
            strike_gex, spot, abs_gex_surface
        )

        # Determine GEX regime
        gex_regime = self._determine_gex_regime(net_gex, abs_gex_surface)
        hedge_pressure = self._determine_hedge_pressure(net_gex, gex_regime)

        # Calculate risk score with DTE adjustment
        risk_score = self._calculate_risk_score(
            abs_gex_surface, spot, len(chain.strikes), dte_weight
        )

        # Normalize GEX per spot unit
        gex_per_spot = net_gex / spot if spot > 0 else 0

        analysis = GammaAnalysis(
            symbol=chain.underlying,
            spot_price=spot,
            timestamp=datetime.now(timezone.utc),
            total_gex=net_gex,
            total_call_gex=total_call_gex,
            total_put_gex=total_put_gex,
            gex_per_spot=gex_per_spot,
            gamma_flip=gamma_flip,
            absolute_gamma_surface=abs_gex_surface,
            gex_support_levels=support_levels,
            gex_resistance_levels=resistance_levels,
            gex_regime=gex_regime,
            dealer_hedge_pressure=hedge_pressure,
            gamma_risk_score=risk_score,
            # DTE metrics
            dte_days=dte,
            dte_weight=dte_weight,
            expiry_imminent=(dte <= 3.0),
        )

        # Add DTE info to analysis via extra logging
        logger.info(
            f"Gamma analysis complete for {chain.underlying}",
            extra={
                "data": {
                    "total_gex": net_gex,
                    "gex_regime": gex_regime,
                    "support_levels": len(support_levels),
                    "resistance_levels": len(resistance_levels),
                    "dte_days": dte,
                    "dte_weight": dte_weight,
                }
            },
        )

        return analysis

    def _calculate_dte(self, expiry: Optional[datetime]) -> float:
        """
        Calculate Days to Expiry (DTE) from expiry datetime.

        Args:
            expiry: Option expiry datetime (UTC expected)

        Returns:
            DTE in days (minimum 0.1 to avoid division by zero)
        """
        if expiry is None:
            # If no expiry provided, assume standard 7-day expiry
            return 7.0

        now = datetime.now(timezone.utc)

        # Handle both timezone-aware and naive datetimes
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        delta = expiry - now
        dte = delta.total_seconds() / 86400  # Convert to days

        # Ensure minimum DTE of 0.1 days (~2.4 hours) to avoid extreme weights
        return max(dte, 0.1)

    def _calculate_dte_weight(self, dte: float) -> float:
        """
        Calculate DTE weight factor for gamma exposure.

        Theory:
            Gamma ∝ 1/√T where T is time to expiry
            As expiry approaches, gamma increases for ATM options
            This means dealer hedging pressure intensifies near expiry

        Formula:
            weight = √(reference_DTE / actual_DTE)

        Normalization:
            - DTE = 7 days → weight = 1.0 (baseline)
            - DTE = 1 day → weight = √7 ≈ 2.65 (higher impact)
            - DTE = 30 days → weight = √(7/30) ≈ 0.48 (lower impact)

        Args:
            dte: Days to expiry

        Returns:
            DTE weight factor (clamped to configured min/max)
        """
        if not self.config.enable_dte_weighting:
            return 1.0

        # Calculate raw weight using inverse square root of time
        # This follows Black-Scholes gamma behavior
        reference_dte = self.config.dte_reference_days

        if dte <= 0:
            # Expired or about to expire - use max weight
            return self.config.max_dte_weight

        # Gamma scales as 1/√T, so weight = √(reference/DTE)
        raw_weight = math.sqrt(reference_dte / dte)

        # Clamp to configured bounds
        weight = max(self.config.min_dte_weight, min(self.config.max_dte_weight, raw_weight))

        return weight

    def _calculate_strike_gex(
        self,
        chain: OptionsChain,
        spot: float,
        dte_weight: float = 1.0,
        dte_days: float = 7.0,
    ) -> Dict[float, Dict[str, float]]:
        """
        Calculate GEX at each strike with DTE weighting.

        GEX = OI × Gamma × 100 × Spot² × 0.01 × DTE_weight

        For calls: Negative (dealers short calls = sell pressure above)
        For puts: Positive (dealers short puts = buy support below)

        DTE Weighting:
            Near expiry (low DTE): Higher gamma → stronger hedging pressure
            Far expiry (high DTE): Lower gamma → weaker hedging pressure

        Args:
            chain: Options chain
            spot: Current spot price
            dte_weight: DTE weighting factor (default 1.0)

        Returns:
            Dictionary of strike -> GEX components
        """
        strike_gex = {}

        for strike_price, strike_data in chain.strikes.items():
            # Skip very low OI strikes
            call_oi = strike_data.call.open_interest
            put_oi = strike_data.put.open_interest

            if call_oi < self.config.min_oi_threshold and put_oi < self.config.min_oi_threshold:
                continue

            # Calculate gamma for calls and puts
            # FIX: Pass IV from strike data and DTE to make gamma estimation adaptive
            call_iv = strike_data.call.iv if strike_data.call.iv > 0 else 0.6
            put_iv = strike_data.put.iv if strike_data.put.iv > 0 else 0.6
            avg_iv = (call_iv + put_iv) / 2

            call_gamma = (
                self._estimate_gamma(spot, strike_price, "CALL", iv=avg_iv, dte=dte_days)
                * dte_weight
            )
            put_gamma = (
                self._estimate_gamma(spot, strike_price, "PUT", iv=avg_iv, dte=dte_days)
                * dte_weight
            )

            # GEX formula: OI × Gamma × 100 × Spot² × 0.01
            # The 100 is contract multiplier, 0.01 is for 1% move
            # Simplified: GEX = OI × Gamma × Spot² × ContractMultiplier

            contract_multiplier = 100  # Standard options contract
            gamma_scaler = spot * spot * 0.01  # Scale factor

            # Call GEX (negative - dealers short calls)
            call_gex = -call_oi * call_gamma * gamma_scaler * contract_multiplier

            # Put GEX (positive - dealers short puts = buy pressure)
            put_gex = put_oi * put_gamma * gamma_scaler * contract_multiplier

            strike_gex[strike_price] = {
                "call_gex": call_gex,
                "put_gex": put_gex,
                "net_gex": call_gex + put_gex,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "call_gamma": call_gamma,
                "put_gamma": put_gamma,
                "dte_weight": dte_weight,
            }

        return strike_gex

    def _estimate_gamma(
        self,
        spot: float,
        strike: float,
        option_type: str,
        iv: float = 0.6,
        dte: float = 7.0,
    ) -> float:
        """
        Estimate gamma for an option.

        FIX: Now scales with IV (sigma) and DTE (time to expiry).
        By Black-Scholes: Gamma ≈ n(d1) / (S × σ × √T)
        Previously, hardcoded values (0.002, 0.010, 0.015) didn't scale
        with IV or DTE, causing:
        - High IV environments to underestimate gamma
        - Low IV environments to overestimate gamma
        - All DTE values getting the same gamma

        The base values are calibrated for IV=60%, DTE=7 days.
        Scaling: gamma *= (0.6 / IV) * sqrt(7 / DTE)

        Args:
            spot: Current spot price
            strike: Strike price
            option_type: "CALL" or "PUT"
            iv: Implied volatility (default 0.6 for crypto)
            dte: Days to expiry (default 7.0)

        Returns:
            Estimated gamma value
        """
        # Moneyness
        moneyness = strike / spot if spot > 0 else 1.0

        # Base gamma based on moneyness (calibrated at IV=0.6, DTE=7)
        if moneyness < 0.7 or moneyness > 1.3:
            base_gamma = 0.002  # Deep OTM or ITM - low gamma
        elif 0.85 <= moneyness <= 1.15:
            distance_from_atm = abs(moneyness - 1.0)
            base_gamma = 0.015 * (1 - distance_from_atm / 0.15)  # Near ATM - highest
        else:
            distance_from_atm = abs(moneyness - 1.0)
            base_gamma = 0.010 * (1 - distance_from_atm / 0.3)  # Slightly OTM/ITM

        # FIX: Scale gamma by IV and DTE
        # Gamma ∝ 1/(σ×√T), so normalize relative to reference (IV=0.6, DTE=7)
        iv = max(iv, 0.1)  # Minimum IV to avoid division by zero
        dte = max(dte, 0.1)  # Minimum DTE

        iv_scaling = 0.6 / iv  # Higher IV → lower gamma
        dte_scaling = math.sqrt(7.0 / dte)  # Shorter DTE → higher gamma

        gamma = base_gamma * iv_scaling * dte_scaling

        return max(gamma, 0.0005)  # Minimum gamma

    def _find_gamma_flip(
        self,
        strike_gex: Dict[float, Dict[str, float]],
        spot: float,
    ) -> Optional[float]:
        """
        Find the gamma flip level where GEX changes sign.

        The gamma flip is where dealers transition from supporting to resisting.

        Args:
            strike_gex: GEX at each strike
            spot: Current spot price

        Returns:
            Estimated gamma flip price or None
        """
        if not strike_gex:
            return None

        # Sort strikes
        strikes = sorted(strike_gex.keys())

        # Calculate cumulative GEX from lowest strike up
        cumulative_gex = 0
        prev_cumulative = 0
        prev_strike = None

        for strike in strikes:
            cumulative_gex += strike_gex[strike]["net_gex"]

            # Check for sign change
            if prev_strike is not None:
                if (prev_cumulative < 0 and cumulative_gex >= 0) or (
                    prev_cumulative > 0 and cumulative_gex <= 0
                ):
                    # Linear interpolation to find flip
                    if cumulative_gex != prev_cumulative:
                        ratio = -prev_cumulative / (cumulative_gex - prev_cumulative)
                        flip = prev_strike + ratio * (strike - prev_strike)
                        return flip

            prev_cumulative = cumulative_gex
            prev_strike = strike

        # No flip found in the data
        # FIX: Previously fabricated levels at spot±10% which then influenced
        # signal direction as if they were real. Now return None to indicate
        # no actual gamma flip exists, and signal_scorer handles this correctly.
        logger.debug(
            f"No gamma flip found in data for {spot:.0f} (cumulative_gex={cumulative_gex:.0f})"
        )
        return None

    def _identify_gex_levels(
        self,
        strike_gex: Dict[float, Dict[str, float]],
        spot: float,
        total_abs_gex: float,
    ) -> Tuple[List[GammaLevel], List[GammaLevel]]:
        """
        Identify significant GEX levels as support/resistance.

        Args:
            strike_gex: GEX at each strike
            spot: Current spot price
            total_abs_gex: Total absolute GEX

        Returns:
            Tuple of (support_levels, resistance_levels)
        """
        support_levels = []
        resistance_levels = []

        threshold = total_abs_gex * self.config.significant_level_threshold

        for strike, gex_data in strike_gex.items():
            net_gex = gex_data["net_gex"]
            abs_gex = abs(net_gex)

            # Skip if below threshold
            if abs_gex < threshold:
                continue

            # Normalize
            normalized = abs_gex / total_abs_gex if total_abs_gex > 0 else 0

            # Determine level type and dealer behavior
            if strike < spot:
                # Below spot = potential support
                if net_gex > 0:
                    # Positive GEX = dealers buy dips = support
                    level_type = "SUPPORT"
                    dealer_behavior = "DEALERS_BUY_DIPS"
                else:
                    # Negative GEX = dealers sell = potential resistance
                    level_type = "NEUTRAL"
                    dealer_behavior = "DEALERS_SELL"

                level = GammaLevel(
                    strike=strike,
                    gex_value=net_gex,
                    gex_normalized=normalized,
                    level_type=level_type,
                    dealer_behavior=dealer_behavior,
                    strength=min(normalized * 10, 1.0),  # Scale to 0-1
                )
                support_levels.append(level)
            else:
                # Above spot = potential resistance
                if net_gex < 0:
                    # Negative GEX = dealers sell rallies = resistance
                    level_type = "RESISTANCE"
                    dealer_behavior = "DEALERS_SELL_RALLIES"
                else:
                    # Positive GEX = dealers buy = potential support
                    level_type = "NEUTRAL"
                    dealer_behavior = "DEALERS_BUY"

                level = GammaLevel(
                    strike=strike,
                    gex_value=net_gex,
                    gex_normalized=normalized,
                    level_type=level_type,
                    dealer_behavior=dealer_behavior,
                    strength=min(normalized * 10, 1.0),
                )
                resistance_levels.append(level)

        # Sort by strength
        support_levels.sort(key=lambda x: x.strength, reverse=True)
        resistance_levels.sort(key=lambda x: x.strength, reverse=True)

        return support_levels[:5], resistance_levels[:5]

    def _determine_gex_regime(
        self,
        net_gex: float,
        total_abs_gex: float,
    ) -> str:
        """
        Determine the overall GEX regime.

        Args:
            net_gex: Net gamma exposure
            total_abs_gex: Total absolute GEX

        Returns:
            Regime string: "POSITIVE", "NEGATIVE", or "NEUTRAL"
        """
        if total_abs_gex == 0:
            return "NEUTRAL"

        ratio = net_gex / total_abs_gex

        if ratio > 0.1:
            return "POSITIVE"  # Dealers provide support
        elif ratio < -0.1:
            return "NEGATIVE"  # Dealers provide resistance
        else:
            return "NEUTRAL"

    def _determine_hedge_pressure(
        self,
        net_gex: float,
        gex_regime: str,
    ) -> str:
        """
        Determine dealer hedging pressure direction.

        Args:
            net_gex: Net gamma exposure
            gex_regime: GEX regime

        Returns:
            Hedge pressure description
        """
        if gex_regime == "POSITIVE":
            return "BUY_DIPS"  # Dealers buy when price drops
        elif gex_regime == "NEGATIVE":
            return "SELL_RALLIES"  # Dealers sell when price rises
        else:
            return "MIXED"  # Mixed signals

    def _calculate_risk_score(
        self,
        abs_gex_surface: float,
        spot: float,
        num_strikes: int,
        dte_weight: float = 1.0,
    ) -> float:
        """
        Calculate gamma risk score with DTE adjustment.

        Higher absolute GEX = higher volatility potential.
        Near expiry (high DTE weight) = higher volatility risk.

        Args:
            abs_gex_surface: Total absolute GEX
            spot: Current spot price
            num_strikes: Number of strikes
            dte_weight: DTE weighting factor (higher = near expiry = more risk)

        Returns:
            Risk score 0-1
        """
        if spot == 0 or num_strikes == 0:
            return 0.0

        # Normalize by spot and number of strikes
        normalized_surface = abs_gex_surface / (spot * spot * num_strikes)

        # Scale to 0-1 (higher = more volatile)
        # Typical values are small, so we scale appropriately
        base_risk_score = min(normalized_surface * 1000, 1.0)

        # Apply DTE adjustment: Near expiry = higher risk
        # DTE weight > 1 means near expiry, amplify risk
        # DTE weight < 1 means far expiry, reduce risk
        dte_adjusted_risk = base_risk_score * (0.5 + 0.5 * dte_weight)

        # Ensure risk stays in 0-1 range
        risk_score = min(dte_adjusted_risk, 1.0)

        return risk_score

    def get_gex_summary(self, analysis: GammaAnalysis) -> Dict[str, Any]:
        """
        Get summary of gamma analysis including DTE weighting.

        Args:
            analysis: Gamma analysis result

        Returns:
            Summary dictionary with DTE metrics
        """
        return {
            "symbol": analysis.symbol,
            "total_gex": round(analysis.total_gex, 2),
            "gex_regime": analysis.gex_regime,
            "dealer_pressure": analysis.dealer_hedge_pressure,
            "gamma_flip": analysis.gamma_flip,
            "support_levels": [
                {"strike": l.strike, "gex": round(l.gex_value, 2), "strength": round(l.strength, 2)}
                for l in analysis.gex_support_levels[:3]
            ],
            "resistance_levels": [
                {"strike": l.strike, "gex": round(l.gex_value, 2), "strength": round(l.strength, 2)}
                for l in analysis.gex_resistance_levels[:3]
            ],
            "gamma_risk_score": round(analysis.gamma_risk_score, 3),
            # DTE metrics
            "dte_days": round(analysis.dte_days, 1),
            "dte_weight": round(analysis.dte_weight, 2),
            "expiry_imminent": analysis.expiry_imminent,
        }
