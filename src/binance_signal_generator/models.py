"""
Data models for the Binance Signal Generator.

This module defines all data structures used throughout the signal
generation pipeline using Python dataclasses for type safety and clarity.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class SignalDirection(Enum):
    """Trading signal direction."""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class SignalStrength(Enum):
    """Signal strength classification."""
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"


class WhaleDirection(Enum):
    """Whale activity direction."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class WallType(Enum):
    """Options wall type."""
    CALL_WALL = "CALL_WALL"  # Resistance
    PUT_WALL = "PUT_WALL"    # Support
    MAX_PAIN = "MAX_PAIN"


class ActivityDriver(Enum):
    """Primary driver of asset activity."""
    OI_CHANGE = "OI_CHANGE"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    IV_INTEREST = "IV_INTEREST"
    PCR_EXTREME = "PCR_EXTREME"
    WHALE_ACTIVITY = "WHALE_ACTIVITY"
    TOTAL_VOLUME = "TOTAL_VOLUME"


# =============================================================================
# Options Data Models
# =============================================================================

@dataclass
class OptionData:
    """Data for a single option (call or put)."""
    open_interest: int = 0
    volume: int = 0
    iv: float = 0.0  # Implied Volatility
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    change_24h: float = 0.0


@dataclass
class StrikeData:
    """Data for a single strike price."""
    strike: float
    call: OptionData = field(default_factory=OptionData)
    put: OptionData = field(default_factory=OptionData)


@dataclass
class OptionsChain:
    """
    Complete options chain for an underlying asset.
    
    Contains all strike data and aggregated metrics for Options analysis.
    """
    underlying: str
    spot_price: float
    timestamp: datetime
    strikes: Dict[float, StrikeData] = field(default_factory=dict)
    total_call_oi: int = 0
    total_put_oi: int = 0
    total_call_volume: float = 0.0
    total_put_volume: float = 0.0
    expiry: Optional[datetime] = None
    avg_call_iv: float = 0.0  # Average implied volatility for calls
    avg_put_iv: float = 0.0   # Average implied volatility for puts
    
    def get_pcr(self) -> float:
        """Calculate Put/Call Ratio based on Open Interest."""
        if self.total_call_oi == 0:
            return float('inf') if self.total_put_oi > 0 else 1.0
        return self.total_put_oi / self.total_call_oi
    
    def get_volume_pcr(self) -> float:
        """Calculate Put/Call Ratio based on Volume."""
        if self.total_call_volume == 0:
            return float('inf') if self.total_put_volume > 0 else 1.0
        return self.total_put_volume / self.total_call_volume


# =============================================================================
# Futures Data Models
# =============================================================================

@dataclass
class FuturesData:
    """USDT-M Futures data for a trading pair."""
    symbol: str
    price: float
    timestamp: datetime
    volume_24h: float = 0.0
    open_interest: float = 0.0
    funding_rate: float = 0.0
    mark_price: float = 0.0
    index_price: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    price_change_pct: float = 0.0


@dataclass
class Kline:
    """Single kline/candlestick data point."""
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime


# =============================================================================
# Activity & Ranking Models
# =============================================================================

@dataclass
class ActivityMetrics:
    """Activity metrics for asset ranking."""
    symbol: str
    timestamp: datetime
    oi_change_pct: float = 0.0
    volume_spike_score: float = 0.0
    iv_percentile: float = 0.0
    pcr_extremeness: float = 0.0
    whale_activity: float = 0.0
    total_options_volume: float = 0.0
    num_strikes_active: int = 0
    activity_score: float = 0.0
    primary_driver: str = "UNKNOWN"


@dataclass
class RankedAsset:
    """An asset selected for detailed analysis."""
    symbol: str
    rank: int
    activity_score: float
    primary_driver: str
    quick_metrics: Dict[str, Any] = field(default_factory=dict)
    selection_reason: str = ""


# =============================================================================
# Whale Detection Models
# =============================================================================

@dataclass
class WhaleTrade:
    """A single whale trade."""
    trade_id: str
    timestamp: datetime
    symbol: str
    option_type: str  # 'CALL' or 'PUT'
    strike: float
    expiry: Optional[datetime]
    premium: float  # $ value
    contracts: int
    price_per_contract: float
    direction: str  # 'BUY' or 'SELL'
    aggressor: str
    is_block_trade: bool
    inferred_sentiment: str  # 'BULLISH' or 'BEARISH'


@dataclass
class WhaleAnalysis:
    """Aggregated whale activity analysis."""
    symbol: str
    analysis_timestamp: datetime
    lookback_hours: int
    
    # Volume metrics
    whale_buy_volume: float = 0.0
    whale_sell_volume: float = 0.0
    whale_net_volume: float = 0.0
    
    # Direction
    whale_net_direction: str = "NEUTRAL"
    whale_activity_score: float = 0.0
    
    # Trade stats
    large_trades_count: int = 0
    avg_trade_size: float = 0.0
    max_single_trade: float = 0.0
    
    # Strike analysis
    notable_strikes: List[Dict] = field(default_factory=list)
    put_heavy_strikes: List[float] = field(default_factory=list)
    call_heavy_strikes: List[float] = field(default_factory=list)
    
    # Signal impact
    confidence_boost: float = 0.0
    signal_alignment: str = "NEUTRAL"


# =============================================================================
# Wall Detection Models
# =============================================================================

@dataclass
class OptionWall:
    """An Options wall (large OI concentration)."""
    strike: float
    wall_type: str  # 'CALL_WALL' or 'PUT_WALL'
    open_interest: int
    oi_percentage: float
    oi_change_24h: float = 0.0
    volume: int = 0
    volume_vs_avg: float = 1.0
    distance_from_spot: float = 0.0
    side: str = "ABOVE"  # 'ABOVE' or 'BELOW' spot
    strength_score: float = 0.0
    is_major_wall: bool = False
    whale_volume_at_strike: float = 0.0
    whale_sentiment: str = "NEUTRAL"


@dataclass
class WallAnalysis:
    """Complete wall analysis for an asset."""
    symbol: str
    spot_price: float
    timestamp: datetime
    
    put_walls: List[OptionWall] = field(default_factory=list)
    call_walls: List[OptionWall] = field(default_factory=list)
    
    strongest_put_wall: Optional[OptionWall] = None
    strongest_call_wall: Optional[OptionWall] = None
    nearest_put_wall: Optional[OptionWall] = None
    nearest_call_wall: Optional[OptionWall] = None
    
    total_walls: int = 0
    wall_intensity: float = 0.0
    wall_imbalance: float = 0.0
    
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)


# =============================================================================
# Sentiment Analysis Models (L/S Ratios, Funding Rate)
# =============================================================================

@dataclass
class LSRatioData:
    """Long/Short ratio data point."""
    timestamp: datetime
    long_short_ratio: float  # > 1 = longs dominate, < 1 = shorts dominate
    long_account: float  # Proportion of longs (0-1)
    short_account: float  # Proportion of shorts (0-1)


@dataclass
class FundingRateData:
    """Funding rate data point."""
    timestamp: datetime
    funding_rate: float  # Positive = longs pay shorts, Negative = shorts pay longs
    mark_price: float


@dataclass
class ExerciseRecord:
    """Historical option exercise record."""
    symbol: str
    strike_price: float
    real_strike_price: float
    expiry_date: datetime
    strike_result: str  # "REALISTIC_VALUE_STRICKEN" (exercised ITM) or "EXTRINSIC_VALUE_EXPIRED" (expired OTM)


@dataclass
class SentimentAnalysis:
    """
    Complete sentiment analysis from multiple sources.
    
    Combines:
    - Top Trader L/S Ratio (Positions): Top 20% traders by margin
    - Top Trader L/S Ratio (Accounts): Account-level positioning
    - Global L/S Ratio: Market-wide sentiment
    - Funding Rate: Cost of holding positions
    """
    symbol: str
    timestamp: datetime
    
    # Top Trader Position Ratio (by position size)
    top_trader_position_ratio: float = 1.0  # Latest value
    top_trader_position_trend: str = "NEUTRAL"  # "BULLISH", "BEARISH", "NEUTRAL"
    top_trader_position_score: float = 0.0  # -1 to 1
    
    # Top Trader Account Ratio (by account count)
    top_trader_account_ratio: float = 1.0
    top_trader_account_trend: str = "NEUTRAL"
    top_trader_account_score: float = 0.0
    
    # Funding Rate Analysis
    current_funding_rate: float = 0.0
    funding_rate_avg_7d: float = 0.0
    funding_rate_extreme: bool = False
    funding_rate_score: float = 0.0  # -1 to 1
    
    # Combined Sentiment
    combined_sentiment: str = "NEUTRAL"  # "BULLISH", "BEARISH", "NEUTRAL"
    sentiment_score: float = 0.0  # -1 to 1 (negative = bearish, positive = bullish)
    confidence: float = 0.0
    
    # Signal
    signal: SignalDirection = SignalDirection.NEUTRAL
    signal_confidence: float = 0.0
    
    # Contrarian Indicator
    is_contrarian_signal: bool = False  # True if extreme sentiment suggests reversal


# =============================================================================
# Gamma Exposure Models (Dealer Hedging Levels)
# =============================================================================

@dataclass
class GammaLevel:
    """Represents a significant gamma level for dealer hedging."""
    strike: float
    gex_value: float  # In $ terms
    gex_normalized: float  # As % of total
    level_type: str  # "SUPPORT", "RESISTANCE", "NEUTRAL"
    dealer_behavior: str  # Description of expected dealer behavior
    strength: float  # 0-1 strength score


@dataclass
class GammaAnalysis:
    """Results of gamma exposure analysis for dealer hedging levels."""
    symbol: str
    spot_price: float
    timestamp: datetime
    
    # Aggregate metrics
    total_gex: float = 0.0  # Total gamma exposure in $
    total_call_gex: float = 0.0
    total_put_gex: float = 0.0
    gex_per_spot: float = 0.0  # GEX normalized by spot price
    
    # Key levels
    gamma_flip: Optional[float] = None  # Price where GEX flips sign
    absolute_gamma_surface: float = 0.0  # Total absolute GEX (volatility indicator)
    
    # Support and resistance levels from GEX
    gex_support_levels: List[GammaLevel] = field(default_factory=list)
    gex_resistance_levels: List[GammaLevel] = field(default_factory=list)
    
    # Interpretation
    gex_regime: str = "NEUTRAL"  # "POSITIVE" (dealers support), "NEGATIVE" (dealers resist), "NEUTRAL"
    dealer_hedge_pressure: str = "MIXED"  # "BUY_DIPS", "SELL_RALLIES", "MIXED"
    
    # Risk metrics
    gamma_risk_score: float = 0.0  # 0-1, higher = more volatile expected


# =============================================================================
# S/R Level Models
# =============================================================================

@dataclass
class SRLevel:
    """Single support or resistance level."""
    level: int  # 1, 2, or 3
    price: float
    type: str  # 'PUT_WALL', 'CALL_WALL', 'MAX_PAIN'
    strength: float
    confidence: float
    source: str
    wall_data: Optional[Dict] = None


@dataclass
class SRLevels:
    """Complete support/resistance structure."""
    support: List[SRLevel] = field(default_factory=list)
    resistance: List[SRLevel] = field(default_factory=list)
    stop_loss: Optional[SRLevel] = None
    take_profit_levels: List[SRLevel] = field(default_factory=list)
    risk_reward_ratio: float = 0.0
    stop_distance_pct: float = 0.0
    avg_tp_distance_pct: float = 0.0


# =============================================================================
# Analysis Results
# =============================================================================

@dataclass
class IVAnalysis:
    """IV analysis result."""
    symbol: str
    timestamp: datetime
    current_iv: float
    iv_rank: float  # 0-1 percentile
    iv_percentile: float
    signal: SignalDirection
    confidence: float
    iv_state: str  # 'LOW', 'NORMAL', 'HIGH'


@dataclass
class PCRAnalysis:
    """PCR analysis result."""
    symbol: str
    timestamp: datetime
    pcr_oi: float
    pcr_volume: float
    pcr_combined: float
    signal: SignalDirection
    confidence: float
    pcr_state: str  # 'CALL_HEAVY', 'NEUTRAL', 'PUT_HEAVY'


@dataclass
class OIAnalysis:
    """Open Interest analysis result."""
    symbol: str
    timestamp: datetime
    total_oi: float
    oi_change_24h: float
    call_oi_concentration: float
    put_oi_concentration: float
    signal: SignalDirection
    confidence: float


@dataclass
class MaxPainAnalysis:
    """Max Pain analysis result."""
    symbol: str
    timestamp: datetime
    max_pain_strike: float
    current_price: float
    distance_pct: float
    call_pain: float
    put_pain: float
    signal: SignalDirection
    confidence: float
    magnet_strength: float


@dataclass
class OptionsSignal:
    """Combined options analysis signal."""
    symbol: str
    timestamp: datetime
    direction: SignalDirection
    confidence: float
    raw_score: float
    iv_analysis: Optional[IVAnalysis] = None
    pcr_analysis: Optional[PCRAnalysis] = None
    oi_analysis: Optional[OIAnalysis] = None
    max_pain_analysis: Optional[MaxPainAnalysis] = None
    whale_analysis: Optional[WhaleAnalysis] = None


# =============================================================================
# Trading Signal
# =============================================================================

@dataclass
class EntryZone:
    """Entry zone for a trade."""
    min: float
    max: float
    ideal: float


@dataclass
class StopLoss:
    """Stop loss configuration."""
    price: float
    type: str  # 'WALL_BASED', 'PERCENTAGE', 'FIXED'
    wall: Optional[Dict] = None
    distance_pct: float = 0.0


@dataclass
class TakeProfitLevel:
    """Single take profit level."""
    level: int
    price: float
    ratio: float
    distance_pct: float
    wall_type: Optional[str] = None


@dataclass
class TradingSignal:
    """
    Complete trading signal with all details.
    
    This is the main output of the signal generator, containing
    all information needed to execute a trade.
    """
    signal_id: str
    timestamp: datetime
    symbol: str
    asset_rank: int
    activity_score: float
    
    # Direction
    direction: SignalDirection
    confidence_score: float
    signal_strength: SignalStrength
    
    # Entry
    entry_zone: EntryZone
    
    # Risk management
    stop_loss: StopLoss
    take_profit_levels: List[TakeProfitLevel] = field(default_factory=list)
    
    # S/R Levels
    support_levels: List[Dict] = field(default_factory=list)
    resistance_levels: List[Dict] = field(default_factory=list)
    
    # Metrics
    whale_metrics: Dict[str, Any] = field(default_factory=dict)
    options_metrics: Dict[str, Any] = field(default_factory=dict)
    futures_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Risk/Reward
    risk_reward_ratio: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary for JSON output."""
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp.isoformat() + "Z",
            "symbol": self.symbol,
            "asset_rank": self.asset_rank,
            "activity_score": self.activity_score,
            "direction": self.direction.value,
            "confidence_score": self.confidence_score,
            "signal_strength": self.signal_strength.value,
            "entry_zone": {
                "min": self.entry_zone.min,
                "max": self.entry_zone.max,
                "ideal": self.entry_zone.ideal,
            },
            "stop_loss": {
                "price": self.stop_loss.price,
                "type": self.stop_loss.type,
                "wall": self.stop_loss.wall,
                "distance_pct": self.stop_loss.distance_pct,
            },
            "take_profit_levels": [
                {
                    "level": tp.level,
                    "price": tp.price,
                    "ratio": tp.ratio,
                    "distance_pct": tp.distance_pct,
                    "wall_type": tp.wall_type,
                }
                for tp in self.take_profit_levels
            ],
            "support_levels": self.support_levels,
            "resistance_levels": self.resistance_levels,
            "whale_metrics": self.whale_metrics,
            "options_metrics": self.options_metrics,
            "futures_metrics": self.futures_metrics,
            "risk_reward_ratio": self.risk_reward_ratio,
        }


# =============================================================================
# Pipeline Output
# =============================================================================

@dataclass
class ExecutionResult:
    """Result of a single pipeline execution."""
    execution_id: str
    timestamp: datetime
    execution_duration_seconds: float
    assets_analyzed: int
    signals_generated: int
    
    selected_assets: List[Dict] = field(default_factory=list)
    signals: List[TradingSignal] = field(default_factory=list)
    
    # Metadata
    config_path: Optional[str] = None
    api_calls_made: int = 0
    data_freshness_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "execution_id": self.execution_id,
            "timestamp": self.timestamp.isoformat() + "Z",
            "execution_duration_seconds": self.execution_duration_seconds,
            "assets_analyzed": self.assets_analyzed,
            "signals_generated": self.signals_generated,
            "selected_assets": self.selected_assets,
            "signals": [s.to_dict() for s in self.signals],
            "metadata": {
                "config_file": self.config_path,
                "api_calls_made": self.api_calls_made,
                "data_freshness_seconds": self.data_freshness_seconds,
                "errors": self.errors,
            },
        }
