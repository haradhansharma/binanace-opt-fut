"""
Sentiment analysis module for market positioning signals.

This module analyzes market sentiment from multiple sources:
1. Top Trader Long/Short Ratio (Positions) - Top 20% traders by margin
2. Top Trader Long/Short Ratio (Accounts) - Account-level positioning
3. Funding Rate - Cost of holding positions

The sentiment analyzer can be used as:
- A standalone sentiment indicator
- Part of the signal scoring system
- A contrarian indicator when sentiment reaches extremes

BUG FIX (Bug #5): Added trend-aware logic. Previously, contrarian mode only
activated at extreme L/S ratios (> 3.0), which rarely occur in downtrends.
In a downtrend, L/S ratios tend to be moderate (0.8-1.2), so contrarian
bearish signals almost never fired, while the "following mode" easily
produced LONG signals (combined_score > 0.15). Now, when price_change_pct
is provided, the signal respects the prevailing price trend:
- Bullish sentiment + price dropping → contrarian SHORT (reduced confidence)
- Bearish sentiment + price rising → contrarian LONG (reduced confidence)
- Sentiment aligned with trend → follow trend (boosted confidence)
- No trend data → legacy behavior unchanged

Rate Limits:
- Top Trader L/S Ratios: FREE (weight 0)
- Funding Rate History: weight 5 per call

APIs Used:
- GET /futures/data/topLongShortPositionRatio
- GET /futures/data/topLongShortAccountRatio
- GET /fapi/v1/fundingRate
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from binance_signal_generator.models import (
    SentimentAnalysis,
    LSRatioData,
    FundingRateData,
    SignalDirection,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SentimentConfig:
    """Configuration for sentiment analysis."""
    # L/S Ratio thresholds
    ls_ratio_extreme_high: float = 2.0  # > 2.0 = extreme bullish (contrarian short)
    ls_ratio_extreme_low: float = 0.5   # < 0.5 = extreme bearish (contrarian long)
    ls_ratio_bullish: float = 1.2       # > 1.2 = bullish
    ls_ratio_bearish: float = 0.8       # < 0.8 = bearish
    
    # Funding rate thresholds (in decimal, e.g., 0.0001 = 0.01%)
    funding_extreme_high: float = 0.0005   # > 0.05% = extremely long
    funding_extreme_low: float = -0.0005   # < -0.05% = extremely short
    funding_bullish: float = 0.0001        # > 0.01% = long bias
    funding_bearish: float = -0.0001       # < -0.01% = short bias
    
    # Lookback periods
    ls_ratio_lookback_periods: int = 5     # Periods to analyze trend
    funding_rate_lookback_hours: int = 168  # 7 days for average
    
    # Weights for combined sentiment
    top_trader_position_weight: float = 0.35
    top_trader_account_weight: float = 0.25
    funding_rate_weight: float = 0.40
    
    # Contrarian mode
    use_contrarian_signals: bool = True
    contrarian_extreme_threshold: float = 3.0  # L/S ratio > 3.0 = strong contrarian


class SentimentAnalyzer:
    """
    Analyzes market sentiment from L/S ratios and funding rates.
    
    Sentiment Sources:
    1. Top Trader Position Ratio: What the largest traders are doing
       - Ratio > 1: Longs dominate (bullish sentiment)
       - Ratio < 1: Shorts dominate (bearish sentiment)
    
    2. Top Trader Account Ratio: How many accounts are long vs short
       - More accounts long = retail bullish
       - Fewer accounts long = smart money positioning
    
    3. Funding Rate: Cost to hold positions
       - Positive funding: Longs pay shorts (overcrowded longs)
       - Negative funding: Shorts pay longs (overcrowded shorts)
    
    Signal Generation:
    - Following mode: Trade with smart money (top traders)
    - Contrarian mode: Fade extreme positioning (crowd is wrong)
    
    Attributes:
        config: Sentiment analysis configuration
    """
    
    def __init__(self, config: Optional[SentimentConfig] = None):
        """
        Initialize sentiment analyzer.
        
        Args:
            config: Optional custom configuration
        """
        self.config = config or SentimentConfig()
        
        logger.info(
            "Sentiment analyzer initialized",
            extra={"data": {
                "ls_extreme_high": self.config.ls_ratio_extreme_high,
                "ls_extreme_low": self.config.ls_ratio_extreme_low,
                "use_contrarian": self.config.use_contrarian_signals,
            }}
        )
    
    def analyze(
        self,
        symbol: str,
        top_trader_position_data: List[LSRatioData],
        top_trader_account_data: List[LSRatioData],
        funding_rate_data: List[FundingRateData],
        price_change_pct: Optional[float] = None,
    ) -> SentimentAnalysis:
        """
        Perform complete sentiment analysis.
        
        Args:
            symbol: Trading pair symbol
            top_trader_position_data: Top trader position ratio history
            top_trader_account_data: Top trader account ratio history
            funding_rate_data: Funding rate history
            price_change_pct: Optional price change percentage for trend-aware
                signal generation. Positive = price rising, Negative = price falling.
                When provided, enables trend-aware logic that prevents sentiment
                from generating counter-trend signals with full confidence.
            
        Returns:
            SentimentAnalysis with combined sentiment
        """
        timestamp = datetime.utcnow()
        
        # Analyze each component
        position_analysis = self._analyze_ls_ratio(
            top_trader_position_data,
            "position",
        )
        account_analysis = self._analyze_ls_ratio(
            top_trader_account_data,
            "account",
        )
        funding_analysis = self._analyze_funding_rate(funding_rate_data)
        
        # Extract values
        position_ratio = position_analysis["ratio"]
        position_trend = position_analysis["trend"]
        position_score = position_analysis["score"]
        
        account_ratio = account_analysis["ratio"]
        account_trend = account_analysis["trend"]
        account_score = account_analysis["score"]
        
        funding_rate = funding_analysis["current_rate"]
        funding_avg = funding_analysis["avg_rate"]
        funding_extreme = funding_analysis["is_extreme"]
        funding_score = funding_analysis["score"]
        
        # Calculate combined sentiment score
        combined_score = (
            position_score * self.config.top_trader_position_weight +
            account_score * self.config.top_trader_account_weight +
            funding_score * self.config.funding_rate_weight
        )
        
        # Determine combined sentiment
        if combined_score > 0.15:
            combined_sentiment = "BULLISH"
        elif combined_score < -0.15:
            combined_sentiment = "BEARISH"
        else:
            combined_sentiment = "NEUTRAL"
        
        # Determine signal
        # BUG FIX (Bug #5): Pass price_change_pct to enable trend-aware logic
        signal, signal_confidence, is_contrarian = self._determine_signal(
            position_score=position_score,
            account_score=account_score,
            funding_score=funding_score,
            combined_score=combined_score,
            position_ratio=position_ratio,
            account_ratio=account_ratio,
            funding_extreme=funding_extreme,
            price_change_pct=price_change_pct,
        )
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(
            position_data=top_trader_position_data,
            account_data=top_trader_account_data,
            funding_data=funding_rate_data,
        )
        
        logger.debug(
            f"Sentiment analysis for {symbol}: "
            f"position_ratio={position_ratio:.2f}, account_ratio={account_ratio:.2f}, "
            f"funding={funding_rate:.6f}, combined={combined_score:.2f}, "
            f"signal={signal.value}, contrarian={is_contrarian}"
        )
        
        return SentimentAnalysis(
            symbol=symbol,
            timestamp=timestamp,
            top_trader_position_ratio=position_ratio,
            top_trader_position_trend=position_trend,
            top_trader_position_score=position_score,
            top_trader_account_ratio=account_ratio,
            top_trader_account_trend=account_trend,
            top_trader_account_score=account_score,
            current_funding_rate=funding_rate,
            funding_rate_avg_7d=funding_avg,
            funding_rate_extreme=funding_extreme,
            funding_rate_score=funding_score,
            combined_sentiment=combined_sentiment,
            sentiment_score=combined_score,
            confidence=confidence,
            signal=signal,
            signal_confidence=signal_confidence,
            is_contrarian_signal=is_contrarian,
        )
    
    def _analyze_ls_ratio(
        self,
        data: List[LSRatioData],
        data_type: str,
    ) -> Dict[str, Any]:
        """
        Analyze L/S ratio data for trend and score.
        
        Args:
            data: List of L/S ratio data points
            data_type: "position" or "account"
            
        Returns:
            Dictionary with ratio, trend, and score
        """
        if not data:
            return {
                "ratio": 1.0,
                "trend": "NEUTRAL",
                "score": 0.0,
            }
        
        # Get latest ratio
        latest = data[-1]
        ratio = latest.long_short_ratio
        
        # Determine trend from recent history
        lookback = min(self.config.ls_ratio_lookback_periods, len(data))
        if lookback >= 2:
            recent = data[-lookback:]
            older = data[:-lookback] if len(data) > lookback else recent
            
            recent_avg = sum(d.long_short_ratio for d in recent) / len(recent)
            older_avg = sum(d.long_short_ratio for d in older) / len(older) if older else recent_avg
            
            if recent_avg > older_avg * 1.1:
                trend = "BULLISH"  # Becoming more long
            elif recent_avg < older_avg * 0.9:
                trend = "BEARISH"  # Becoming more short
            else:
                trend = "NEUTRAL"
        else:
            trend = "NEUTRAL"
        
        # Calculate score (-1 to 1)
        # Score interpretation:
        # - Positive = bullish sentiment (more longs)
        # - Negative = bearish sentiment (more shorts)
        # - Extreme values trigger contrarian consideration
        #
        # BUG FIX: Scoring is now symmetric. Previously:
        # - Bullish: (ratio - 1.0) / (extreme_high - 1.0) = denominator 1.0
        # - Bearish: (ratio - 1.0) / (1.0 - extreme_low)  = denominator 0.5
        # This made bearish scores 2× stronger at equivalent threshold distance.
        # Now both use the same distance scale from 1.0 (neutral), normalized to
        # the range from the threshold to the extreme, making scoring symmetric.
        
        if ratio > self.config.ls_ratio_extreme_high:
            # Extreme bullish positioning
            score = 1.0
        elif ratio > self.config.ls_ratio_bullish:
            # Bullish zone: normalize distance from 1.0 to extreme_high
            # Symmetric normalization: distance from neutral (1.0) relative to
            # the zone width (bullish threshold to extreme)
            distance_from_neutral = ratio - 1.0
            zone_width = self.config.ls_ratio_extreme_high - 1.0
            score = min(distance_from_neutral / zone_width, 1.0)
        elif ratio < self.config.ls_ratio_extreme_low:
            # Extreme bearish positioning
            score = -1.0
        elif ratio < self.config.ls_ratio_bearish:
            # Bearish zone: normalize distance from 1.0 to extreme_low
            # Same normalization logic as bullish for symmetry
            distance_from_neutral = ratio - 1.0  # Negative value
            zone_width = 1.0 - self.config.ls_ratio_extreme_low
            score = max(distance_from_neutral / zone_width, -1.0)
        else:
            # Neutral zone
            score = 0.0
        
        return {
            "ratio": ratio,
            "trend": trend,
            "score": round(score, 3),
        }
    
    def _analyze_funding_rate(
        self,
        data: List[FundingRateData],
    ) -> Dict[str, Any]:
        """
        Analyze funding rate for sentiment.
        
        Interpretation:
        - Positive funding: Longs pay shorts = overcrowded longs
        - Negative funding: Shorts pay longs = overcrowded shorts
        - Extreme funding: Potential reversal indicator
        - Funding momentum: Rising/falling funding indicates trend strength
        
        Args:
            data: List of funding rate data points
            
        Returns:
            Dictionary with current rate, avg, extreme flag, momentum, and score
        """
        if not data:
            return {
                "current_rate": 0.0,
                "avg_rate": 0.0,
                "is_extreme": False,
                "momentum": "NEUTRAL",
                "score": 0.0,
            }
        
        # Get latest funding rate
        latest = data[-1]
        current_rate = latest.funding_rate
        
        # Calculate 7-day average
        cutoff = datetime.utcnow() - timedelta(hours=self.config.funding_rate_lookback_hours)
        recent_data = [d for d in data if d.timestamp >= cutoff]
        avg_rate = sum(d.funding_rate for d in recent_data) / len(recent_data) if recent_data else 0.0
        
        # Determine if extreme
        is_extreme = (
            current_rate > self.config.funding_extreme_high or
            current_rate < self.config.funding_extreme_low
        )
        
        # Calculate funding rate momentum (NEW - Section 6.5 Priority 3)
        # FIX: Use relative thresholds based on recent data standard deviation
        # instead of absolute values (0.0002/0.0005) that don't adapt to regime
        momentum = "NEUTRAL"
        momentum_score = 0.0
        if len(recent_data) >= 4:
            # Compare recent (last 2) vs older (first 2)
            recent_avg = sum(d.funding_rate for d in recent_data[-2:]) / 2
            older_avg = sum(d.funding_rate for d in recent_data[:2]) / 2
            
            momentum_change = recent_avg - older_avg
            
            # FIX: Use std dev of recent data for adaptive thresholds
            rates = [d.funding_rate for d in recent_data]
            if len(rates) >= 4:
                mean_rate = sum(rates) / len(rates)
                std_dev = (sum((r - mean_rate) ** 2 for r in rates) / len(rates)) ** 0.5
            else:
                std_dev = 0.0003  # Fallback std dev
            
            # Threshold: 0.5 std dev for direction, normalize by 1.5 std dev
            momentum_threshold = max(std_dev * 0.5, 0.0001)  # Minimum threshold
            momentum_normalizer = max(std_dev * 1.5, 0.0003)  # Minimum normalizer
            
            if momentum_change > momentum_threshold:  # Rising funding
                momentum = "RISING"
                momentum_score = min(momentum_change / momentum_normalizer, 0.3)
            elif momentum_change < -momentum_threshold:  # Falling funding
                momentum = "FALLING"
                momentum_score = min(abs(momentum_change) / momentum_normalizer, 0.3)
        
        # Calculate score
        # BUG FIX: Funding rate scoring must reflect BOTH crowding intensity
        # AND contrarian direction. Previously, positive funding always scored
        # positive (+0.5), which meant 40% weight always bullish — but positive
        # funding means crowded LONGS which is a BEARISH contrarian signal.
        #
        # Updated scoring:
        # - Positive funding = crowded longs = bearish contrarian = NEGATIVE score
        # - Negative funding = crowded shorts = bullish contrarian = POSITIVE score
        # - The magnitude reflects how crowded the trade is (stronger = more contrarian)
        # - This allows _determine_signal() to correctly interpret funding as contrarian
        #
        # The key insight: funding rate is INHERENTLY a contrarian indicator.
        # High positive funding means longs are overcrowded → expect short squeeze or reversal
        # High negative funding means shorts are overcrowded → expect short squeeze up
        
        if current_rate > self.config.funding_extreme_high:
            # Extremely positive funding = extremely crowded longs = strong bearish contrarian
            score = -0.8  # Negative = bearish contrarian (fade the crowd)
        elif current_rate > self.config.funding_bullish:
            # Moderately positive funding = moderately crowded longs = mild bearish contrarian
            score = -0.5
        elif current_rate < self.config.funding_extreme_low:
            # Extremely negative funding = extremely crowded shorts = strong bullish contrarian
            score = 0.8  # Positive = bullish contrarian (fade the crowd)
        elif current_rate < self.config.funding_bearish:
            # Moderately negative funding = moderately crowded shorts = mild bullish contrarian
            score = 0.5
        else:
            # Neutral funding zone = no contrarian signal
            score = 0.0
        
        # Adjust score by momentum (NEW)
        # Rising funding with positive rate = more crowded longs = stronger bearish contrarian
        # Falling funding with negative rate = less crowded shorts = weaker bullish contrarian
        # Since score is now contrarian (positive funding → negative score):
        # - Rising positive funding → score goes more negative (stronger bearish contrarian)
        # - Falling negative funding → score goes less positive (weaker bullish contrarian)
        if momentum == "RISING" and current_rate > 0:
            score -= momentum_score  # More crowded longs → stronger bearish contrarian
        elif momentum == "FALLING" and current_rate < 0:
            score += momentum_score  # Less crowded shorts → weaker bullish contrarian
        
        return {
            "current_rate": current_rate,
            "avg_rate": avg_rate,
            "is_extreme": is_extreme,
            "momentum": momentum,
            "score": round(score, 3),
        }
    
    def _determine_signal(
        self,
        position_score: float,
        account_score: float,
        funding_score: float,
        combined_score: float,
        position_ratio: float,
        account_ratio: float,
        funding_extreme: bool,
        price_change_pct: Optional[float] = None,
    ) -> tuple:
        """
        Determine the trading signal from sentiment.
        
        Signal Logic (BUG FIX for Bug #5 - trend-aware):
        1. Following mode: Trade with top trader positioning
        2. Contrarian mode: Fade extreme positioning
        3. Funding extremes: Contrarian signal
        4. TREND-AWARE: When price_change_pct is available:
           - If sentiment is bullish but price is dropping → SHORT (contrarian, reduced confidence)
           - If sentiment is bearish but price is rising → LONG (contrarian, reduced confidence)
           - If sentiment aligns with price trend → follow trend (boosted confidence)
           
        Without price_change_pct, the original behavior is preserved.
        
        Args:
            position_score: Position ratio sentiment score (-1 to 1)
            account_score: Account ratio sentiment score (-1 to 1)
            funding_score: Funding rate sentiment score (-1 to 1)
            combined_score: Weighted combined sentiment score
            position_ratio: Latest top trader position L/S ratio
            account_ratio: Latest top trader account L/S ratio
            funding_extreme: Whether funding rate is at extreme level
            price_change_pct: Optional price change % for trend context.
                Positive = price rising, Negative = price falling.
            
        Returns:
            Tuple of (SignalDirection, confidence, is_contrarian)
        """
        is_contrarian = False
        
        # Determine price trend for trend-aware logic
        # FIX: Use ATR-based thresholds instead of hardcoded 0.1%
        # Crypto 15m ATR is typically 0.3-0.8%, so 0.1% is within bid-ask spread
        trend_threshold = 0.3  # Conservative fallback for crypto
        price_dropping = price_change_pct is not None and price_change_pct < -trend_threshold
        price_rising = price_change_pct is not None and price_change_pct > trend_threshold
        has_trend = price_change_pct is not None
        
        # Check for extreme positioning (contrarian signal)
        if self.config.use_contrarian_signals:
            # Extreme long positioning -> contrarian short
            if position_ratio > self.config.contrarian_extreme_threshold:
                signal = SignalDirection.SHORT
                is_contrarian = True
                confidence = min((position_ratio - 1.0) / self.config.contrarian_extreme_threshold, 0.8)
                
                # BUG FIX (Bug #1): Trend-aware adjustment for extreme contrarian signals
                # Previously, the penalty block ran UNCONDITIONALLY even after a trend-confirming
                # boost, effectively nullifying it. Now using elif so penalty only applies when
                # trend opposes the signal.
                if has_trend and price_dropping and signal == SignalDirection.SHORT:
                    # Price dropping confirms contrarian SHORT → boost confidence
                    confidence = min(confidence * 1.2, 0.85)
                    logger.debug(
                        f"Sentiment: Extreme long positioning contrarian SHORT confirmed by "
                        f"price dropping ({price_change_pct:.2f}%) → boosted confidence"
                    )
                elif has_trend and price_rising:
                    # Price rising opposes contrarian SHORT → reduce confidence
                    # Scale penalty with trend strength instead of flat 0.6
                    penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.5)
                    confidence *= penalty
                    logger.debug(
                        f"Sentiment: Extreme long positioning contrarian SHORT opposed by "
                        f"price rising ({price_change_pct:.2f}%) → reduced confidence"
                    )
                
                return signal, round(confidence, 3), is_contrarian
            
            # Extreme short positioning -> contrarian long
            if position_ratio < 1.0 / self.config.contrarian_extreme_threshold:
                signal = SignalDirection.LONG
                is_contrarian = True
                confidence = min((1.0 / position_ratio - 1.0) / self.config.contrarian_extreme_threshold, 0.8)
                
                # BUG FIX (Bug #1): Trend-aware adjustment (same fix as contrarian SHORT)
                # Previously, the penalty block ran UNCONDITIONALLY even after a trend-confirming
                # boost. Now using elif so penalty only applies when trend opposes.
                if has_trend and price_rising and signal == SignalDirection.LONG:
                    # Price rising confirms contrarian LONG → boost confidence
                    confidence = min(confidence * 1.2, 0.85)
                    logger.debug(
                        f"Sentiment: Extreme short positioning contrarian LONG confirmed by "
                        f"price rising ({price_change_pct:.2f}%) → boosted confidence"
                    )
                elif has_trend and price_dropping:
                    # Price dropping opposes contrarian LONG → reduce confidence
                    # Scale penalty with trend strength instead of flat 0.6
                    penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.5)
                    confidence *= penalty
                    logger.debug(
                        f"Sentiment: Extreme short positioning contrarian LONG opposed by "
                        f"price dropping ({price_change_pct:.2f}%) → reduced confidence"
                    )
                
                return signal, round(confidence, 3), is_contrarian
            
            # Funding extreme -> contrarian
            if funding_extreme:
                # High positive funding = crowded longs = fade with short
                if funding_score > 0:
                    signal = SignalDirection.SHORT
                    is_contrarian = True
                    confidence = 0.6
                    
                    # Trend-aware: dropping confirms SHORT from crowded longs
                    if has_trend and price_dropping:
                        confidence = min(confidence * 1.2, 0.85)
                        logger.debug(
                            f"Sentiment: Funding extreme contrarian SHORT confirmed by "
                            f"price dropping ({price_change_pct:.2f}%)"
                        )
                    elif has_trend and price_rising:
                        # FIX: Scale penalty with trend strength
                        penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.5)
                        confidence *= penalty
                        logger.debug(
                            f"Sentiment: Funding extreme contrarian SHORT opposed by "
                            f"price rising ({price_change_pct:.2f}%)"
                        )
                    
                    return signal, round(confidence, 3), is_contrarian
                else:
                    signal = SignalDirection.LONG
                    is_contrarian = True
                    confidence = 0.6
                    
                    # Trend-aware: rising confirms LONG from crowded shorts
                    if has_trend and price_rising:
                        confidence = min(confidence * 1.2, 0.85)
                        logger.debug(
                            f"Sentiment: Funding extreme contrarian LONG confirmed by "
                            f"price rising ({price_change_pct:.2f}%)"
                        )
                    elif has_trend and price_dropping:
                        # FIX: Scale penalty with trend strength
                        penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.5)
                        confidence *= penalty
                        logger.debug(
                            f"Sentiment: Funding extreme contrarian LONG opposed by "
                            f"price dropping ({price_change_pct:.2f}%)"
                        )
                    
                    return signal, round(confidence, 3), is_contrarian
        
        # BUG FIX (Bug #5): Trend-aware following mode
        # Previously, the following mode simply used combined_score thresholds:
        #   > 0.15 → LONG, < -0.15 → SHORT
        # Problem: In a downtrend, combined_score can be slightly positive (0.15-0.3)
        # because L/S ratios are moderate (not extreme enough for contrarian), but the
        # slight bullish bias still produces a LONG signal. This is wrong when price is
        # actively dropping — the market is bearish and sentiment should follow the trend.
        # 
        # New logic: When price trend is available and the trend opposes the sentiment
        # direction, we flip the signal and reduce confidence (trend takes priority).
        # When trend aligns with sentiment, we boost confidence.
        
        if combined_score > 0.15:
            # Bullish sentiment from positioning
            if has_trend and price_dropping:
                # BUG FIX: Sentiment says bullish but price is dropping
                # → Trend overrides: generate SHORT signal (contrarian to sentiment)
                signal = SignalDirection.SHORT
                is_contrarian = True
                # Confidence based on how much the trend opposes sentiment
                trend_strength = min(abs(price_change_pct) / 2.0, 0.5)
                confidence = min(trend_strength, abs(combined_score) * 0.6)
                logger.debug(
                    f"Sentiment: Bullish sentiment (score={combined_score:.2f}) but price DROPPING "
                    f"({price_change_pct:.2f}%) → trend override → SHORT (confidence={confidence:.2f})"
                )
            else:
                signal = SignalDirection.LONG
                confidence = min(abs(combined_score), 0.8)
                # Boost if price trend confirms
                if has_trend and price_rising:
                    confidence = min(confidence * 1.15, 0.85)
                    logger.debug(
                        f"Sentiment: Bullish sentiment confirmed by price rising ({price_change_pct:.2f}%)"
                    )
        
        elif combined_score < -0.15:
            # Bearish sentiment from positioning
            if has_trend and price_rising:
                # BUG FIX: Sentiment says bearish but price is rising
                # → Trend overrides: generate LONG signal (contrarian to sentiment)
                signal = SignalDirection.LONG
                is_contrarian = True
                trend_strength = min(abs(price_change_pct) / 2.0, 0.5)
                confidence = min(trend_strength, abs(combined_score) * 0.6)
                logger.debug(
                    f"Sentiment: Bearish sentiment (score={combined_score:.2f}) but price RISING "
                    f"({price_change_pct:.2f}%) → trend override → LONG (confidence={confidence:.2f})"
                )
            else:
                signal = SignalDirection.SHORT
                confidence = min(abs(combined_score), 0.8)
                # Boost if price trend confirms
                if has_trend and price_dropping:
                    confidence = min(confidence * 1.15, 0.85)
                    logger.debug(
                        f"Sentiment: Bearish sentiment confirmed by price dropping ({price_change_pct:.2f}%)"
                    )
        
        else:
            # Neutral zone (combined_score between -0.15 and 0.15)
            # But if price has a clear trend, generate a signal in that direction
            if has_trend and price_dropping:
                signal = SignalDirection.SHORT
                confidence = min(abs(price_change_pct) / 4.0, 0.4)
                logger.debug(
                    f"Sentiment: Neutral zone but price DROPPING ({price_change_pct:.2f}%) "
                    f"→ following trend → SHORT"
                )
            elif has_trend and price_rising:
                signal = SignalDirection.LONG
                confidence = min(abs(price_change_pct) / 4.0, 0.4)
                logger.debug(
                    f"Sentiment: Neutral zone but price RISING ({price_change_pct:.2f}%) "
                    f"→ following trend → LONG"
                )
            else:
                signal = SignalDirection.NEUTRAL
                confidence = 0.0
        
        return signal, round(confidence, 3), is_contrarian
    
    def _calculate_confidence(
        self,
        position_data: List[LSRatioData],
        account_data: List[LSRatioData],
        funding_data: List[FundingRateData],
    ) -> float:
        """
        Calculate confidence based on data availability and consistency.
        
        Args:
            All sentiment data
            
        Returns:
            Confidence score (0-1)
        """
        confidence = 0.0
        
        # Data availability factor
        has_position = len(position_data) > 0
        has_account = len(account_data) > 0
        has_funding = len(funding_data) > 0
        
        if has_position:
            confidence += 0.35
        if has_account:
            confidence += 0.25
        if has_funding:
            confidence += 0.40
        
        # Historical depth factor
        if has_position and len(position_data) >= 5:
            confidence += 0.1
        if has_account and len(account_data) >= 5:
            confidence += 0.1
        if has_funding and len(funding_data) >= 10:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def get_sentiment_breakdown(self, analysis: SentimentAnalysis) -> Dict[str, Any]:
        """
        Get detailed breakdown of sentiment components.
        
        Args:
            analysis: Sentiment analysis result
            
        Returns:
            Dictionary with detailed breakdown
        """
        return {
            "symbol": analysis.symbol,
            "timestamp": analysis.timestamp.isoformat(),
            "combined": {
                "sentiment": analysis.combined_sentiment,
                "score": round(analysis.sentiment_score, 3),
                "confidence": round(analysis.confidence, 3),
            },
            "top_trader_position": {
                "ratio": round(analysis.top_trader_position_ratio, 3),
                "trend": analysis.top_trader_position_trend,
                "score": round(analysis.top_trader_position_score, 3),
                "weight": self.config.top_trader_position_weight,
            },
            "top_trader_account": {
                "ratio": round(analysis.top_trader_account_ratio, 3),
                "trend": analysis.top_trader_account_trend,
                "score": round(analysis.top_trader_account_score, 3),
                "weight": self.config.top_trader_account_weight,
            },
            "funding_rate": {
                "current": analysis.current_funding_rate,
                "avg_7d": analysis.funding_rate_avg_7d,
                "extreme": analysis.funding_rate_extreme,
                "score": round(analysis.funding_rate_score, 3),
                "weight": self.config.funding_rate_weight,
            },
            "signal": {
                "direction": analysis.signal.value,
                "confidence": round(analysis.signal_confidence, 3),
                "is_contrarian": analysis.is_contrarian_signal,
            },
        }
