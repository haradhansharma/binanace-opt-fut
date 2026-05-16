"""
Whale detection module for identifying large trades in Options market.

This module detects and analyzes whale activity (large trades) in the
Binance Options market. Whale trades can indicate directional bias
and potential price moves.

Whale Definition:
- Regular whale: Trade premium > $100,000
- Block trade: Trade premium > $500,000
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict
import re

from binance_signal_generator.models import (
    OptionsChain,
    StrikeData,
    WhaleTrade,
    WhaleAnalysis,
    WhaleDirection,
)
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WhaleDetectorConfig:
    """Configuration for whale detection."""
    # Premium thresholds
    min_premium: float = 100_000       # $100k for regular whale
    block_threshold: float = 500_000   # $500k for block trade
    
    # Analysis settings
    lookback_hours: int = 24
    min_trades_for_analysis: int = 3
    
    # Sentiment thresholds
    bullish_threshold: float = 0.3     # 30% net bullish = bullish
    bearish_threshold: float = -0.3    # 30% net bearish = bearish


class WhaleDetector:
    """
    Detects and analyzes whale activity in Options market.
    
    Whale Definition:
        - Regular whale: Trade premium > $100,000
        - Block trade: Trade premium > $500,000
    
    Purpose:
        Identify large player activity that may indicate
        directional bias and potential price moves.
    
    Signal Impact:
        - Whale buying calls = Bullish signal
        - Whale buying puts = Bearish signal
        - Net whale volume direction = Confidence boost
    
    Attributes:
        config: Whale detection configuration
    """
    
    def __init__(self, config: Optional[WhaleDetectorConfig] = None):
        """
        Initialize whale detector.
        
        Args:
            config: Whale detection configuration
        """
        self.config = config or WhaleDetectorConfig()
        
        logger.info(
            "Whale detector initialized",
            extra={"data": {
                "min_premium": self.config.min_premium,
                "block_threshold": self.config.block_threshold,
                "lookback_hours": self.config.lookback_hours,
            }}
        )
    
    def analyze(
        self,
        trades: List[Dict[str, Any]],
        options_chain: OptionsChain,
    ) -> WhaleAnalysis:
        """
        Analyze trades for whale activity.
        
        Args:
            trades: List of recent trades from API
            options_chain: Current options chain for context
            
        Returns:
            WhaleAnalysis with all whale metrics
        """
        # Filter and parse whale trades
        whale_trades = self._filter_whale_trades(trades)
        
        if not whale_trades:
            logger.debug(f"No whale trades found for {options_chain.underlying}")
            return self._create_empty_analysis(options_chain.underlying)
        
        # Analyze whale activity
        analysis = self._analyze_whale_trades(whale_trades, options_chain)
        
        logger.info(
            f"Whale analysis complete for {options_chain.underlying}",
            extra={"data": {
                "whale_trades": len(whale_trades),
                "net_direction": analysis.whale_net_direction,
                "net_volume": analysis.whale_net_volume,
            }}
        )
        
        return analysis
    
    def _filter_whale_trades(
        self,
        trades: List[Dict[str, Any]],
    ) -> List[WhaleTrade]:
        """
        Filter trades to identify whale trades.
        
        Args:
            trades: List of recent trades
            
        Returns:
            List of WhaleTrade objects
        """
        whale_trades = []
        
        for trade in trades:
            premium = trade.get("premium", trade.get("quote_qty", 0))
            
            if premium >= self.config.min_premium:
                whale_trade = self._parse_trade(trade)
                if whale_trade:
                    whale_trades.append(whale_trade)
        
        return whale_trades
    
    def _parse_trade(self, trade: Dict[str, Any]) -> Optional[WhaleTrade]:
        """
        Parse raw trade data into WhaleTrade object.
        
        Args:
            trade: Raw trade dictionary
            
        Returns:
            WhaleTrade object or None
        """
        try:
            symbol = trade.get("symbol", "")
            
            # Determine option type from symbol
            option_type = self._get_option_type(symbol)
            
            # Determine strike from symbol
            strike = self._get_strike_from_symbol(symbol)
            
            # Get premium
            premium = trade.get("premium", trade.get("quote_qty", 0))
            
            # Determine if block trade
            is_block = premium >= self.config.block_threshold
            
            # Determine trade direction
            direction = trade.get("side", trade.get("direction", "UNKNOWN"))
            
            # Infer sentiment
            sentiment = self._infer_sentiment(option_type, direction)
            
            return WhaleTrade(
                trade_id=str(trade.get("trade_id", trade.get("tradeId", ""))),
                timestamp=trade.get("time", datetime.utcnow()),
                symbol=symbol,
                option_type=option_type,
                strike=strike,
                expiry=trade.get("expiry"),
                premium=float(premium),
                contracts=int(trade.get("quantity", trade.get("contracts", 0))),
                price_per_contract=float(trade.get("price", 0)),
                direction=direction,
                aggressor=trade.get("aggressor", "UNKNOWN"),
                is_block_trade=is_block,
                inferred_sentiment=sentiment,
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse trade: {e}")
            return None
    
    def _get_option_type(self, symbol: str) -> str:
        """Determine option type from symbol."""
        if "-C" in symbol or "-c" in symbol or "CALL" in symbol.upper():
            return "CALL"
        elif "-P" in symbol or "-p" in symbol or "PUT" in symbol.upper():
            return "PUT"
        else:
            return "UNKNOWN"
    
    def _get_strike_from_symbol(self, symbol: str) -> float:
        """Extract strike price from option symbol."""
        # Try common patterns: BTC-240115-42000-C or BTC240115C42000
        patterns = [
            r"-(\d+(?:\.\d+)?)-[CP]$",      # -42000-C
            r"[CP](\d+(?:\.\d+)?)$",         # C42000
            r"-(\d+(?:\.\d+)?)[CP]$",        # -42000C
        ]
        
        for pattern in patterns:
            match = re.search(pattern, symbol)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return 0.0
    
    def _infer_sentiment(self, option_type: str, direction: str) -> str:
        """
        Infer market sentiment from trade.
        
        Long call or short put = Bullish
        Long put or short call = Bearish
        
        Args:
            option_type: CALL or PUT
            direction: BUY or SELL
            
        Returns:
            BULLISH or BEARISH
        """
        direction_upper = direction.upper()
        
        if option_type == "CALL":
            # Buying calls = Bullish
            # Selling calls = Bearish (short call)
            return "BULLISH" if direction_upper == "BUY" else "BEARISH"
        elif option_type == "PUT":
            # Buying puts = Bearish
            # Selling puts = Bullish (short put)
            return "BEARISH" if direction_upper == "BUY" else "BULLISH"
        else:
            return "NEUTRAL"
    
    def _analyze_whale_trades(
        self,
        whale_trades: List[WhaleTrade],
        options_chain: OptionsChain,
    ) -> WhaleAnalysis:
        """
        Analyze whale trades for patterns and sentiment.
        
        Args:
            whale_trades: List of whale trades
            options_chain: Options chain for context
            
        Returns:
            WhaleAnalysis object
        """
        # Aggregate volumes by direction
        buy_volume = 0.0
        sell_volume = 0.0
        
        call_buy_volume = 0.0
        call_sell_volume = 0.0
        put_buy_volume = 0.0
        put_sell_volume = 0.0
        
        # Track activity by strike
        strike_activity: Dict[float, Dict[str, float]] = defaultdict(
            lambda: {"call": 0.0, "put": 0.0, "buy": 0.0, "sell": 0.0}
        )
        
        for trade in whale_trades:
            # Track by sentiment
            if trade.inferred_sentiment == "BULLISH":
                buy_volume += trade.premium
            else:
                sell_volume += trade.premium
            
            # Track by option type
            if trade.option_type == "CALL":
                if trade.direction == "BUY":
                    call_buy_volume += trade.premium
                else:
                    call_sell_volume += trade.premium
            elif trade.option_type == "PUT":
                if trade.direction == "BUY":
                    put_buy_volume += trade.premium
                else:
                    put_sell_volume += trade.premium
            
            # Track by strike
            if trade.strike > 0:
                strike_activity[trade.strike][trade.option_type.lower()] += trade.premium
                strike_activity[trade.strike][trade.direction.lower()] += trade.premium
        
        # Calculate net metrics
        net_volume = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        
        # Determine direction
        net_direction = self._determine_direction(net_volume, total_volume)
        
        # Calculate activity score
        activity_score = min(total_volume / 50_000_000, 1.0)  # $50M = max
        
        # Find notable strikes
        notable_strikes = self._find_notable_strikes(strike_activity)
        call_heavy = self._find_call_heavy_strikes(strike_activity)
        put_heavy = self._find_put_heavy_strikes(strike_activity)
        
        # Calculate confidence boost
        confidence_boost = self._calculate_confidence_boost(
            net_volume=net_volume,
            total_volume=total_volume,
            activity_score=activity_score,
        )
        
        return WhaleAnalysis(
            symbol=options_chain.underlying,
            analysis_timestamp=datetime.utcnow(),
            lookback_hours=self.config.lookback_hours,
            
            whale_buy_volume=buy_volume,
            whale_sell_volume=sell_volume,
            whale_net_volume=net_volume,
            
            whale_net_direction=net_direction,
            whale_activity_score=activity_score,
            
            large_trades_count=len(whale_trades),
            avg_trade_size=total_volume / len(whale_trades) if whale_trades else 0,
            max_single_trade=max(t.premium for t in whale_trades) if whale_trades else 0,
            
            notable_strikes=notable_strikes,
            put_heavy_strikes=put_heavy,
            call_heavy_strikes=call_heavy,
            
            confidence_boost=confidence_boost,
            signal_alignment=net_direction,
        )
    
    def _determine_direction(
        self,
        net_volume: float,
        total_volume: float,
    ) -> str:
        """
        Determine whale net direction.
        
        Args:
            net_volume: Net buy/sell volume
            total_volume: Total volume
            
        Returns:
            Direction string
        """
        if total_volume == 0:
            return "NEUTRAL"
        
        ratio = net_volume / total_volume
        
        if ratio >= self.config.bullish_threshold:
            return "BULLISH"
        elif ratio <= self.config.bearish_threshold:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _find_notable_strikes(
        self,
        strike_activity: Dict[float, Dict[str, float]],
    ) -> List[Dict[str, Any]]:
        """
        Find strikes with significant whale activity.
        
        Args:
            strike_activity: Activity by strike
            
        Returns:
            List of notable strikes
        """
        notable = []
        
        for strike, activity in strike_activity.items():
            total = activity["call"] + activity["put"]
            if total >= self.config.min_premium:
                notable.append({
                    "strike": strike,
                    "total_volume": total,
                    "call_volume": activity["call"],
                    "put_volume": activity["put"],
                    "net_volume": activity["buy"] - activity["sell"],
                })
        
        # Sort by total volume
        notable.sort(key=lambda x: x["total_volume"], reverse=True)
        
        return notable[:5]  # Top 5
    
    def _find_call_heavy_strikes(
        self,
        strike_activity: Dict[float, Dict[str, float]],
    ) -> List[float]:
        """Find strikes with more call activity."""
        strikes = []
        
        for strike, activity in strike_activity.items():
            if activity["call"] > activity["put"] * 1.5:
                strikes.append(strike)
        
        return sorted(strikes)
    
    def _find_put_heavy_strikes(
        self,
        strike_activity: Dict[float, Dict[str, float]],
    ) -> List[float]:
        """Find strikes with more put activity."""
        strikes = []
        
        for strike, activity in strike_activity.items():
            if activity["put"] > activity["call"] * 1.5:
                strikes.append(strike)
        
        return sorted(strikes)
    
    def _calculate_confidence_boost(
        self,
        net_volume: float,
        total_volume: float,
        activity_score: float,
    ) -> float:
        """
        Calculate confidence boost from whale activity.
        
        Args:
            net_volume: Net buy/sell volume
            total_volume: Total volume
            activity_score: Activity score
            
        Returns:
            Confidence boost (0-0.2)
        """
        if total_volume == 0:
            return 0.0
        
        # Strong activity and clear direction = high boost
        direction_strength = abs(net_volume / total_volume)
        
        boost = activity_score * direction_strength * 0.2
        
        return min(boost, 0.2)
    
    def _create_empty_analysis(self, symbol: str) -> WhaleAnalysis:
        """Create empty whale analysis."""
        return WhaleAnalysis(
            symbol=symbol,
            analysis_timestamp=datetime.utcnow(),
            lookback_hours=self.config.lookback_hours,
        )
    
    def analyze_block_trades(
        self,
        block_trades: List[Dict[str, Any]],
        options_chain: OptionsChain,
    ) -> WhaleAnalysis:
        """
        Analyze block trades for whale activity.
        
        This method is specifically for the block trades API which returns
        all block trades (not filtered by symbol). We filter by underlying.
        
        IMPORTANT: The quoteQty from Binance API is in BASE CURRENCY (BTC, ETH, etc.),
        NOT in USD. We need to multiply by spot price to get USD value.
        
        Example from API:
        {"symbol": "ETH-260522-2200-C", "price": "45.2", "qty": "0.01", "quoteQty": "0.452"}
        - quoteQty = 0.452 ETH (not $0.452!)
        - Real USD value = 0.452 ETH × $2,400 = $1,084.80
        
        Args:
            block_trades: List of block trades from API (all symbols)
            options_chain: Current options chain for context (includes spot_price)
            
        Returns:
            WhaleAnalysis with whale metrics
        """
        # Extract base asset (BTCUSDT -> BTC)
        base = options_chain.underlying.replace("USDT", "").replace("BUSD", "")
        
        # Get spot price for USD conversion
        spot_price = options_chain.spot_price
        
        # Filter trades for this underlying
        underlying_trades = [
            t for t in block_trades
            if t.get("symbol", "").startswith(f"{base}-")
        ]
        
        if not underlying_trades:
            logger.debug(f"No block trades found for {options_chain.underlying}")
            return self._create_empty_analysis(options_chain.underlying)
        
        # Calculate total premium in USD and identify larger trades
        # quoteQty is in base currency (BTC, ETH), need to convert to USD
        premiums_usd = []
        for trade in underlying_trades:
            # quoteQty is the premium in BASE CURRENCY (BTC, ETH, etc.)
            quote_qty = abs(float(trade.get("quoteQty", 0) or 0))
            
            # Convert to USD by multiplying by spot price
            if spot_price > 0:
                premium_usd = quote_qty * spot_price
            else:
                # Fallback: estimate from price × qty if no spot price
                price = float(trade.get("price", 0) or 0)
                qty = float(trade.get("qty", 0) or 0)
                premium_usd = price * qty
            
            premiums_usd.append(premium_usd)
        
        total_premium_usd = sum(premiums_usd)
        avg_premium_usd = total_premium_usd / len(premiums_usd) if premiums_usd else 0
        max_premium_usd = max(premiums_usd) if premiums_usd else 0
        
        # Determine "whale" trades as those above average
        # (since block trades are already filtered for size by the exchange)
        whale_threshold = max(avg_premium_usd, 100)  # At least $100 or above average
        
        # Analyze direction based on option type and side
        call_premium_usd = 0.0
        put_premium_usd = 0.0
        buy_side_premium_usd = 0.0
        sell_side_premium_usd = 0.0
        
        for trade in underlying_trades:
            symbol = trade.get("symbol", "")
            quote_qty = abs(float(trade.get("quoteQty", 0) or 0))
            side = trade.get("side", 0)  # -1 = sell, 1 = buy
            
            # Convert to USD
            if spot_price > 0:
                premium_usd = quote_qty * spot_price
            else:
                price = float(trade.get("price", 0) or 0)
                qty = float(trade.get("qty", 0) or 0)
                premium_usd = price * qty
            
            # Determine option type
            if "-C" in symbol:
                call_premium_usd += premium_usd
                # Side -1 = selling calls = bearish
                # Side 1 = buying calls = bullish
                if side == -1:
                    sell_side_premium_usd += premium_usd  # Short call = bearish
                else:
                    buy_side_premium_usd += premium_usd  # Long call = bullish
            elif "-P" in symbol:
                put_premium_usd += premium_usd
                # Side -1 = selling puts = bullish
                # Side 1 = buying puts = bearish
                if side == -1:
                    buy_side_premium_usd += premium_usd  # Short put = bullish
                else:
                    sell_side_premium_usd += premium_usd  # Long put = bearish
        
        # Net direction: positive = bullish, negative = bearish
        net_volume_usd = buy_side_premium_usd - sell_side_premium_usd
        total_volume_usd = buy_side_premium_usd + sell_side_premium_usd
        
        # Determine direction
        if total_volume_usd > 0:
            ratio = net_volume_usd / total_volume_usd
            if ratio >= self.config.bullish_threshold:
                net_direction = "BULLISH"
            elif ratio <= self.config.bearish_threshold:
                net_direction = "BEARISH"
            else:
                net_direction = "NEUTRAL"
        else:
            net_direction = "NEUTRAL"
        
        # Activity score based on number of trades and premium
        trade_count_score = min(len(underlying_trades) / 50, 1.0)
        premium_score = min(total_premium_usd / 1_000_000, 1.0)  # $1M = max
        activity_score = (trade_count_score + premium_score) / 2
        
        # Confidence boost
        direction_strength = abs(net_volume_usd / total_volume_usd) if total_volume_usd > 0 else 0
        confidence_boost = activity_score * direction_strength * 0.15
        
        logger.debug(
            f"Block trade analysis for {options_chain.underlying}: "
            f"trades={len(underlying_trades)}, total_premium=${total_premium_usd:.0f}, "
            f"net_direction={net_direction}, activity_score={activity_score:.3f}, spot=${spot_price:.2f}"
        )
        
        return WhaleAnalysis(
            symbol=options_chain.underlying,
            analysis_timestamp=datetime.utcnow(),
            lookback_hours=self.config.lookback_hours,
            
            whale_buy_volume=buy_side_premium_usd,
            whale_sell_volume=sell_side_premium_usd,
            whale_net_volume=net_volume_usd,
            
            whale_net_direction=net_direction,
            whale_activity_score=activity_score,
            
            large_trades_count=len(underlying_trades),
            avg_trade_size=avg_premium_usd,
            max_single_trade=max_premium_usd,
            
            notable_strikes=[],
            put_heavy_strikes=[],
            call_heavy_strikes=[],
            
            confidence_boost=min(confidence_boost, 0.15),
            signal_alignment=net_direction,
        )
    
    def get_whale_summary(self, analysis: WhaleAnalysis) -> Dict[str, Any]:
        """
        Get summary of whale analysis.
        
        Args:
            analysis: Whale analysis result
            
        Returns:
            Summary dictionary
        """
        return {
            "symbol": analysis.symbol,
            "net_direction": analysis.whale_net_direction,
            "buy_volume": round(analysis.whale_buy_volume, 0),
            "sell_volume": round(analysis.whale_sell_volume, 0),
            "net_volume": round(analysis.whale_net_volume, 0),
            "trade_count": analysis.large_trades_count,
            "avg_trade_size": round(analysis.avg_trade_size, 0),
            "activity_score": round(analysis.whale_activity_score, 3),
            "confidence_boost": round(analysis.confidence_boost, 3),
        }
