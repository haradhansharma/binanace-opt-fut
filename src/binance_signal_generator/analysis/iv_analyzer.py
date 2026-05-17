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
        
        Signal Logic (Enhanced for crypto - Section 6.5 Priority 2):
        - High IV (>0.80 value or >75th percentile) + Positive Skew = Bearish (panic pricing)
        - Low IV (<0.40 value or <25th percentile) + Negative Skew = Bullish (complacency)
        - Normal IV = Neutral
        
        For crypto, we use BOTH value-based and percentile-based thresholds:
        - Value-based: More absolute, good for comparing across assets
        - Percentile-based: Better for relative positioning
        
        Args:
            iv_percentile: IV percentile
            iv_skew: IV skew value
            atm_iv: At-the-money IV
            
        Returns:
            Tuple of (SignalDirection, confidence)
        """
        # Use value-based thresholds for crypto (more reliable)
        # These are configurable in IVConfig
        iv_high_value = self.config.iv_high_value  # Default 0.80 (80% annualized)
        iv_low_value = self.config.iv_low_value     # Default 0.40 (40% annualized)
        
        # Determine IV state using BOTH value and percentile
        is_high_iv = atm_iv >= iv_high_value or iv_percentile >= self.config.iv_high_threshold
        is_low_iv = atm_iv <= iv_low_value or iv_percentile <= self.config.iv_low_threshold
        
        # High IV regime
        if is_high_iv:
            # Positive skew confirms bearish sentiment
            if iv_skew > 0.05:
                return SignalDirection.SHORT, 0.7
            elif iv_skew > 0:
                return SignalDirection.SHORT, 0.5
            else:
                # High IV but no skew = neutral (less bearish signal)
                # For crypto, high IV without skew still indicates potential volatility
                # Could be a neutral or slight short bias
                return SignalDirection.NEUTRAL, 0.3
        
        # Low IV regime
        elif is_low_iv:
            # Negative skew suggests bullish bias
            if iv_skew < -0.05:
                return SignalDirection.LONG, 0.6
            elif iv_skew < 0:
                return SignalDirection.LONG, 0.4
            else:
                # Low IV without skew - still potentially bullish for crypto
                # Low IV periods often precede price moves
                return SignalDirection.LONG, 0.35
        
        # Normal IV regime - use value proximity for gradient signals
        else:
            # If IV is trending toward high/low, provide weak signals
            if atm_iv > (iv_high_value * 0.9):  # Approaching high
                if iv_skew > 0:
                    return SignalDirection.SHORT, 0.25
            elif atm_iv < (iv_low_value * 1.1):  # Approaching low
                if iv_skew < 0:
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
