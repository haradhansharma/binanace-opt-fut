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

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import math

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    GammaLevel,
    GammaAnalysis,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GammaExposureConfig:
    """Configuration for gamma exposure calculation."""
    # GEX significance threshold (as % of total absolute GEX)
    significant_level_threshold: float = 0.05  # 5% of total
    
    # Minimum OI to consider
    min_oi_threshold: int = 10
    
    # Price range for flip detection (% from spot)
    flip_search_range: float = 0.30  # ±30% from spot
    
    # Whether to use simplified delta approximation
    use_simplified_delta: bool = True


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
        config: Gamma exposure configuration
    """
    
    # Standard normal distribution percentiles for delta approximation
    # These approximate N(d1) for Black-Scholes delta
    DELTA_APPROX = {
        "deep_otm": 0.05,   # < 0.7 delta moneyness
        "otm": 0.15,        # 0.7-0.85 delta moneyness
        "near_atm": 0.50,   # 0.85-1.15 delta moneyness
        "itm": 0.70,        # 1.15-1.30 delta moneyness
        "deep_itm": 0.90,   # > 1.30 delta moneyness
    }
    
    def __init__(self, config: Optional[GammaExposureConfig] = None):
        """
        Initialize gamma exposure calculator.
        
        Args:
            config: Gamma exposure configuration
        """
        self.config = config or GammaExposureConfig()
        
        logger.info(
            "Gamma exposure calculator initialized",
            extra={"data": {
                "significant_threshold": self.config.significant_level_threshold,
            }}
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
        
        logger.info(
            f"Calculating gamma exposure for {chain.underlying}: "
            f"strikes={len(chain.strikes)}, spot={spot}"
        )
        
        # Calculate GEX at each strike
        strike_gex = self._calculate_strike_gex(chain, spot)
        
        # Calculate aggregate metrics
        total_call_gex = sum(g['call_gex'] for g in strike_gex.values())
        total_put_gex = sum(g['put_gex'] for g in strike_gex.values())
        total_gex = total_call_gex + total_put_gex
        
        # Note: Put GEX is typically negative (dealers are short puts = long delta)
        # But for GEX calculation, we consider the hedging impact
        # Short puts = dealers are short puts = must buy to hedge = positive GEX impact
        # Short calls = dealers are short calls = must sell to hedge = negative GEX impact
        
        # Adjust sign: Call GEX is negative (dealers short calls = sell pressure)
        # Put GEX is positive (dealers short puts = buy pressure)
        net_gex = -total_call_gex + total_put_gex
        
        # Calculate absolute gamma surface
        abs_gex_surface = sum(abs(g['call_gex']) + abs(g['put_gex']) for g in strike_gex.values())
        
        # Find gamma flip level
        gamma_flip = self._find_gamma_flip(strike_gex, spot)
        
        # Identify significant levels
        support_levels, resistance_levels = self._identify_gex_levels(
            strike_gex, spot, abs_gex_surface
        )
        
        # Determine GEX regime
        gex_regime = self._determine_gex_regime(net_gex, abs_gex_surface)
        hedge_pressure = self._determine_hedge_pressure(net_gex, gex_regime)
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(abs_gex_surface, spot, len(chain.strikes))
        
        # Normalize GEX per spot unit
        gex_per_spot = net_gex / spot if spot > 0 else 0
        
        analysis = GammaAnalysis(
            symbol=chain.underlying,
            spot_price=spot,
            timestamp=datetime.utcnow(),
            
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
        )
        
        logger.info(
            f"Gamma analysis complete for {chain.underlying}",
            extra={"data": {
                "total_gex": net_gex,
                "gex_regime": gex_regime,
                "support_levels": len(support_levels),
                "resistance_levels": len(resistance_levels),
            }}
        )
        
        return analysis
    
    def _calculate_strike_gex(
        self,
        chain: OptionsChain,
        spot: float,
    ) -> Dict[float, Dict[str, float]]:
        """
        Calculate GEX at each strike.
        
        GEX = OI × Gamma × 100 × Spot² × 0.01
        
        For calls: Negative (dealers short calls = sell pressure above)
        For puts: Positive (dealers short puts = buy support below)
        
        Args:
            chain: Options chain
            spot: Current spot price
            
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
            # Simplified: Gamma ≈ 1 / (spot × sqrt(2π)) for ATM, scaled for moneyness
            call_gamma = self._estimate_gamma(spot, strike_price, "CALL")
            put_gamma = self._estimate_gamma(spot, strike_price, "PUT")
            
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
                'call_gex': call_gex,
                'put_gex': put_gex,
                'net_gex': call_gex + put_gex,
                'call_oi': call_oi,
                'put_oi': put_oi,
                'call_gamma': call_gamma,
                'put_gamma': put_gamma,
            }
        
        return strike_gex
    
    def _estimate_gamma(
        self,
        spot: float,
        strike: float,
        option_type: str,
    ) -> float:
        """
        Estimate gamma for an option.
        
        Simplified gamma approximation:
        Gamma ≈ n(d1) / (S × σ × sqrt(T))
        
        For our purposes, we use a simplified approach based on moneyness.
        
        Args:
            spot: Current spot price
            strike: Strike price
            option_type: "CALL" or "PUT"
            
        Returns:
            Estimated gamma value
        """
        # Moneyness
        moneyness = strike / spot if spot > 0 else 1.0
        
        # Simplified gamma based on moneyness
        # ATM options have highest gamma, OTM have lower
        # Gamma peak is near ATM
        
        if moneyness < 0.7 or moneyness > 1.3:
            # Deep OTM or ITM - low gamma
            gamma = 0.002
        elif 0.85 <= moneyness <= 1.15:
            # Near ATM - highest gamma
            # Peak at ATM (moneyness = 1.0)
            distance_from_atm = abs(moneyness - 1.0)
            gamma = 0.015 * (1 - distance_from_atm / 0.15)
        else:
            # Slightly OTM/ITM - moderate gamma
            distance_from_atm = abs(moneyness - 1.0)
            gamma = 0.010 * (1 - distance_from_atm / 0.3)
        
        return max(gamma, 0.001)  # Minimum gamma
    
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
            cumulative_gex += strike_gex[strike]['net_gex']
            
            # Check for sign change
            if prev_strike is not None:
                if (prev_cumulative < 0 and cumulative_gex >= 0) or \
                   (prev_cumulative > 0 and cumulative_gex <= 0):
                    # Linear interpolation to find flip
                    if cumulative_gex != prev_cumulative:
                        ratio = -prev_cumulative / (cumulative_gex - prev_cumulative)
                        flip = prev_strike + ratio * (strike - prev_strike)
                        return flip
            
            prev_cumulative = cumulative_gex
            prev_strike = strike
        
        # No flip found - return spot if all positive, or None if all negative
        if cumulative_gex > 0:
            return spot * 0.9  # Estimated support level
        else:
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
            net_gex = gex_data['net_gex']
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
    ) -> float:
        """
        Calculate gamma risk score.
        
        Higher absolute GEX = higher volatility potential.
        
        Args:
            abs_gex_surface: Total absolute GEX
            spot: Current spot price
            num_strikes: Number of strikes
            
        Returns:
            Risk score 0-1
        """
        if spot == 0 or num_strikes == 0:
            return 0.0
        
        # Normalize by spot and number of strikes
        normalized_surface = abs_gex_surface / (spot * spot * num_strikes)
        
        # Scale to 0-1 (higher = more volatile)
        # Typical values are small, so we scale appropriately
        risk_score = min(normalized_surface * 1000, 1.0)
        
        return risk_score
    
    def get_gex_summary(self, analysis: GammaAnalysis) -> Dict[str, Any]:
        """
        Get summary of gamma analysis.
        
        Args:
            analysis: Gamma analysis result
            
        Returns:
            Summary dictionary
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
        }
