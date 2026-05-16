"""
Whale volume analyzer for aggregating whale trading activity.

This module provides additional analysis on whale trading volumes,
including time-based patterns, strike concentration, and flow analysis.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import defaultdict

from binance_signal_generator.models import WhaleTrade, WhaleAnalysis
from binance_signal_generator.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VolumeAnalyzerConfig:
    """Configuration for volume analyzer."""
    # Time buckets for analysis
    time_buckets: int = 4  # Divide lookback into 4 buckets
    
    # Concentration thresholds
    high_concentration_threshold: float = 0.3  # 30% at one strike


class WhaleVolumeAnalyzer:
    """
    Analyzes whale volume patterns and concentration.
    
    Analysis Types:
    1. Time-based volume flow (is whale activity increasing/decreasing)
    2. Strike concentration (where are whales active)
    3. Call vs Put volume comparison
    4. Block trade impact
    
    Attributes:
        config: Volume analyzer configuration
    """
    
    def __init__(self, config: Optional[VolumeAnalyzerConfig] = None):
        """
        Initialize volume analyzer.
        
        Args:
            config: Volume analyzer configuration
        """
        self.config = config or VolumeAnalyzerConfig()
        
        logger.info("Whale volume analyzer initialized")
    
    def analyze(
        self,
        whale_trades: List[WhaleTrade],
        whale_analysis: WhaleAnalysis,
    ) -> Dict[str, Any]:
        """
        Perform detailed volume analysis.
        
        Args:
            whale_trades: List of whale trades
            whale_analysis: Basic whale analysis
            
        Returns:
            Dictionary with volume analysis
        """
        if not whale_trades:
            return self._empty_analysis()
        
        # Time-based analysis
        time_analysis = self._analyze_time_pattern(whale_trades)
        
        # Concentration analysis
        concentration = self._analyze_concentration(whale_trades)
        
        # Flow analysis
        flow = self._analyze_flow(whale_trades)
        
        # Block trade analysis
        blocks = self._analyze_block_trades(whale_trades)
        
        return {
            "time_pattern": time_analysis,
            "concentration": concentration,
            "flow": flow,
            "block_trades": blocks,
            "summary": self._create_summary(
                time_analysis, concentration, flow, blocks
            ),
        }
    
    def _analyze_time_pattern(
        self,
        whale_trades: List[WhaleTrade],
    ) -> Dict[str, Any]:
        """
        Analyze whale activity over time.
        
        Args:
            whale_trades: List of whale trades
            
        Returns:
            Time pattern analysis
        """
        if not whale_trades:
            return {}
        
        # Sort by time
        sorted_trades = sorted(whale_trades, key=lambda t: t.timestamp)
        
        # Divide into time buckets
        start_time = sorted_trades[0].timestamp
        end_time = sorted_trades[-1].timestamp
        
        if start_time == end_time:
            return {"pattern": "SINGLE_POINT", "buckets": []}
        
        bucket_duration = (end_time - start_time) / self.config.time_buckets
        
        buckets = []
        for i in range(self.config.time_buckets):
            bucket_start = start_time + bucket_duration * i
            bucket_end = start_time + bucket_duration * (i + 1)
            
            bucket_trades = [
                t for t in sorted_trades
                if bucket_start <= t.timestamp < bucket_end
            ]
            
            buy_vol = sum(t.premium for t in bucket_trades if t.inferred_sentiment == "BULLISH")
            sell_vol = sum(t.premium for t in bucket_trades if t.inferred_sentiment == "BEARISH")
            
            buckets.append({
                "bucket": i + 1,
                "start": bucket_start.isoformat(),
                "end": bucket_end.isoformat(),
                "trade_count": len(bucket_trades),
                "buy_volume": buy_vol,
                "sell_volume": sell_vol,
                "net_volume": buy_vol - sell_vol,
            })
        
        # Determine pattern
        net_volumes = [b["net_volume"] for b in buckets]
        
        if all(v >= 0 for v in net_volumes):
            pattern = "CONSISTENT_BUYING"
        elif all(v <= 0 for v in net_volumes):
            pattern = "CONSISTENT_SELLING"
        elif net_volumes[-1] > net_volumes[0]:
            pattern = "INCREASING_BUYING"
        elif net_volumes[-1] < net_volumes[0]:
            pattern = "INCREASING_SELLING"
        else:
            pattern = "MIXED"
        
        return {
            "pattern": pattern,
            "buckets": buckets,
        }
    
    def _analyze_concentration(
        self,
        whale_trades: List[WhaleTrade],
    ) -> Dict[str, Any]:
        """
        Analyze strike concentration of whale activity.
        
        Args:
            whale_trades: List of whale trades
            
        Returns:
            Concentration analysis
        """
        total_volume = sum(t.premium for t in whale_trades)
        
        if total_volume == 0:
            return {}
        
        # Volume by strike
        strike_volume: Dict[float, float] = defaultdict(float)
        for trade in whale_trades:
            if trade.strike > 0:
                strike_volume[trade.strike] += trade.premium
        
        # Sort by volume
        sorted_strikes = sorted(
            strike_volume.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        
        # Calculate concentration
        top_strike_concentration = 0.0
        if sorted_strikes:
            top_strike_concentration = sorted_strikes[0][1] / total_volume
        
        # Find high concentration strikes
        high_concentration = [
            {"strike": s, "volume": v, "pct": v / total_volume}
            for s, v in sorted_strikes
            if v / total_volume >= self.config.high_concentration_threshold
        ]
        
        return {
            "total_strikes": len(strike_volume),
            "top_strike": sorted_strikes[0][0] if sorted_strikes else None,
            "top_strike_volume": sorted_strikes[0][1] if sorted_strikes else 0,
            "top_strike_concentration": top_strike_concentration,
            "high_concentration_strikes": high_concentration,
            "is_concentrated": top_strike_concentration >= self.config.high_concentration_threshold,
        }
    
    def _analyze_flow(
        self,
        whale_trades: List[WhaleTrade],
    ) -> Dict[str, Any]:
        """
        Analyze whale money flow.
        
        Args:
            whale_trades: List of whale trades
            
        Returns:
            Flow analysis
        """
        call_buy = sum(t.premium for t in whale_trades if t.option_type == "CALL" and t.direction == "BUY")
        call_sell = sum(t.premium for t in whale_trades if t.option_type == "CALL" and t.direction == "SELL")
        put_buy = sum(t.premium for t in whale_trades if t.option_type == "PUT" and t.direction == "BUY")
        put_sell = sum(t.premium for t in whale_trades if t.option_type == "PUT" and t.direction == "SELL")
        
        total = call_buy + call_sell + put_buy + put_sell
        
        return {
            "call_flow": {
                "buy": call_buy,
                "sell": call_sell,
                "net": call_buy - call_sell,
            },
            "put_flow": {
                "buy": put_buy,
                "sell": put_sell,
                "net": put_buy - put_sell,
            },
            "total_call_volume": call_buy + call_sell,
            "total_put_volume": put_buy + put_sell,
            "call_put_ratio": (call_buy + call_sell) / (put_buy + put_sell) if (put_buy + put_sell) > 0 else 1.0,
            "aggressive_side": "BUYERS" if (call_buy + put_buy) > (call_sell + put_sell) else "SELLERS",
        }
    
    def _analyze_block_trades(
        self,
        whale_trades: List[WhaleTrade],
    ) -> Dict[str, Any]:
        """
        Analyze block trades (very large trades).
        
        Args:
            whale_trades: List of whale trades
            
        Returns:
            Block trade analysis
        """
        block_trades = [t for t in whale_trades if t.is_block_trade]
        
        if not block_trades:
            return {
                "count": 0,
                "total_volume": 0,
                "avg_size": 0,
            }
        
        total_volume = sum(t.premium for t in block_trades)
        
        buy_count = sum(1 for t in block_trades if t.inferred_sentiment == "BULLISH")
        sell_count = sum(1 for t in block_trades if t.inferred_sentiment == "BEARISH")
        
        return {
            "count": len(block_trades),
            "total_volume": total_volume,
            "avg_size": total_volume / len(block_trades),
            "max_size": max(t.premium for t in block_trades),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "sentiment": "BULLISH" if buy_count > sell_count else "BEARISH" if sell_count > buy_count else "NEUTRAL",
        }
    
    def _create_summary(
        self,
        time_analysis: Dict,
        concentration: Dict,
        flow: Dict,
        blocks: Dict,
    ) -> Dict[str, Any]:
        """Create overall summary."""
        # Determine overall whale sentiment
        call_net = flow.get("call_flow", {}).get("net", 0)
        put_net = flow.get("put_flow", {}).get("net", 0)
        
        # Positive call net = buying calls = bullish
        # Positive put net = buying puts = bearish
        overall_sentiment = "NEUTRAL"
        
        if call_net > abs(put_net) and call_net > 0:
            overall_sentiment = "BULLISH"
        elif abs(put_net) > call_net and put_net > 0:
            overall_sentiment = "BEARISH"
        
        return {
            "overall_sentiment": overall_sentiment,
            "time_pattern": time_analysis.get("pattern", "UNKNOWN"),
            "is_concentrated": concentration.get("is_concentrated", False),
            "aggressive_side": flow.get("aggressive_side", "UNKNOWN"),
            "block_sentiment": blocks.get("sentiment", "NEUTRAL"),
            "block_count": blocks.get("count", 0),
        }
    
    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis."""
        return {
            "time_pattern": {},
            "concentration": {},
            "flow": {},
            "block_trades": {},
            "summary": {
                "overall_sentiment": "NEUTRAL",
                "time_pattern": "UNKNOWN",
                "is_concentrated": False,
            },
        }
