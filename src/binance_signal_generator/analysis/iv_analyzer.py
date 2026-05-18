"""
Implied Volatility (IV) analyzer for Options data.

This module analyzes Implied Volatility from Options data to generate
trading signals. IV analysis helps identify:

- Overpriced options (high IV = sell premium strategy)
- Underpriced options (low IV = buy premium strategy)
- Market sentiment and expected moves

Signal Logic:
- High IV (>75th percentile): Bearish for long options, good for selling
- Low IV (<25th percentile): Bullish for long options, good for buying
- IV Rank: Position in 52-week range
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    IVAnalysis,
    SignalDirection,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IVConfig:
    """Configuration for IV analysis."""
    # IV percentile thresholds
    iv_high_threshold: float = 0.75  # 75th percentile
    iv_low_threshold: float = 0.25   # 25th percentile
    
    # IV value thresholds (annualized)
    iv_high_value: float = 0.80      # 80% annualized
    iv_low_value: float = 0.30       # 30% annualized
    
    # ATM range for IV calculation (percentage from spot)
    atm_range_pct: float = 5.0       # 5% from spot
    
    # Minimum strikes for valid analysis
    min_strikes: int = 3


class IVAnalyzer:
    """
    Analyzes Implied Volatility from Options data.
    
    IV Analysis Methods:
    1. ATM IV: Average IV of at-the-money options
    2. IV Skew: Difference between OTM put and call IV
    3. IV Term Structure: IV across different expiries (if available)
    4. IV Rank: Position in historical range
    
    Signal Generation:
    - High IV + Put Skew = Bearish signal (panic in market)
    - Low IV + Call Skew = Bullish signal (complacency)
    - Neutral IV = No signal from IV
    
    Attributes:
        config: IV analysis configuration
    """
    
    def __init__(self, config: Optional[IVConfig] = None):
        """
        Initialize IV analyzer.
        
        Args:
            config: IV analysis configuration
        """
        self.config = config or IVConfig()
        
        logger.info(
            "IV analyzer initialized",
            extra={"data": {
                "iv_high_threshold": self.config.iv_high_threshold,
                "iv_low_threshold": self.config.iv_low_threshold,
            }}
        )
    
    def analyze(self, chain: OptionsChain) -> IVAnalysis:
        """
        Analyze IV from options chain.
        
        Args:
            chain: Options chain data
            
        Returns:
            IVAnalysis with IV metrics and signal
        """
        if len(chain.strikes) < self.config.min_strikes:
            logger.warning(
                f"Insufficient strikes for IV analysis: {len(chain.strikes)}"
            )
            return self._create_empty_analysis(chain.underlying)
        
        # Calculate ATM IV
        atm_iv = self._calculate_atm_iv(chain)
        
        # Calculate IV percentile (estimated)
        iv_percentile = self._estimate_iv_percentile(atm_iv)
        
        # Calculate IV skew
        iv_skew = self._calculate_iv_skew(chain)
        
        # Determine IV state
        iv_state = self._determine_iv_state(iv_percentile)
        
        # Generate signal
        signal, confidence = self._generate_signal(
            iv_percentile=iv_percentile,
            iv_skew=iv_skew,
            atm_iv=atm_iv,
        )
        
        return IVAnalysis(
            symbol=chain.underlying,
            timestamp=datetime.utcnow(),
            current_iv=atm_iv,
            iv_rank=iv_percentile,  # Using percentile as rank proxy
            iv_percentile=iv_percentile,
            signal=signal,
            confidence=confidence,
            iv_state=iv_state,
        )
    
    def _calculate_atm_iv(self, chain: OptionsChain) -> float:
        """
        Calculate at-the-money implied volatility.
        
        Uses options within a specified range of spot price.
        
        Args:
            chain: Options chain
            
        Returns:
            Average ATM IV
        """
        spot = chain.spot_price
        range_pct = self.config.atm_range_pct / 100
        
        lower_bound = spot * (1 - range_pct)
        upper_bound = spot * (1 + range_pct)
        
        ivs = []
        for strike_price, strike_data in chain.strikes.items():
            if lower_bound <= strike_price <= upper_bound:
                # Weight by proximity to ATM
                distance = abs(strike_price - spot) / spot
                weight = 1 - (distance / range_pct)
                
                if strike_data.call.iv > 0:
                    ivs.append((strike_data.call.iv, weight))
                if strike_data.put.iv > 0:
                    ivs.append((strike_data.put.iv, weight))
        
        if not ivs:
            # Fallback: use all available IVs
            for strike_data in chain.strikes.values():
                if strike_data.call.iv > 0:
                    ivs.append((strike_data.call.iv, 1.0))
                if strike_data.put.iv > 0:
                    ivs.append((strike_data.put.iv, 1.0))
        
        if not ivs:
            return 0.5  # Default neutral IV
        
        # Calculate weighted average
        total_weight = sum(w for _, w in ivs)
        weighted_iv = sum(iv * w for iv, w in ivs)
        
        return weighted_iv / total_weight if total_weight > 0 else 0.5
    
    def _calculate_iv_skew(self, chain: OptionsChain) -> float:
        """
        Calculate IV skew (OTM Put IV - OTM Call IV).
        
        Positive skew = Put IV > Call IV (bearish sentiment)
        Negative skew = Call IV > Put IV (bullish sentiment)
        
        Args:
            chain: Options chain
            
        Returns:
            IV skew value
        """
        spot = chain.spot_price
        
        # Find OTM puts (strike < spot)
        otm_put_ivs = []
        for strike_price, strike_data in chain.strikes.items():
            if strike_price < spot and strike_data.put.iv > 0:
                otm_put_ivs.append(strike_data.put.iv)
        
        # Find OTM calls (strike > spot)
        otm_call_ivs = []
        for strike_price, strike_data in chain.strikes.items():
            if strike_price > spot and strike_data.call.iv > 0:
                otm_call_ivs.append(strike_data.call.iv)
        
        avg_put_iv = sum(otm_put_ivs) / len(otm_put_ivs) if otm_put_ivs else 0
        avg_call_iv = sum(otm_call_ivs) / len(otm_call_ivs) if otm_call_ivs else 0
        
        return avg_put_iv - avg_call_iv
    
    def _estimate_iv_percentile(self, current_iv: float) -> float:
        """
        Estimate IV percentile from current IV value.
        
        In production, this would use historical IV data.
        This implementation uses rough thresholds for crypto.
        
        Args:
            current_iv: Current IV value
            
        Returns:
            Estimated IV percentile (0-1)
        """
        # Rough crypto IV ranges
        # Very low: < 30%
        # Low: 30-50%
        # Normal: 50-70%
        # High: 70-100%
        # Very high: > 100%
        
        if current_iv <= 0.30:
            return 0.15
        elif current_iv <= 0.50:
            return 0.35
        elif current_iv <= 0.70:
            return 0.55
        elif current_iv <= 0.80:
            return 0.70
        elif current_iv <= 1.00:
            return 0.85
        else:
            return 0.95
    
    def _determine_iv_state(self, iv_percentile: float) -> str:
        """
        Determine IV state from percentile.
        
        Args:
            iv_percentile: IV percentile (0-1)
            
        Returns:
            IV state string
        """
        if iv_percentile >= self.config.iv_high_threshold:
            return "HIGH"
        elif iv_percentile <= self.config.iv_low_threshold:
            return "LOW"
        else:
            return "NORMAL"
    
    def _generate_signal(
        self,
        iv_percentile: float,
        iv_skew: float,
        atm_iv: float,
    ) -> tuple:
        """
        Generate trading signal from IV analysis.
        
        IMPROVED: IV-004 - Revised IV skew signal logic for better interpretation
        
        Signal Logic (Enhanced for crypto with contrarian interpretation):
        
        IV Skew Interpretation:
        - Positive Skew (Put IV > Call IV): Indicates demand for downside protection
          Traditional view: Bearish sentiment → SHORT signal
          Contrarian view: Could indicate hedged longs (institutions bullish)
        
        - Negative Skew (Call IV > Put IV): Indicates demand for upside exposure
          Traditional view: Bullish sentiment → LONG signal
          Contrarian view: Could indicate crowded longs (retail FOMO)
        
        For crypto retail trading, we use a MODIFIED CONTRARIAN approach:
        - Extreme IV + Extreme Skew = Follow the skew (momentum)
        - Moderate IV + Moderate Skew = Fade the skew (contrarian)
        
        High IV + Positive Skew:
        - Could mean: Panic hedging or speculative put buying
        - If IV is extreme (>85%), likely panic → SHORT (follow momentum)
        - If IV is moderate (75-85%), could be hedged longs → LONG (contrarian)
        
        Low IV + Negative Skew:
        - Could mean: Complacency or speculative call buying
        - If IV is extreme (<25%), likely complacency → LONG (follow momentum)
        - If IV is moderate (25-40%), could be crowded longs → SHORT (contrarian)
        
        Args:
            iv_percentile: IV percentile
            iv_skew: IV skew value
            atm_iv: At-the-money IV
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        # Use value-based thresholds for crypto (more reliable)
        iv_high_value = self.config.iv_high_value  # Default 0.80 (80% annualized)
        iv_low_value = self.config.iv_low_value     # Default 0.40 (40% annualized)
        
        # Determine IV state using BOTH value and percentile
        is_high_iv = atm_iv >= iv_high_value or iv_percentile >= self.config.iv_high_threshold
        is_low_iv = atm_iv <= iv_low_value or iv_percentile <= self.config.iv_low_threshold
        is_extreme_high_iv = atm_iv >= 1.0 or iv_percentile >= 0.90  # 100%+ IV or 90th percentile
        is_extreme_low_iv = atm_iv <= 0.25 or iv_percentile <= 0.10  # 25% IV or 10th percentile
        
        # High IV regime
        if is_high_iv:
            # IMPROVED: IV-004 - Distinguish between extreme and moderate IV
            if iv_skew > 0.05:  # Significant positive skew (put demand)
                if is_extreme_high_iv:
                    # Extreme IV + positive skew = panic pricing → SHORT (follow momentum)
                    # High put demand confirms downside fear
                    return SignalDirection.SHORT, 0.75
                else:
                    # Moderate high IV + positive skew = could be institutional hedging
                    # Institutions hedging longs = contrarian LONG signal
                    # This is the key fix: don't always SHORT on positive skew
                    return SignalDirection.LONG, 0.45  # Contrarian signal
            elif iv_skew > 0:
                if is_extreme_high_iv:
                    return SignalDirection.SHORT, 0.55
                else:
                    return SignalDirection.NEUTRAL, 0.3
            else:
                # High IV but negative/neutral skew
                # Could indicate call demand despite high IV
                return SignalDirection.NEUTRAL, 0.3
        
        # Low IV regime
        elif is_low_iv:
            if iv_skew < -0.05:  # Significant negative skew (call demand)
                if is_extreme_low_iv:
                    # Extreme low IV + call demand = potential breakout → LONG
                    return SignalDirection.LONG, 0.65
                else:
                    # Moderate low IV + call demand = could be crowded longs
                    # Contrarian: fade the call demand
                    return SignalDirection.SHORT, 0.35  # Contrarian signal
            elif iv_skew < 0:
                if is_extreme_low_iv:
                    return SignalDirection.LONG, 0.50
                else:
                    return SignalDirection.NEUTRAL, 0.3
            else:
                # Low IV with positive/neutral skew
                # BUG FIX: Previously defaulted to LONG, 0.35 — asymmetric with
                # HIGH IV default of NEUTRAL, 0.3. Low IV alone doesn't guarantee
                # bullish direction; it just means options are cheap. Without a
                # clear directional skew, NEUTRAL is the appropriate default.
                return SignalDirection.NEUTRAL, 0.3
        
        # Normal IV regime
        else:
            # If IV is trending toward high/low, provide weak signals
            if atm_iv > (iv_high_value * 0.9):  # Approaching high
                if iv_skew > 0.03:
                    return SignalDirection.SHORT, 0.25
            elif atm_iv < (iv_low_value * 1.1):  # Approaching low
                if iv_skew < -0.03:
                    return SignalDirection.LONG, 0.25
            
            return SignalDirection.NEUTRAL, 0.2
    
    def _create_empty_analysis(self, symbol: str) -> IVAnalysis:
        """Create empty IV analysis for insufficient data."""
        return IVAnalysis(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            current_iv=0.5,
            iv_rank=0.5,
            iv_percentile=0.5,
            signal=SignalDirection.NEUTRAL,
            confidence=0.0,
            iv_state="NORMAL",
        )
    
    def get_iv_summary(self, analysis: IVAnalysis) -> Dict[str, Any]:
        """
        Get summary of IV analysis.
        
        Args:
            analysis: IV analysis result
            
        Returns:
            Dictionary with IV summary
        """
        return {
            "symbol": analysis.symbol,
            "current_iv": round(analysis.current_iv, 4),
            "iv_percentile": round(analysis.iv_percentile, 3),
            "iv_state": analysis.iv_state,
            "signal": analysis.signal.value,
            "confidence": round(analysis.confidence, 2),
        }
    
    def analyze_iv_term_structure(
        self,
        chains: List[OptionsChain],
    ) -> Dict[str, Any]:
        """
        Analyze IV term structure across multiple expiries.
        
        Args:
            chains: List of options chains with different expiries
            
        Returns:
            Dictionary with term structure analysis
        """
        if not chains:
            return {"error": "No chains provided"}
        
        term_structure = []
        for chain in chains:
            atm_iv = self._calculate_atm_iv(chain)
            expiry = chain.expiry or datetime.utcnow()
            days_to_expiry = (expiry - datetime.utcnow()).days
            
            term_structure.append({
                "expiry": expiry.isoformat() if expiry else None,
                "days_to_expiry": days_to_expiry,
                "atm_iv": round(atm_iv, 4),
            })
        
        # Sort by days to expiry
        term_structure.sort(key=lambda x: x["days_to_expiry"])
        
        # Determine term structure shape
        if len(term_structure) >= 2:
            short_iv = term_structure[0]["atm_iv"]
            long_iv = term_structure[-1]["atm_iv"]
            
            if short_iv > long_iv * 1.1:
                shape = "INVERTED"  # Bearish
            elif long_iv > short_iv * 1.1:
                shape = "UPWARD"    # Normal/Neutral
            else:
                shape = "FLAT"      # Neutral
        else:
            shape = "INSUFFICIENT_DATA"
        
        return {
            "term_structure": term_structure,
            "shape": shape,
            "interpretation": self._interpret_term_structure(shape),
        }
    
    def _interpret_term_structure(self, shape: str) -> str:
        """Interpret term structure shape."""
        interpretations = {
            "INVERTED": "Short-term IV elevated - expecting near-term volatility",
            "UPWARD": "Normal term structure - long-term uncertainty",
            "FLAT": "Uniform IV across expiries - stable expectations",
            "INSUFFICIENT_DATA": "Not enough expiry data",
        }
        return interpretations.get(shape, "Unknown")
    
    def generate_term_structure_signal(
        self,
        term_structure_analysis: Dict[str, Any],
    ) -> tuple:
        """
        IMPROVED: IV-003 - Generate trading signal from IV term structure.
        
        IV Term Structure Signal Logic:
        
        Inverted Term Structure (Short IV > Long IV):
        - Short-term IV elevated relative to long-term
        - Indicates expectation of near-term volatility event
        - Often precedes significant price moves
        - Signal: Look for direction from other indicators, but prepare for volatility
        
        Upward Term Structure (Long IV > Short IV):
        - Normal market conditions
        - Long-term uncertainty priced higher than short-term
        - Signal: Neutral to continuation of current trend
        
        Flat Term Structure:
        - Uniform expectations across time
        - No significant events expected
        - Signal: Neutral
        
        Signal Strength:
        - More inverted = stronger signal
        - Steep upward = normal, weak signal
        
        Args:
            term_structure_analysis: Output from analyze_iv_term_structure()
            
        Returns:
            Tuple of (SignalDirection, confidence, signal_details)
        """
        shape = term_structure_analysis.get("shape", "INSUFFICIENT_DATA")
        term_structure = term_structure_analysis.get("term_structure", [])
        
        if shape == "INSUFFICIENT_DATA" or len(term_structure) < 2:
            return SignalDirection.NEUTRAL, 0.0, {"reason": "Insufficient expiry data"}
        
        # Calculate term structure metrics
        short_iv = term_structure[0]["atm_iv"]
        long_iv = term_structure[-1]["atm_iv"]
        short_dte = term_structure[0]["days_to_expiry"]
        long_dte = term_structure[-1]["days_to_expiry"]
        
        # Calculate inversion ratio
        if long_iv > 0:
            inversion_ratio = (short_iv - long_iv) / long_iv
        else:
            inversion_ratio = 0.0
        
        signal = SignalDirection.NEUTRAL
        confidence = 0.0
        details = {
            "shape": shape,
            "short_iv": round(short_iv, 4),
            "long_iv": round(long_iv, 4),
            "inversion_ratio": round(inversion_ratio, 4),
            "short_dte": short_dte,
            "long_dte": long_dte,
        }
        
        if shape == "INVERTED":
            # Inverted term structure - near-term volatility expected
            # The more inverted, the stronger the signal
            # However, direction is unclear from term structure alone
            # We use inversion magnitude for confidence
            
            if inversion_ratio > 0.3:
                # Strongly inverted - significant event expected
                confidence = 0.6
                details["interpretation"] = "Strongly inverted - major near-term volatility expected"
            elif inversion_ratio > 0.15:
                # Moderately inverted
                confidence = 0.4
                details["interpretation"] = "Moderately inverted - near-term event expected"
            else:
                # Slightly inverted
                confidence = 0.25
                details["interpretation"] = "Slightly inverted - minor near-term event possible"
            
            # Direction: Inverted term often precede downside moves in crypto
            # But can also precede upside breakouts
            # Use skew from other analysis for direction
            # Default to NEUTRAL with confidence for volatility expectation
            signal = SignalDirection.NEUTRAL
            details["volatility_expected"] = True
            
        elif shape == "UPWARD":
            # Normal upward sloping term structure
            # Higher long-term IV = more uncertainty about future
            
            if long_iv > short_iv * 1.3:
                # Steep upward - significant long-term uncertainty
                confidence = 0.3
                details["interpretation"] = "Steep upward - significant long-term uncertainty"
            else:
                # Normal upward - standard conditions
                confidence = 0.15
                details["interpretation"] = "Normal upward term structure"
            
            signal = SignalDirection.NEUTRAL
            details["volatility_expected"] = False
            
        else:  # FLAT
            # Flat term structure - uniform expectations
            confidence = 0.1
            signal = SignalDirection.NEUTRAL
            details["interpretation"] = "Flat term structure - stable expectations"
            details["volatility_expected"] = False
        
        return signal, round(confidence, 3), details
    
    def analyze_term_structure_from_chain(
        self,
        chain: OptionsChain,
    ) -> Dict[str, Any]:
        """
        IMPROVED: IV-003 - Extract and analyze IV term structure from a single chain.
        
        This method extracts IV data by expiration from the chain's strike data.
        It groups options by their expiration dates (extracted from symbol naming)
        and calculates IV for each expiration.
        
        Binance option symbol format: BTC-260626-140000-C (ASSET-EXPIRY-STRIKE-C/P)
        
        Args:
            chain: Options chain data (contains all expirations)
            
        Returns:
            Dictionary with term structure analysis and signal
        """
        from collections import defaultdict
        
        # Extract IV by expiration from strike data
        # We need to infer expiration from the data
        # Since OptionsChain doesn't store symbol-level expiration info directly,
        # we use the chain's avg_call_iv and avg_put_iv as proxies for the aggregate
        
        # For a proper term structure, we would need symbol-level data
        # This is a simplified version using available chain data
        
        # Check if chain has expiration info
        if hasattr(chain, 'expiry') and chain.expiry:
            # Single expiry chain
            days_to_expiry = (chain.expiry - datetime.utcnow()).days if chain.expiry else 0
            atm_iv = self._calculate_atm_iv(chain)
            
            term_structure = [{
                "expiry": chain.expiry.isoformat() if chain.expiry else None,
                "days_to_expiry": max(days_to_expiry, 0),
                "atm_iv": round(atm_iv, 4),
            }]
            
            # Single expiry - cannot determine term structure shape
            return {
                "term_structure": term_structure,
                "shape": "SINGLE_EXPIRY",
                "interpretation": "Single expiry - term structure analysis requires multiple expirations",
                "signal": SignalDirection.NEUTRAL.value,
                "confidence": 0.0,
            }
        
        # Use chain's average IVs as aggregate proxy
        # Note: This is less accurate than per-expiry analysis
        avg_iv = (chain.avg_call_iv + chain.avg_put_iv) / 2 if (chain.avg_call_iv > 0 and chain.avg_put_iv > 0) else self._calculate_atm_iv(chain)
        
        return {
            "term_structure": [{
                "expiry": "AGGREGATE",
                "days_to_expiry": 0,
                "atm_iv": round(avg_iv, 4),
            }],
            "shape": "AGGREGATE",
            "interpretation": "Aggregate IV from combined expirations - for proper term structure, fetch chains by individual expiry",
            "signal": SignalDirection.NEUTRAL.value,
            "confidence": 0.0,
            "note": "IV-003: Term structure requires fetching multiple expiry-specific chains. Use analyze_iv_term_structure() with separate chains.",
        }
