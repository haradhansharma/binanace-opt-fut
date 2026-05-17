# Module Specifications

## Module Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MODULE ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  binance_signal_generator/                                         │
│  │                                                                  │
│  ├── cli.py                    # Entry point                       │
│  │                                                                  │
│  ├── config/                   # Configuration management          │
│  │   ├── loader.py                                                 │
│  │   └── validators.py                                             │
│  │                                                                  │
│  ├── data/                     # Data fetching layer               │
│  │   ├── options_fetcher.py    # Options SDK client                │
│  │   ├── futures_fetcher.py    # Futures SDK + Sentiment APIs      │
│  │   └── cache.py                                                  │
│  │                                                                  │
│  ├── ranking/                  # ASSET RANKING                     │
│  │   ├── activity_scorer.py    # Score by Options activity         │
│  │   └── asset_selector.py     # Select top N assets              │
│  │                                                                  │
│  ├── analysis/                 # Options analysis engine           │
│  │   ├── iv_analyzer.py                                            │
│  │   ├── pcr_analyzer.py                                           │
│  │   ├── oi_analyzer.py                                            │
│  │   ├── wall_detector.py      # Detect Options walls             │
│  │   ├── max_pain.py                                               │
│  │   ├── gamma_exposure.py     # NEW: GEX calculator              │
│  │   ├── sentiment.py          # NEW: L/S + Funding analysis      │
│  │   └── signal_scorer.py                                          │
│  │                                                                  │
│  ├── whale/                    # WHALE DETECTION                   │
│  │   ├── whale_detector.py     # Asset-specific thresholds        │
│  │   └── volume_analyzer.py    # Analyze whale volumes            │
│  │                                                                  │
│  ├── validation/               # Futures validation                │
│  │   └── futures_validator.py                                      │
│  │                                                                  │
│  ├── output/                   # Signal output layer               │
│  │   ├── json_output.py        # JSON output to stdout (PRIMARY)  │
│  │   ├── signal_generator.py   # Create signal objects            │
│  │   ├── sr_levels.py          # S/R + Gamma levels               │
│  │   └── database.py           # SQLite persistence (SECONDARY)   │
│  │                                                                  │
│  └── utils/                    # Utilities                        │
│      ├── logging.py                                                │
│      └── helpers.py                                                │
│                                                                     │
│  SDK Dependencies:                                                  │
│  ├── binance-sdk-derivatives-trading-options (Official SDK)        │
│  ├── binance-sdk-derivatives-trading-usds-futures (Official SDK)   │
│  │                                                                  │
│  NOTE: No internal scheduling or Telegram notifications            │
│        These are handled externally                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 0. Data Fetching Module (SDK Integration)

### Overview

The data fetching module uses the **official Binance Python SDK** for reliable API interactions. This provides:
- Built-in rate limiting
- Automatic request signing
- Error handling and retries
- Connection pooling

### 0.1 Options Fetcher (`data/options_fetcher.py`)

Uses Options SDK for Binance Options API:

```python
# binance_signal_generator/data/options_fetcher.py

from binance_sdk_derivatives_trading_options import DerivativesTradingOptions
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class OptionsChain:
    """Options chain data for a single asset"""
    underlying: str
    spot_price: float
    timestamp: datetime
    strikes: Dict[float, 'StrikeData']
    total_call_oi: int
    total_put_oi: int
    total_call_volume: float
    total_put_volume: float

@dataclass
class StrikeData:
    """Data for a single strike"""
    strike: float
    call: 'OptionData'
    put: 'OptionData'

@dataclass
class OptionData:
    """Option data for call or put"""
    open_interest: int
    volume: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    last_price: float
    bid: float
    ask: float

class OptionsFetcher:
    """
    Fetches Options data using official Binance Options SDK.
    
    Features:
        - Asset-specific whale thresholds
        - Intraday multi-timeframe support
        - GEX calculation data
    """
    
    # Asset-specific whale thresholds
    ASSET_THRESHOLDS = {
        'BTCUSDT': {'min_premium': 500000, 'block_threshold': 2000000},
        'ETHUSDT': {'min_premium': 200000, 'block_threshold': 1000000},
        'DEFAULT': {'min_premium': 100000, 'block_threshold': 500000}
    }
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.client = DerivativesTradingOptions(
            api_key=api_key,
            api_secret=api_secret,
            base_url='https://eapi.binance.com'
        )
    
    def get_thresholds(self, symbol: str) -> Dict:
        """Get asset-specific whale thresholds."""
        return self.ASSET_THRESHOLDS.get(
            symbol.replace('USDT', 'USDT'),
            self.ASSET_THRESHOLDS['DEFAULT']
        )
    
    async def get_option_chain(self, underlying: str) -> OptionsChain:
        """Get complete options chain for an underlying."""
        ...
    
    async def get_block_trades(self, underlying: str, limit: int = 500) -> List[Dict]:
        """Get recent block trades for whale detection."""
        ...
```

### 0.2 Futures Fetcher (`data/futures_fetcher.py`)

Uses Futures SDK for USDT-M Futures API with **sentiment data**:

```python
# binance_signal_generator/data/futures_fetcher.py

from binance_sdk_derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class FuturesData:
    """Futures data for a single asset"""
    symbol: str
    price: float
    timestamp: datetime
    volume_24h: float
    open_interest: float
    funding_rate: float
    mark_price: float
    index_price: float
    high_24h: float
    low_24h: float
    price_change_pct: float

@dataclass
class SentimentData:
    """NEW: Sentiment data from L/S ratios and funding"""
    position_ratio: float          # Top trader L/S position ratio
    account_ratio: float           # Top trader L/S account ratio
    funding_rate: float            # Current funding rate
    funding_rate_avg_7d: float     # 7-day average funding
    funding_history: List[Dict]    # Historical funding rates
    timestamp: datetime

class FuturesFetcher:
    """
    Fetches USDT-M Futures data + Sentiment data.
    
    NEW: Sentiment APIs
        - Top Trader L/S Position Ratio (FREE)
        - Top Trader L/S Account Ratio (FREE)
        - Funding Rate History (Weight: 5)
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.client = DerivativesTradingUsdsFutures(
            api_key=api_key,
            api_secret=api_secret,
            base_url='https://fapi.binance.com'
        )
    
    async def get_sentiment_data(self, symbol: str) -> SentimentData:
        """
        Fetch sentiment data from multiple APIs.
        
        APIs Used:
            - top_trader_long_short_ratio_positions (FREE)
            - top_trader_long_short_ratio_accounts (FREE)
            - get_funding_rate_history (Weight: 5)
        """
        # Get L/S ratios
        position_ratio = await self._get_top_trader_position_ratio(symbol)
        account_ratio = await self._get_top_trader_account_ratio(symbol)
        
        # Get funding rate history
        funding_history = await self._get_funding_rate_history(symbol, limit=168)
        
        return SentimentData(
            position_ratio=position_ratio,
            account_ratio=account_ratio,
            funding_rate=funding_history[0]['fundingRate'] if funding_history else 0,
            funding_rate_avg_7d=self._calc_avg_funding(funding_history),
            funding_history=funding_history,
            timestamp=datetime.utcnow()
        )
    
    async def _get_top_trader_position_ratio(self, symbol: str) -> float:
        """
        Get Top Trader Long/Short Position Ratio.
        
        API: GET /futures/data/topLongShortPositionRatio
        Weight: 0 (FREE)
        IP Rate Limit: 1000/5min
        """
        response = self.client.rest_api.top_trader_long_short_ratio_positions(
            symbol=symbol,
            period="1h",
            limit=30
        )
        # Returns: longShortRatio, longAccount, shortAccount, timestamp
        if response and len(response) > 0:
            return float(response[0].get('longShortRatio', 1.0))
        return 1.0
    
    async def _get_top_trader_account_ratio(self, symbol: str) -> float:
        """
        Get Top Trader Long/Short Account Ratio.
        
        API: GET /futures/data/topLongShortAccountRatio
        Weight: 0 (FREE)
        IP Rate Limit: 1000/5min
        """
        response = self.client.rest_api.top_trader_long_short_ratio_accounts(
            symbol=symbol,
            period="1h",
            limit=30
        )
        # Returns: longShortRatio, longAccount, shortAccount, timestamp
        if response and len(response) > 0:
            return float(response[0].get('longShortRatio', 1.0))
        return 1.0
    
    async def _get_funding_rate_history(self, symbol: str, limit: int = 168) -> List[Dict]:
        """
        Get Funding Rate History.
        
        API: GET /fapi/v1/fundingRate
        Weight: 5 (shares 500/5min/IP with fundingInfo)
        """
        response = self.client.rest_api.get_funding_rate_history(
            symbol=symbol,
            limit=limit
        )
        # Returns: symbol, fundingRate, fundingTime, markPrice
        return response if response else []
```

---

## 1. Sentiment Analysis Module (NEW)

### `analysis/sentiment.py`

```python
# binance_signal_generator/analysis/sentiment.py

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class SentimentSignal(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

@dataclass
class SentimentResult:
    """Result of sentiment analysis"""
    # Raw inputs
    position_ratio: float          # Top trader position L/S ratio
    account_ratio: float           # Top trader account L/S ratio
    funding_rate: float            # Current funding rate
    funding_rate_avg_7d: float     # 7-day average funding
    
    # Processed
    funding_rate_extreme: bool     # Is funding extreme?
    combined_score: float          # Combined sentiment score (0-1)
    signal: str                    # LONG, SHORT, NEUTRAL
    is_contrarian: bool            # Contrarian signal detected
    
    # Timestamp
    timestamp: datetime

class SentimentAnalyzer:
    """
    Analyzes market sentiment from top trader ratios and funding rates.
    
    Data Sources:
        - Top Trader L/S Position Ratio (FREE): Top 20% by margin
        - Top Trader L/S Account Ratio (FREE): Top 20% accounts
        - Funding Rate History (Weight: 5): 7-day history
    
    Signal Generation:
        - Combined score from weighted inputs
        - Contrarian signals at extreme readings
    
    Configuration:
        ls_extreme_high: 2.0    # Ratio > 2.0 = extreme
        ls_extreme_low: 0.5     # Ratio < 0.5 = extreme
        use_contrarian: true    # Generate contrarian signals
    """
    
    def __init__(self, config: Dict):
        self.ls_extreme_high = config.get('ls_extreme_high', 2.0)
        self.ls_extreme_low = config.get('ls_extreme_low', 0.5)
        self.use_contrarian = config.get('use_contrarian', True)
        self.funding_extreme_threshold = config.get('funding_extreme_threshold', 0.001)
        
        # Weights for combined score
        self.weights = config.get('weights', {
            'position_ratio': 0.40,
            'account_ratio': 0.30,
            'funding_rate': 0.30
        })
    
    def analyze(
        self,
        position_ratio: float,
        account_ratio: float,
        funding_rate: float,
        funding_history: List[Dict]
    ) -> SentimentResult:
        """
        Calculate combined sentiment score.
        
        Returns:
            SentimentResult with all metrics
        """
        # Calculate normalized scores
        position_score = self._normalize_ratio(position_ratio)
        account_score = self._normalize_ratio(account_ratio)
        funding_score = self._normalize_funding(funding_rate, funding_history)
        
        # Combined weighted score
        combined_score = (
            self.weights['position_ratio'] * position_score +
            self.weights['account_ratio'] * account_score +
            self.weights['funding_rate'] * funding_score
        )
        
        # Determine signal
        signal = self._determine_signal(combined_score)
        
        # Check for contrarian
        is_contrarian = self._check_contrarian(position_ratio, account_ratio)
        
        # Check funding extreme
        funding_extreme = abs(funding_rate) > self.funding_extreme_threshold
        
        # If contrarian, flip signal
        if is_contrarian and self.use_contrarian:
            signal = self._flip_signal(signal)
        
        return SentimentResult(
            position_ratio=position_ratio,
            account_ratio=account_ratio,
            funding_rate=funding_rate,
            funding_rate_avg_7d=self._calc_avg_funding(funding_history),
            funding_rate_extreme=funding_extreme,
            combined_score=combined_score,
            signal=signal,
            is_contrarian=is_contrarian,
            timestamp=datetime.utcnow()
        )
    
    def _normalize_ratio(self, ratio: float) -> float:
        """
        Normalize L/S ratio to -1 to 1 range.
        
        Ratio = 1.0: Neutral
        Ratio > 1.0: Long bias (positive score)
        Ratio < 1.0: Short bias (negative score)
        """
        if ratio >= 1.0:
            # Long bias: 1.0 -> 0, 2.0 -> 0.5, 3.0 -> 0.67
            return min((ratio - 1.0) / 2.0, 1.0)
        else:
            # Short bias: 1.0 -> 0, 0.5 -> -0.5, 0.33 -> -0.67
            return max((ratio - 1.0) / 1.0, -1.0)
    
    def _normalize_funding(self, rate: float, history: List[Dict]) -> float:
        """
        Normalize funding rate.
        
        Positive funding = Longs pay shorts = Bearish pressure
        Negative funding = Shorts pay longs = Bullish pressure
        """
        # Invert: positive funding = bearish, negative = bullish
        if rate > 0:
            return -min(rate / self.funding_extreme_threshold, 1.0)
        else:
            return min(abs(rate) / self.funding_extreme_threshold, 1.0)
    
    def _determine_signal(self, score: float) -> str:
        """Determine signal from combined score."""
        if score > 0.2:
            return SentimentSignal.LONG.value
        elif score < -0.2:
            return SentimentSignal.SHORT.value
        else:
            return SentimentSignal.NEUTRAL.value
    
    def _check_contrarian(self, position_ratio: float, account_ratio: float) -> bool:
        """Check for contrarian signal conditions."""
        # Extremely bullish positioning = contrarian SHORT
        if position_ratio > self.ls_extreme_high or account_ratio > self.ls_extreme_high:
            return True
        # Extremely bearish positioning = contrarian LONG
        if position_ratio < self.ls_extreme_low or account_ratio < self.ls_extreme_low:
            return True
        return False
    
    def _flip_signal(self, signal: str) -> str:
        """Flip signal for contrarian."""
        if signal == SentimentSignal.LONG.value:
            return SentimentSignal.SHORT.value
        elif signal == SentimentSignal.SHORT.value:
            return SentimentSignal.LONG.value
        return signal
```

---

## 2. Gamma Exposure Module (NEW)

### `analysis/gamma_exposure.py`

```python
# binance_signal_generator/analysis/gamma_exposure.py

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import math
import logging

logger = logging.getLogger(__name__)

class GEXRegime(Enum):
    POSITIVE = "POSITIVE"    # Dealers buy dips, sell rips
    NEGATIVE = "NEGATIVE"    # Dealers sell dips, buy rips
    NEUTRAL = "NEUTRAL"

class HedgePressure(Enum):
    BUY_DIPS = "BUY_DIPS"    # Positive GEX: Dealers support on dips
    SELL_RIPS = "SELL_RIPS"  # Negative GEX: Dealers accelerate moves

@dataclass
class GammaLevel:
    """A gamma-based support/resistance level"""
    price: float
    gex: float
    strength: float
    type: str  # GAMMA_SUPPORT or GAMMA_RESISTANCE

@dataclass
class GammaExposureResult:
    """Result of gamma exposure analysis"""
    total_gex: float                    # Total gamma exposure
    gex_regime: str                     # POSITIVE, NEGATIVE, NEUTRAL
    dealer_hedge_pressure: str          # BUY_DIPS or SELL_RIPS
    gamma_flip: float                   # Price where GEX flips sign
    support_levels: List[GammaLevel]    # Gamma-based support
    resistance_levels: List[GammaLevel] # Gamma-based resistance
    gamma_risk_score: float             # Normalized risk (0-1)
    timestamp: datetime

class GammaExposureCalculator:
    """
    Calculates dealer gamma exposure from options chain.
    
    Formula:
        GEX = Σ (Gamma × OI × 100 × Spot² × 0.01)
        
        For calls: GEX_call = Gamma × OI_call × 100 × Spot² × 0.01
        For puts: GEX_put = -Gamma × OI_put × 100 × Spot² × 0.01
    
    Interpretation:
        Positive GEX:
            - Dealers are long gamma
            - They buy dips, sell rips
            - Price tends to stabilize
            - Lower volatility expected
            
        Negative GEX:
            - Dealers are short gamma
            - They sell dips, buy rips
            - Price tends to accelerate
            - Higher volatility expected
    
    Configuration:
        significant_threshold: 0.05   # Min gamma for S/R
        include_in_sr: true           # Add to S/R levels
    """
    
    def __init__(self, config: Dict):
        self.significant_threshold = config.get('significant_threshold', 0.05)
        self.include_in_sr = config.get('include_in_sr', True)
    
    def calculate(self, options_chain: 'OptionsChain') -> GammaExposureResult:
        """
        Calculate GEX from options chain data.
        
        Args:
            options_chain: Complete options chain with strike data
            
        Returns:
            GammaExposureResult with all GEX metrics
        """
        spot = options_chain.spot_price
        total_gex = 0.0
        gex_by_strike = {}
        
        for strike, data in options_chain.strikes.items():
            # Calculate GEX for calls (positive)
            call_gamma = data.call.gamma if data.call.gamma else 0
            call_oi = data.call.open_interest
            call_gex = call_gamma * call_oi * 100 * spot * spot * 0.01
            
            # Calculate GEX for puts (negative)
            put_gamma = data.put.gamma if data.put.gamma else 0
            put_oi = data.put.open_interest
            put_gex = -put_gamma * put_oi * 100 * spot * spot * 0.01
            
            # Total GEX at this strike
            strike_gex = call_gex + put_gex
            gex_by_strike[strike] = strike_gex
            total_gex += strike_gex
        
        # Determine regime
        if total_gex > 0:
            regime = GEXRegime.POSITIVE
            hedge_pressure = HedgePressure.BUY_DIPS
        elif total_gex < 0:
            regime = GEXRegime.NEGATIVE
            hedge_pressure = HedgePressure.SELL_RIPS
        else:
            regime = GEXRegime.NEUTRAL
            hedge_pressure = HedgePressure.BUY_DIPS
        
        # Find gamma flip level
        gamma_flip = self._find_gamma_flip(gex_by_strike, spot)
        
        # Find gamma-based S/R levels
        support_levels, resistance_levels = self._find_gamma_levels(
            gex_by_strike, spot
        )
        
        # Calculate risk score
        gamma_risk_score = self._calc_risk_score(total_gex)
        
        return GammaExposureResult(
            total_gex=total_gex,
            gex_regime=regime.value,
            dealer_hedge_pressure=hedge_pressure.value,
            gamma_flip=gamma_flip,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            gamma_risk_score=gamma_risk_score,
            timestamp=datetime.utcnow()
        )
    
    def _find_gamma_flip(
        self, 
        gex_by_strike: Dict[float, float],
        spot: float
    ) -> Optional[float]:
        """
        Find price level where GEX transitions from positive to negative.
        """
        sorted_strikes = sorted(gex_by_strike.keys())
        
        for i in range(len(sorted_strikes) - 1):
            strike1 = sorted_strikes[i]
            strike2 = sorted_strikes[i + 1]
            gex1 = gex_by_strike[strike1]
            gex2 = gex_by_strike[strike2]
            
            # Look for sign change
            if gex1 * gex2 < 0:
                # Linear interpolation
                ratio = abs(gex1) / (abs(gex1) + abs(gex2))
                flip = strike1 + ratio * (strike2 - strike1)
                return flip
        
        return None
    
    def _find_gamma_levels(
        self,
        gex_by_strike: Dict[float, float],
        spot: float
    ) -> Tuple[List[GammaLevel], List[GammaLevel]]:
        """Find significant gamma levels for S/R."""
        support = []
        resistance = []
        
        # Find strikes with significant GEX concentration
        max_abs_gex = max(abs(g) for g in gex_by_strike.values()) if gex_by_strike else 1
        
        for strike, gex in gex_by_strike.items():
            # Normalize significance
            significance = abs(gex) / max_abs_gex if max_abs_gex > 0 else 0
            
            if significance > self.significant_threshold:
                level = GammaLevel(
                    price=strike,
                    gex=gex,
                    strength=min(significance, 1.0),
                    type="GAMMA_SUPPORT" if gex > 0 else "GAMMA_RESISTANCE"
                )
                
                if strike < spot:
                    support.append(level)
                else:
                    resistance.append(level)
        
        # Sort by distance from spot
        support.sort(key=lambda x: abs(x.price - spot))
        resistance.sort(key=lambda x: abs(x.price - spot))
        
        return support[:3], resistance[:3]
    
    def _calc_risk_score(self, total_gex: float) -> float:
        """
        Calculate normalized risk score.
        
        Higher absolute GEX = higher risk of volatile moves.
        """
        abs_gex = abs(total_gex)
        
        # Risk thresholds (in notional terms)
        low_threshold = 10_000_000_000      # $10B
        high_threshold = 100_000_000_000    # $100B
        
        if abs_gex < low_threshold:
            return 0.2
        elif abs_gex > high_threshold:
            return 1.0
        else:
            # Linear interpolation
            return 0.2 + 0.8 * (abs_gex - low_threshold) / (high_threshold - low_threshold)
```

---

## 3. Asset-Specific Whale Detection

### `whale/whale_detector.py`

```python
# binance_signal_generator/whale/whale_detector.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class WhaleDirection(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

@dataclass
class WhaleAnalysis:
    """Aggregated whale activity analysis"""
    symbol: str
    analysis_timestamp: datetime
    
    # Volume metrics
    whale_buy_volume: float
    whale_sell_volume: float
    whale_net_volume: float
    
    # Direction
    whale_net_direction: str
    whale_activity_score: float
    
    # Trade stats
    large_trades_count: int
    avg_trade_size: float
    
    # Thresholds used (asset-specific)
    min_premium: float
    block_threshold: float

class WhaleDetector:
    """
    Detects whale activity with asset-specific thresholds.
    
    Asset Thresholds:
        BTCUSDT:  $500k min, $2M block
        ETHUSDT:  $200k min, $1M block
        Others:   $100k min, $500k block
    
    Purpose:
        Identify large player activity that may indicate
        directional bias and potential price moves.
    """
    
    ASSET_THRESHOLDS = {
        'BTCUSDT': {'min_premium': 500000, 'block_threshold': 2000000},
        'ETHUSDT': {'min_premium': 200000, 'block_threshold': 1000000},
        'DEFAULT': {'min_premium': 100000, 'block_threshold': 500000}
    }
    
    def __init__(self, config: Dict):
        self.config = config
        self.lookback_hours = config.get('lookback_hours', 24)
        
        # Allow override from config
        if 'asset_thresholds' in config:
            self.ASSET_THRESHOLDS.update(config['asset_thresholds'])
    
    def get_thresholds(self, symbol: str) -> Dict:
        """Get thresholds for specific asset."""
        return self.ASSET_THRESHOLDS.get(
            symbol,
            self.ASSET_THRESHOLDS['DEFAULT']
        )
    
    def analyze(
        self,
        recent_trades: List[dict],
        symbol: str
    ) -> WhaleAnalysis:
        """
        Analyze recent trades for whale activity.
        
        Uses asset-specific thresholds for detection.
        """
        # Get thresholds for this asset
        thresholds = self.get_thresholds(symbol)
        min_premium = thresholds['min_premium']
        block_threshold = thresholds['block_threshold']
        
        # Filter whale trades
        whale_trades = [
            t for t in recent_trades 
            if self._get_premium(t) >= min_premium
        ]
        
        if not whale_trades:
            return self._empty_analysis(symbol, min_premium, block_threshold)
        
        # Aggregate volumes
        buy_volume = sum(t.get('premium', 0) for t in whale_trades 
                        if self._is_bullish(t))
        sell_volume = sum(t.get('premium', 0) for t in whale_trades 
                         if self._is_bearish(t))
        net_volume = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        
        # Determine direction
        direction = self._determine_direction(net_volume, min_premium)
        
        # Activity score (normalized)
        activity_score = min(total_volume / 50_000_000, 1.0)
        
        return WhaleAnalysis(
            symbol=symbol,
            analysis_timestamp=datetime.utcnow(),
            whale_buy_volume=buy_volume,
            whale_sell_volume=sell_volume,
            whale_net_volume=net_volume,
            whale_net_direction=direction,
            whale_activity_score=activity_score,
            large_trades_count=len(whale_trades),
            avg_trade_size=total_volume / len(whale_trades) if whale_trades else 0,
            min_premium=min_premium,
            block_threshold=block_threshold
        )
    
    def _get_premium(self, trade: dict) -> float:
        """Extract premium from trade."""
        return float(trade.get('quote_qty', trade.get('premium', 0)))
    
    def _is_bullish(self, trade: dict) -> bool:
        """Determine if trade is bullish."""
        side = trade.get('side', 0)
        symbol = trade.get('symbol', '')
        
        # Call buy or put sell = bullish
        if 'C' in symbol and side == 1:  # Call buy
            return True
        if 'P' in symbol and side == -1:  # Put sell
            return True
        return False
    
    def _is_bearish(self, trade: dict) -> bool:
        """Determine if trade is bearish."""
        side = trade.get('side', 0)
        symbol = trade.get('symbol', '')
        
        # Put buy or call sell = bearish
        if 'P' in symbol and side == 1:  # Put buy
            return True
        if 'C' in symbol and side == -1:  # Call sell
            return True
        return False
    
    def _determine_direction(self, net_volume: float, threshold: float) -> str:
        """Determine whale direction."""
        if net_volume > threshold:
            return WhaleDirection.BULLISH.value
        elif net_volume < -threshold:
            return WhaleDirection.BEARISH.value
        return WhaleDirection.NEUTRAL.value
    
    def _empty_analysis(self, symbol: str, min_premium: float, block_threshold: float) -> WhaleAnalysis:
        """Return empty analysis when no whale activity."""
        return WhaleAnalysis(
            symbol=symbol,
            analysis_timestamp=datetime.utcnow(),
            whale_buy_volume=0.0,
            whale_sell_volume=0.0,
            whale_net_volume=0.0,
            whale_net_direction=WhaleDirection.NEUTRAL.value,
            whale_activity_score=0.0,
            large_trades_count=0,
            avg_trade_size=0.0,
            min_premium=min_premium,
            block_threshold=block_threshold
        )
```

---

## 4. Signal Scorer Module

### `analysis/signal_scorer.py`

```python
# binance_signal_generator/analysis/signal_scorer.py

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class SignalDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

class SignalStrength(Enum):
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"

@dataclass
class SignalComponents:
    """Individual signal components"""
    iv: str           # LONG, SHORT, NEUTRAL
    iv_score: float   # Confidence 0-1
    pcr: str
    pcr_score: float
    oi: str
    oi_score: float
    max_pain: str
    max_pain_score: float
    sentiment: str    # NEW
    sentiment_score: float  # NEW

@dataclass
class SignalResult:
    """Final signal result"""
    direction: str
    confidence: float
    raw_score: float
    strength: str
    components: SignalComponents

class SignalScorer:
    """
    Combines all analyzer outputs into unified signal.
    
    Weights (configurable):
        iv: 0.20
        pcr: 0.25
        oi: 0.20
        max_pain: 0.15
        sentiment: 0.20    # NEW
    """
    
    DEFAULT_WEIGHTS = {
        'iv': 0.20,
        'pcr': 0.25,
        'oi': 0.20,
        'max_pain': 0.15,
        'sentiment': 0.20
    }
    
    def __init__(self, config: Dict):
        self.weights = config.get('weights', self.DEFAULT_WEIGHTS)
    
    def score(
        self,
        iv_result: Dict,
        pcr_result: Dict,
        oi_result: Dict,
        max_pain_result: Dict,
        sentiment_result: Dict  # NEW
    ) -> SignalResult:
        """
        Calculate combined signal score.
        """
        directional_score = 0.0
        
        # Process each analyzer
        components = SignalComponents(
            iv=iv_result.get('signal', 'NEUTRAL'),
            iv_score=iv_result.get('score', 0.5),
            pcr=pcr_result.get('signal', 'NEUTRAL'),
            pcr_score=pcr_result.get('score', 0.5),
            oi=oi_result.get('signal', 'NEUTRAL'),
            oi_score=oi_result.get('score', 0.5),
            max_pain=max_pain_result.get('signal', 'NEUTRAL'),
            max_pain_score=max_pain_result.get('score', 0.5),
            sentiment=sentiment_result.get('signal', 'NEUTRAL'),
            sentiment_score=sentiment_result.get('combined_score', 0.0)
        )
        
        # Calculate weighted score
        for name, result in [
            ('iv', iv_result),
            ('pcr', pcr_result),
            ('oi', oi_result),
            ('max_pain', max_pain_result),
            ('sentiment', sentiment_result)
        ]:
            weight = self.weights.get(name, 0)
            signal = result.get('signal', 'NEUTRAL')
            score = result.get('score', result.get('combined_score', 0.5))
            
            if signal == 'LONG':
                directional_score += weight * score
            elif signal == 'SHORT':
                directional_score -= weight * score
        
        # Determine final direction
        if directional_score > 0.30:
            direction = SignalDirection.LONG.value
        elif directional_score < -0.30:
            direction = SignalDirection.SHORT.value
        else:
            direction = SignalDirection.NEUTRAL.value
        
        # Calculate confidence
        confidence = min(abs(directional_score), 1.0)
        
        # Determine strength
        strength = self._determine_strength(confidence)
        
        return SignalResult(
            direction=direction,
            confidence=confidence,
            raw_score=directional_score,
            strength=strength,
            components=components
        )
    
    def _determine_strength(self, confidence: float) -> str:
        """Determine signal strength from confidence."""
        if confidence >= 0.80:
            return SignalStrength.VERY_STRONG.value
        elif confidence >= 0.65:
            return SignalStrength.STRONG.value
        elif confidence >= 0.50:
            return SignalStrength.MODERATE.value
        else:
            return SignalStrength.WEAK.value
```

---

## Module Integration Summary

| Module | Input | Output | Weight |
|--------|-------|--------|--------|
| `iv_analyzer.py` | Options IV data | IV signal, percentile | 0.20 |
| `pcr_analyzer.py` | Put/Call OI & Volume | PCR signal, ratio | 0.25 |
| `oi_analyzer.py` | OI distribution | OI signal, concentration | 0.20 |
| `max_pain.py` | All strikes | Max pain price, distance | 0.15 |
| `sentiment.py` (NEW) | L/S ratios, Funding | Sentiment signal, score | 0.20 |
| `gamma_exposure.py` (NEW) | Options chain | GEX, flip level, S/R | - |
| `whale_detector.py` | Block trades | Whale activity, direction | - |
| `wall_detector.py` | OI at strikes | Support/Resistance levels | - |
| `signal_scorer.py` | All above | Final signal | - |
