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
│  │   ├── options_fetcher.py    # Uses binance.options SDK         │
│  │   ├── futures_fetcher.py    # Uses binance.um_futures SDK      │
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
│  │   └── signal_scorer.py                                          │
│  │                                                                  │
│  ├── whale/                    # WHALE DETECTION                   │
│  │   ├── whale_detector.py     # Detect whale trades              │
│  │   └── volume_analyzer.py    # Analyze whale volumes            │
│  │                                                                  │
│  ├── validation/               # Futures validation                │
│  │   └── futures_validator.py                                      │
│  │                                                                  │
│  ├── output/                   # Signal output layer               │
│  │   ├── json_output.py        # JSON output to stdout (PRIMARY)  │
│  │   ├── signal_generator.py   # Create signal objects            │
│  │   ├── sr_levels.py          # S/R level calculator             │
│  │   └── database.py           # SQLite persistence (SECONDARY)   │
│  │                                                                  │
│  └── utils/                    # Utilities                        │
│      ├── logging.py                                                │
│      └── helpers.py                                                │
│                                                                     │
│  SDK Dependencies:                                                  │
│  ├── binance-connector (Official Binance Python SDK)               │
│  ├── binance.um_futures (USDT-M Futures)                           │
│  └── binance.options (Binance Options)                             │
│                                                                     │
│  NOTE: No internal scheduling or Telegram notifications            │
│        These are handled externally                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 0. Data Fetching Module (SDK Integration)

### Overview

The data fetching module uses the **official Binance Connector Python SDK** for reliable API interactions. This provides:
- Built-in rate limiting
- Automatic request signing
- Error handling and retries
- Connection pooling

### SDK Installation

```bash
# Install via pip (included in project dependencies)
pip install binance-connector

# Or install the full project
pip install -e .
```

### 0.1 Options Fetcher (`data/options_fetcher.py`)

Uses `binance.options` module for Binance Options API:

```python
# binance_signal_generator/data/options_fetcher.py

from binance.options import Options
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import asyncio
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
    
    SDK Documentation:
    - https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_options
    - https://binance-docs.github.io/apidocs/options/en/
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        Initialize Options client.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet (default: False)
        """
        self.client = Options(
            key=api_key,
            secret=api_secret,
            base_url='https://testnet.binanceops.com' if testnet else 'https://eapi.binance.com'
        )
        self._rate_limiter = RateLimiter(requests_per_second=10)
    
    async def get_available_symbols(self) -> List[str]:
        """
        Get all available Options symbols.
        
        API: GET /eapi/v1/exchangeInfo
        """
        await self._rate_limiter.acquire()
        
        response = self.client.exchange_info()
        symbols = set()
        
        for symbol_info in response.get('optionSymbols', []):
            # Extract underlying (e.g., "BTCUSDT" from "BTC-240115-42000-C")
            underlying = symbol_info.get('underlying', '')
            if underlying:
                symbols.add(underlying)
        
        return list(symbols)
    
    async def get_option_chain(self, underlying: str) -> OptionsChain:
        """
        Get complete options chain for an underlying asset.
        
        API: GET /eapi/v1/optionChain
        """
        await self._rate_limiter.acquire()
        
        try:
            response = self.client.option_chain(underlying=underlying)
            
            # Parse response
            spot_price = float(response.get('underlyingPrice', 0))
            
            strikes = {}
            total_call_oi = 0
            total_put_oi = 0
            total_call_volume = 0.0
            total_put_volume = 0.0
            
            for option_data in response.get('optionChain', []):
                strike_price = float(option_data.get('strikePrice', 0))
                
                # Parse call data
                call_data = option_data.get('call', {})
                call = OptionData(
                    open_interest=int(call_data.get('openInterest', 0)),
                    volume=int(call_data.get('volume', 0)),
                    iv=float(call_data.get('impliedVolatility', 0)),
                    delta=float(call_data.get('delta', 0)),
                    gamma=float(call_data.get('gamma', 0)),
                    theta=float(call_data.get('theta', 0)),
                    vega=float(call_data.get('vega', 0)),
                    last_price=float(call_data.get('lastPrice', 0)),
                    bid=float(call_data.get('bidPrice', 0)),
                    ask=float(call_data.get('askPrice', 0))
                )
                total_call_oi += call.open_interest
                total_call_volume += call.volume * call.last_price
                
                # Parse put data
                put_data = option_data.get('put', {})
                put = OptionData(
                    open_interest=int(put_data.get('openInterest', 0)),
                    volume=int(put_data.get('volume', 0)),
                    iv=float(put_data.get('impliedVolatility', 0)),
                    delta=float(put_data.get('delta', 0)),
                    gamma=float(put_data.get('gamma', 0)),
                    theta=float(put_data.get('theta', 0)),
                    vega=float(put_data.get('vega', 0)),
                    last_price=float(put_data.get('lastPrice', 0)),
                    bid=float(put_data.get('bidPrice', 0)),
                    ask=float(put_data.get('askPrice', 0))
                )
                total_put_oi += put.open_interest
                total_put_volume += put.volume * put.last_price
                
                strikes[strike_price] = StrikeData(
                    strike=strike_price,
                    call=call,
                    put=put
                )
            
            return OptionsChain(
                underlying=underlying,
                spot_price=spot_price,
                timestamp=datetime.utcnow(),
                strikes=strikes,
                total_call_oi=total_call_oi,
                total_put_oi=total_put_oi,
                total_call_volume=total_call_volume,
                total_put_volume=total_put_volume
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch options chain for {underlying}: {e}")
            raise DataFetchError(f"Options chain fetch failed: {e}")
    
    async def get_open_interest(self, symbol: str) -> Dict:
        """
        Get open interest for a specific option symbol.
        
        API: GET /eapi/v1/openInterest
        """
        await self._rate_limiter.acquire()
        
        response = self.client.open_interest(symbol=symbol)
        return {
            'symbol': response.get('symbol'),
            'open_interest': float(response.get('openInterest', 0)),
            'time': datetime.fromtimestamp(response.get('time', 0) / 1000)
        }
    
    async def get_recent_trades(self, underlying: str, limit: int = 500) -> List[Dict]:
        """
        Get recent trades for whale detection.
        
        API: GET /eapi/v1/trades
        """
        await self._rate_limiter.acquire()
        
        response = self.client.recent_trades(
            underlying=underlying,
            limit=limit
        )
        
        trades = []
        for trade in response:
            trades.append({
                'trade_id': trade.get('id'),
                'price': float(trade.get('price', 0)),
                'qty': float(trade.get('qty', 0)),
                'quote_qty': float(trade.get('quoteQty', 0)),
                'time': datetime.fromtimestamp(trade.get('time', 0) / 1000),
                'side': trade.get('side'),  # BUY or SELL
                'symbol': trade.get('symbol'),
                'premium': float(trade.get('quoteQty', 0))  # $ value
            })
        
        return trades
    
    async def get_activity_summary(self, underlying: str) -> Dict:
        """
        Get quick activity summary for asset ranking.
        Combines multiple lightweight API calls.
        """
        await self._rate_limiter.acquire()
        
        # Get ticker
        ticker = self.client.ticker_24hr(underlying=underlying)
        
        return {
            'underlying': underlying,
            'total_volume': float(ticker.get('volume', 0)),
            'volume_change_pct': float(ticker.get('priceChangePercent', 0)),
            'oi_change_24h': 0.0,  # Would need historical data
            'iv_percentile': 0.5,  # Would need calculation
            'pcr': float(ticker.get('putCallRatio', 1.0)),
            'active_strikes': int(ticker.get('activeStrikes', 0)),
            'whale_activity_score': 0.0  # Calculated separately
        }
```

### 0.2 Futures Fetcher (`data/futures_fetcher.py`)

Uses `binance.um_futures` module for USDT-M Futures API:

```python
# binance_signal_generator/data/futures_fetcher.py

from binance.um_futures import UMFutures
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import asyncio
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
class FuturesValidationResult:
    """Validation result for futures trading conditions"""
    symbol: str
    liquidity_score: float
    trend_alignment: str
    volatility_state: str
    funding_rate_ok: bool
    passed: bool
    reasons: List[str]

class FuturesFetcher:
    """
    Fetches USDT-M Futures data using official Binance Futures SDK.
    
    SDK Documentation:
    - https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_coin_futures
    - https://binance-docs.github.io/apidocs/futures/en/
    
    Note: We use USDT-M Futures (um_futures) for trading BTCUSDT, ETHUSDT, etc.
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        Initialize USDT-M Futures client.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet (default: False)
        """
        self.client = UMFutures(
            key=api_key,
            secret=api_secret,
            base_url='https://testnet.binancefuture.com' if testnet else 'https://fapi.binance.com'
        )
        self._rate_limiter = RateLimiter(requests_per_second=10)
    
    async def get_price(self, symbol: str) -> FuturesData:
        """
        Get current price and 24hr ticker data.
        
        API: GET /fapi/v1/ticker/24hr
        """
        await self._rate_limiter.acquire()
        
        response = self.client.ticker_24hr(symbol=symbol)
        
        return FuturesData(
            symbol=symbol,
            price=float(response.get('lastPrice', 0)),
            timestamp=datetime.utcnow(),
            volume_24h=float(response.get('quoteVolume', 0)),
            open_interest=0.0,  # Fetched separately
            funding_rate=0.0,   # Fetched separately
            mark_price=float(response.get('lastPrice', 0)),
            index_price=float(response.get('lastPrice', 0)),
            high_24h=float(response.get('highPrice', 0)),
            low_24h=float(response.get('lowPrice', 0)),
            price_change_pct=float(response.get('priceChangePercent', 0))
        )
    
    async def get_all_data(self, symbol: str) -> FuturesData:
        """
        Get complete futures data for a symbol.
        Combines price, open interest, and funding rate.
        """
        # Parallel fetch for efficiency
        price_task = self.get_price(symbol)
        oi_task = self.get_open_interest(symbol)
        funding_task = self.get_funding_rate(symbol)
        mark_task = self.get_mark_price(symbol)
        
        price_data, oi_data, funding_data, mark_data = await asyncio.gather(
            price_task, oi_task, funding_task, mark_task
        )
        
        return FuturesData(
            symbol=symbol,
            price=price_data.price,
            timestamp=datetime.utcnow(),
            volume_24h=price_data.volume_24h,
            open_interest=oi_data.get('open_interest', 0),
            funding_rate=funding_data.get('funding_rate', 0),
            mark_price=mark_data.get('mark_price', 0),
            index_price=mark_data.get('index_price', 0),
            high_24h=price_data.high_24h,
            low_24h=price_data.low_24h,
            price_change_pct=price_data.price_change_pct
        )
    
    async def get_open_interest(self, symbol: str) -> Dict:
        """
        Get open interest for futures.
        
        API: GET /fapi/v1/openInterest
        """
        await self._rate_limiter.acquire()
        
        response = self.client.open_interest(symbol=symbol)
        return {
            'symbol': symbol,
            'open_interest': float(response.get('openInterest', 0)),
            'time': datetime.utcnow()
        }
    
    async def get_funding_rate(self, symbol: str) -> Dict:
        """
        Get current funding rate.
        
        API: GET /fapi/v1/fundingRate
        """
        await self._rate_limiter.acquire()
        
        response = self.client.funding_rate(symbol=symbol, limit=1)
        if response:
            return {
                'symbol': symbol,
                'funding_rate': float(response[0].get('fundingRate', 0)),
                'time': datetime.fromtimestamp(response[0].get('fundingTime', 0) / 1000)
            }
        return {'symbol': symbol, 'funding_rate': 0.0, 'time': datetime.utcnow()}
    
    async def get_mark_price(self, symbol: str) -> Dict:
        """
        Get mark price and index price.
        
        API: GET /fapi/v1/premiumIndex
        """
        await self._rate_limiter.acquire()
        
        response = self.client.mark_price(symbol=symbol)
        return {
            'symbol': symbol,
            'mark_price': float(response.get('markPrice', 0)),
            'index_price': float(response.get('indexPrice', 0)),
            'time': datetime.utcnow()
        }
    
    async def get_klines(
        self, 
        symbol: str, 
        interval: str = '15m', 
        limit: int = 100
    ) -> List[Dict]:
        """
        Get klines/candlesticks for trend analysis.
        
        API: GET /fapi/v1/klines
        
        Args:
            symbol: Trading pair
            interval: Kline interval (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of klines
        """
        await self._rate_limiter.acquire()
        
        response = self.client.klines(symbol=symbol, interval=interval, limit=limit)
        
        klines = []
        for k in response:
            klines.append({
                'open_time': datetime.fromtimestamp(k[0] / 1000),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'close_time': datetime.fromtimestamp(k[6] / 1000)
            })
        
        return klines
    
    async def check_liquidity(self, symbol: str, min_volume: float = 1_000_000) -> bool:
        """
        Check if symbol has sufficient liquidity.
        """
        data = await self.get_price(symbol)
        return data.volume_24h >= min_volume
```

### 0.3 Rate Limiter (`data/rate_limiter.py`)

Simple rate limiter for API calls:

```python
# binance_signal_generator/data/rate_limiter.py

import asyncio
import time
from dataclasses import dataclass

@dataclass
class RateLimiter:
    """Simple rate limiter for API calls"""
    requests_per_second: int = 10
    burst: int = 20
    
    def __post_init__(self):
        self._tokens = self.burst
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            
            # Replenish tokens
            self._tokens = min(
                self.burst,
                self._tokens + elapsed * self.requests_per_second
            )
            self._last_update = now
            
            if self._tokens < 1:
                # Wait for a token
                wait_time = (1 - self._tokens) / self.requests_per_second
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1
```

---

## 1. Ranking Module (NEW)

### 1.1 Activity Scorer (`ranking/activity_scorer.py`)

```python
# binance_signal_generator/ranking/activity_scorer.py

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

class ActivityDriver(Enum):
    OI_CHANGE = "OI_CHANGE"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    IV_INTEREST = "IV_INTEREST"
    PCR_EXTREME = "PCR_EXTREME"
    WHALE_ACTIVITY = "WHALE_ACTIVITY"
    TOTAL_VOLUME = "TOTAL_VOLUME"

@dataclass
class ActivityMetrics:
    """Activity metrics for a single asset"""
    symbol: str
    timestamp: datetime
    
    # Individual metrics
    oi_change_pct: float              # Open Interest change % (last 24h)
    volume_spike_score: float         # Volume vs 7-day average (0-1)
    iv_percentile: float              # Current IV percentile (0-1)
    pcr_extremeness: float            # How extreme is PCR (0-1)
    whale_activity: float             # Whale activity indicator (0-1)
    total_options_volume: float       # Total options volume in $
    num_strikes_active: int           # Strikes with significant OI
    
    # Calculated
    activity_score: float = 0.0       # Combined score (0-1)
    primary_driver: str = ""          # Main activity driver

@dataclass
class ActivityScanResult:
    """Result of activity scan across all assets"""
    timestamp: datetime
    total_assets_scanned: int
    metrics_by_symbol: Dict[str, ActivityMetrics]
    ranked_symbols: List[str]         # Symbols sorted by score
    scan_duration_seconds: float

class ActivityScorer:
    """
    Scores assets by Options market activity level.
    
    Purpose:
        Quickly scan all assets to identify which have the most
        interesting Options activity for detailed analysis.
    
    Activity Score Formula:
        score = w1*oi_change + w2*volume_spike + w3*iv_percentile 
              + w4*pcr_extreme + w5*whale_activity + w6*total_volume
    """
    
    DEFAULT_WEIGHTS = {
        ActivityDriver.OI_CHANGE: 0.25,
        ActivityDriver.VOLUME_SPIKE: 0.20,
        ActivityDriver.IV_INTEREST: 0.15,
        ActivityDriver.PCR_EXTREME: 0.15,
        ActivityDriver.WHALE_ACTIVITY: 0.15,
        ActivityDriver.TOTAL_VOLUME: 0.10
    }
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.weights = self.DEFAULT_WEIGHTS.copy()
        
        # Thresholds
        self.oi_change_max = 20.0      # 20% change = max score
        self.volume_spike_max = 5.0    # 5x average = max score
        self.total_volume_max = 100_000_000  # $100M = max score
    
    def calculate_score(self, metrics: ActivityMetrics) -> float:
        """
        Calculate normalized activity score (0-1).
        
        Higher score = More interesting activity.
        """
        # Normalize each component
        oi_change_norm = min(abs(metrics.oi_change_pct) / self.oi_change_max, 1.0)
        volume_norm = min(metrics.volume_spike_score / self.volume_spike_max, 1.0)
        iv_norm = metrics.iv_percentile
        pcr_norm = metrics.pcr_extremeness
        whale_norm = metrics.whale_activity
        volume_total_norm = min(metrics.total_options_volume / self.total_volume_max, 1.0)
        
        # Weighted sum
        score = (
            self.weights[ActivityDriver.OI_CHANGE] * oi_change_norm +
            self.weights[ActivityDriver.VOLUME_SPIKE] * volume_norm +
            self.weights[ActivityDriver.IV_INTEREST] * iv_norm +
            self.weights[ActivityDriver.PCR_EXTREME] * pcr_norm +
            self.weights[ActivityDriver.WHALE_ACTIVITY] * whale_norm +
            self.weights[ActivityDriver.TOTAL_VOLUME] * volume_total_norm
        )
        
        return min(score, 1.0)
    
    def identify_primary_driver(self, metrics: ActivityMetrics) -> ActivityDriver:
        """Identify which metric is driving the most activity."""
        contributions = {
            ActivityDriver.OI_CHANGE: abs(metrics.oi_change_pct) / self.oi_change_max,
            ActivityDriver.VOLUME_SPIKE: metrics.volume_spike_score / self.volume_spike_max,
            ActivityDriver.IV_INTEREST: metrics.iv_percentile,
            ActivityDriver.PCR_EXTREME: metrics.pcr_extremeness,
            ActivityDriver.WHALE_ACTIVITY: metrics.whale_activity,
            ActivityDriver.TOTAL_VOLUME: min(metrics.total_options_volume / self.total_volume_max, 1.0)
        }
        return max(contributions, key=contributions.get)
    
    def score_metrics(self, metrics: ActivityMetrics) -> ActivityMetrics:
        """Calculate and populate score in metrics object."""
        metrics.activity_score = self.calculate_score(metrics)
        metrics.primary_driver = self.identify_primary_driver(metrics).value
        return metrics
    
    async def scan_all_assets(self) -> ActivityScanResult:
        """
        Scan all available assets for activity scoring.
        
        Uses lightweight API calls to minimize latency.
        Target: Complete within 30 seconds.
        """
        start_time = datetime.utcnow()
        
        # Get all symbols
        symbols = await self._get_available_symbols()
        
        # Fetch quick metrics for each
        metrics_by_symbol = {}
        for symbol in symbols:
            try:
                quick_data = await self._fetch_quick_metrics(symbol)
                metrics = self._build_metrics(symbol, quick_data)
                metrics = self.score_metrics(metrics)
                metrics_by_symbol[symbol] = metrics
            except Exception as e:
                logger.warning(f"Failed to scan {symbol}: {e}")
        
        # Rank by score
        ranked = sorted(
            metrics_by_symbol.keys(),
            key=lambda s: metrics_by_symbol[s].activity_score,
            reverse=True
        )
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return ActivityScanResult(
            timestamp=start_time,
            total_assets_scanned=len(symbols),
            metrics_by_symbol=metrics_by_symbol,
            ranked_symbols=ranked,
            scan_duration_seconds=duration
        )
    
    async def _fetch_quick_metrics(self, symbol: str) -> dict:
        """Fetch lightweight metrics for a single symbol."""
        # Single API call for ticker + OI summary
        return await self.fetcher.get_activity_summary(symbol)
    
    def _build_metrics(self, symbol: str, data: dict) -> ActivityMetrics:
        """Build ActivityMetrics from API response."""
        return ActivityMetrics(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            oi_change_pct=data.get('oi_change_24h', 0.0),
            volume_spike_score=data.get('volume_vs_avg', 0.0),
            iv_percentile=data.get('iv_percentile', 0.0),
            pcr_extremeness=self._calc_pcr_extreme(data.get('pcr', 1.0)),
            whale_activity=data.get('whale_activity_score', 0.0),
            total_options_volume=data.get('total_volume', 0.0),
            num_strikes_active=data.get('active_strikes', 0)
        )
    
    def _calc_pcr_extreme(self, pcr: float) -> float:
        """Calculate how extreme PCR is (0 = neutral, 1 = very extreme)."""
        # PCR = 1.0 is neutral
        # PCR > 1.5 or < 0.5 is very extreme
        if pcr > 1.0:
            return min((pcr - 1.0) / 0.5, 1.0)
        else:
            return min((1.0 - pcr) / 0.5, 1.0)
```

### 1.2 Asset Selector (`ranking/asset_selector.py`)

```python
# binance_signal_generator/ranking/asset_selector.py

from dataclasses import dataclass
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class RankedAsset:
    """An asset selected for detailed analysis"""
    symbol: str
    rank: int
    activity_score: float
    primary_driver: str
    quick_metrics: dict
    selection_reason: str

class AssetSelector:
    """
    Selects top N assets for detailed analysis.
    
    Purpose:
        From all available assets, select the ones with highest
        activity scores for full signal generation pipeline.
    
    Selection Criteria:
        1. Activity score >= min_threshold
        2. Sufficient liquidity
        3. Has Options data available
        4. Not in exclusion list
    """
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.top_n = config.ranking.top_assets_count          # Default: 5
        self.min_score = config.ranking.min_activity_score    # Default: 0.30
        self.excluded = set(config.ranking.excluded_symbols)  # Symbols to skip
    
    def select(
        self, 
        scan_result: ActivityScanResult
    ) -> List[RankedAsset]:
        """
        Select top assets from scan results.
        
        Returns:
            List of RankedAsset for detailed analysis
        """
        selected = []
        
        for rank, symbol in enumerate(scan_result.ranked_symbols, 1):
            metrics = scan_result.metrics_by_symbol[symbol]
            
            # Check criteria
            if metrics.activity_score < self.min_score:
                logger.debug(f"{symbol} below threshold: {metrics.activity_score:.2f}")
                continue
            
            if symbol in self.excluded:
                logger.debug(f"{symbol} in exclusion list")
                continue
            
            if not self._check_liquidity(metrics):
                logger.debug(f"{symbol} insufficient liquidity")
                continue
            
            # Create ranked asset
            selected.append(RankedAsset(
                symbol=symbol,
                rank=len(selected) + 1,
                activity_score=metrics.activity_score,
                primary_driver=metrics.primary_driver,
                quick_metrics={
                    'oi_change_pct': metrics.oi_change_pct,
                    'volume': metrics.total_options_volume,
                    'iv_percentile': metrics.iv_percentile,
                    'pcr_extremeness': metrics.pcr_extremeness
                },
                selection_reason=f"High {metrics.primary_driver}"
            ))
            
            # Stop at top N
            if len(selected) >= self.top_n:
                break
        
        logger.info(f"Selected {len(selected)} assets from {scan_result.total_assets_scanned} candidates")
        return selected
    
    def _check_liquidity(self, metrics: ActivityMetrics) -> bool:
        """Check if asset has sufficient liquidity."""
        min_volume = self.config.ranking.min_options_volume
        min_strikes = self.config.ranking.min_active_strikes
        
        return (
            metrics.total_options_volume >= min_volume and
            metrics.num_strikes_active >= min_strikes
        )
```

---

## 2. Whale Module (NEW)

### 2.1 Whale Detector (`whale/whale_detector.py`)

```python
# binance_signal_generator/whale/whale_detector.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class WhaleDirection(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

@dataclass
class WhaleTrade:
    """A single whale trade"""
    trade_id: str
    timestamp: datetime
    symbol: str
    option_type: str          # 'CALL' or 'PUT'
    strike: float
    expiry: datetime
    premium: float            # $ value
    contracts: int
    price_per_contract: float
    direction: str            # 'BUY' or 'SELL'
    aggressor: str            # Who initiated
    is_block_trade: bool      # Block trade or regular
    inferred_sentiment: str   # 'BULLISH' or 'BEARISH'

@dataclass
class WhaleAnalysis:
    """Aggregated whale activity analysis"""
    symbol: str
    analysis_timestamp: datetime
    lookback_period: timedelta
    
    # Volume metrics
    whale_buy_volume: float       # Total bullish whale $ volume
    whale_sell_volume: float      # Total bearish whale $ volume
    whale_net_volume: float       # Buy - Sell
    
    # Direction
    whale_net_direction: str      # BULLISH, BEARISH, NEUTRAL
    whale_activity_score: float   # Normalized 0-1
    
    # Trade stats
    large_trades_count: int       # Number of whale trades
    avg_trade_size: float         # Average premium per trade
    max_single_trade: float       # Largest single trade
    
    # Strike analysis
    notable_strikes: List[Dict]   # Strikes with whale activity
    put_heavy_strikes: List[float]  # Strikes with put whale buying
    call_heavy_strikes: List[float] # Strikes with call whale buying
    
    # Signal impact
    confidence_boost: float       # How much to boost signal confidence
    signal_alignment: str         # How whale activity aligns with signal

class WhaleDetector:
    """
    Detects and analyzes whale activity in Options market.
    
    Whale Definition:
        - Regular whale: Trade premium > $100,000
        - Block trade: Trade premium > $500,000
    
    Purpose:
        Identify large player activity that may indicate
        directional bias and potential price moves.
    """
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.whale_threshold = config.whale.min_premium        # $100k
        self.block_threshold = config.whale.block_threshold    # $500k
        self.lookback_hours = config.whale.lookback_hours      # 24h default
    
    def analyze(
        self,
        recent_trades: List[dict],
        options_chain: 'OptionsChain'
    ) -> WhaleAnalysis:
        """
        Analyze recent trades for whale activity.
        
        Args:
            recent_trades: Recent option trades from API
            options_chain: Current options chain for context
        
        Returns:
            WhaleAnalysis with all whale metrics
        """
        # Parse and filter whale trades
        whale_trades = []
        for trade in recent_trades:
            if trade.get('premium', 0) >= self.whale_threshold:
                parsed = self._parse_trade(trade, options_chain)
                whale_trades.append(parsed)
        
        if not whale_trades:
            return self._empty_analysis(options_chain.underlying)
        
        # Aggregate volumes by direction
        buy_volume, sell_volume = 0.0, 0.0
        call_buy_volume, put_buy_volume = 0.0, 0.0
        call_sell_volume, put_sell_volume = 0.0, 0.0
        
        strike_activity = defaultdict(lambda: {'call': 0.0, 'put': 0.0, 'buy': 0.0, 'sell': 0.0})
        
        for trade in whale_trades:
            # Track by overall direction
            if trade.inferred_sentiment == 'BULLISH':
                buy_volume += trade.premium
            else:
                sell_volume += trade.premium
            
            # Track by option type
            if trade.option_type == 'CALL':
                if trade.direction == 'BUY':
                    call_buy_volume += trade.premium
                else:
                    call_sell_volume += trade.premium
            else:  # PUT
                if trade.direction == 'BUY':
                    put_buy_volume += trade.premium
                else:
                    put_sell_volume += trade.premium
            
            # Track by strike
            strike_activity[trade.strike][trade.option_type.lower()] += trade.premium
            strike_activity[trade.strike][trade.direction.lower()] += trade.premium
        
        # Calculate net metrics
        net_volume = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        
        # Determine direction
        direction = self._determine_direction(net_volume)
        
        # Calculate activity score
        activity_score = min(total_volume / 50_000_000, 1.0)  # $50M = max
        
        # Find notable strikes
        notable_strikes = self._find_notable_strikes(strike_activity)
        call_heavy = [s for s, a in strike_activity.items() 
                      if a['call'] > a['put'] * 1.5]
        put_heavy = [s for s, a in strike_activity.items() 
                     if a['put'] > a['call'] * 1.5]
        
        return WhaleAnalysis(
            symbol=options_chain.underlying,
            analysis_timestamp=datetime.utcnow(),
            lookback_period=timedelta(hours=self.lookback_hours),
            
            whale_buy_volume=buy_volume,
            whale_sell_volume=sell_volume,
            whale_net_volume=net_volume,
            
            whale_net_direction=direction,
            whale_activity_score=activity_score,
            
            large_trades_count=len(whale_trades),
            avg_trade_size=total_volume / len(whale_trades),
            max_single_trade=max(t.premium for t in whale_trades),
            
            notable_strikes=notable_strikes,
            put_heavy_strikes=put_heavy,
            call_heavy_strikes=call_heavy,
            
            confidence_boost=self._calc_confidence_boost(net_volume, activity_score),
            signal_alignment=direction
        )
    
    def _parse_trade(self, trade: dict, chain: 'OptionsChain') -> WhaleTrade:
        """Parse raw trade data into WhaleTrade object."""
        option_type = 'CALL' if 'C' in trade.get('symbol', '') else 'PUT'
        
        # Determine if block trade
        is_block = trade.get('premium', 0) >= self.block_threshold
        
        # Infer sentiment from trade
        # Long call or short put = bullish
        # Long put or short call = bearish
        if option_type == 'CALL':
            sentiment = 'BULLISH' if trade.get('side') == 'BUY' else 'BEARISH'
        else:
            sentiment = 'BEARISH' if trade.get('side') == 'BUY' else 'BULLISH'
        
        return WhaleTrade(
            trade_id=trade.get('tradeId', ''),
            timestamp=datetime.fromtimestamp(trade.get('time', 0) / 1000),
            symbol=trade.get('symbol', ''),
            option_type=option_type,
            strike=trade.get('strike', 0.0),
            expiry=datetime.fromtimestamp(trade.get('expiry', 0) / 1000),
            premium=trade.get('premium', 0.0),
            contracts=trade.get('quantity', 0),
            price_per_contract=trade.get('price', 0.0),
            direction=trade.get('side', 'UNKNOWN'),
            aggressor=trade.get('buyerOrderType', 'UNKNOWN'),
            is_block_trade=is_block,
            inferred_sentiment=sentiment
        )
    
    def _determine_direction(self, net_volume: float) -> str:
        """Determine whale net direction."""
        threshold = self.whale_threshold * 2  # $200k net for clear direction
        
        if net_volume > threshold:
            return 'BULLISH'
        elif net_volume < -threshold:
            return 'BEARISH'
        else:
            return 'NEUTRAL'
    
    def _find_notable_strikes(self, strike_activity: dict) -> List[Dict]:
        """Find strikes with significant whale activity."""
        notable = []
        for strike, activity in strike_activity.items():
            total = activity['call'] + activity['put']
            if total >= 1_000_000:  # $1M+ at strike
                notable.append({
                    'strike': strike,
                    'total_volume': total,
                    'call_volume': activity['call'],
                    'put_volume': activity['put'],
                    'net_bias': 'CALL' if activity['call'] > activity['put'] else 'PUT'
                })
        
        return sorted(notable, key=lambda x: x['total_volume'], reverse=True)[:5]
    
    def _calc_confidence_boost(self, net_volume: float, activity_score: float) -> float:
        """
        Calculate how much whale activity should boost signal confidence.
        
        Max boost: 0.15 (15 percentage points)
        """
        # Strong net direction + high activity = max boost
        normalized_net = min(abs(net_volume) / 20_000_000, 1.0)  # $20M net = max
        return 0.15 * normalized_net * activity_score
    
    def _empty_analysis(self, symbol: str) -> WhaleAnalysis:
        """Return empty analysis when no whale activity."""
        return WhaleAnalysis(
            symbol=symbol,
            analysis_timestamp=datetime.utcnow(),
            lookback_period=timedelta(hours=self.lookback_hours),
            whale_buy_volume=0.0,
            whale_sell_volume=0.0,
            whale_net_volume=0.0,
            whale_net_direction='NEUTRAL',
            whale_activity_score=0.0,
            large_trades_count=0,
            avg_trade_size=0.0,
            max_single_trade=0.0,
            notable_strikes=[],
            put_heavy_strikes=[],
            call_heavy_strikes=[],
            confidence_boost=0.0,
            signal_alignment='NEUTRAL'
        )
```

---

## 3. Wall Detector Module (NEW)

### 3.1 Wall Detector (`analysis/wall_detector.py`)

```python
# binance_signal_generator/analysis/wall_detector.py

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class WallType(Enum):
    CALL_WALL = "CALL_WALL"     # Resistance
    PUT_WALL = "PUT_WALL"       # Support
    GAMMA_WALL = "GAMMA_WALL"   # High gamma concentration

@dataclass
class OptionWall:
    """An Options wall (large OI concentration)"""
    strike: float
    wall_type: str              # 'CALL_WALL' or 'PUT_WALL'
    
    # OI metrics
    open_interest: int
    oi_percentage: float        # % of total OI
    oi_change_24h: float        # Change in last 24h
    
    # Volume metrics
    volume: int
    volume_vs_avg: float        # Volume vs 7-day avg
    
    # Position
    distance_from_spot: float   # Distance in %
    side: str                   # 'ABOVE' or 'BELOW' spot
    
    # Strength
    strength_score: float       # 0-1 overall strength
    is_major_wall: bool         # Top OI strike for type
    
    # Whale activity
    whale_volume_at_strike: float
    whale_sentiment: str        # Net whale direction at strike

@dataclass
class WallAnalysis:
    """Complete wall analysis for an asset"""
    symbol: str
    spot_price: float
    timestamp: 'datetime'
    
    # Walls by type
    put_walls: List[OptionWall]       # Support levels
    call_walls: List[OptionWall]      # Resistance levels
    
    # Key walls
    strongest_put_wall: Optional[OptionWall]
    strongest_call_wall: Optional[OptionWall]
    nearest_put_wall: Optional[OptionWall]
    nearest_call_wall: Optional[OptionWall]
    
    # Overall metrics
    total_walls: int
    wall_intensity: float        # How concentrated is OI
    wall_imbalance: float        # Call walls vs Put walls strength
    
    # Trading levels
    support_levels: List[float]   # Sorted put wall strikes
    resistance_levels: List[float]  # Sorted call wall strikes

class WallDetector:
    """
    Detects Options walls for support/resistance identification.
    
    Wall Definition:
        Strike with Open Interest >= 15% of total OI
    
    Purpose:
        Identify key price levels where market has concentrated
        option positions, which often act as support/resistance.
    
    Output:
        2-3 levels of support and resistance for signal generation
    """
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.wall_threshold = config.walls.min_oi_percentage   # 0.15
        self.max_walls = config.walls.max_levels               # 3
        self.major_wall_threshold = config.walls.major_threshold  # 0.25
    
    def detect(
        self,
        options_chain: 'OptionsChain',
        whale_analysis: Optional['WhaleAnalysis'] = None
    ) -> WallAnalysis:
        """
        Detect put and call walls from OI distribution.
        
        Args:
            options_chain: Full options chain data
            whale_analysis: Optional whale data for enrichment
        
        Returns:
            WallAnalysis with all detected walls
        """
        spot = options_chain.spot_price
        
        # Calculate total OI
        total_call_oi = sum(s.call.open_interest for s in options_chain.strikes.values())
        total_put_oi = sum(s.put.open_interest for s in options_chain.strikes.values())
        total_oi = total_call_oi + total_put_oi
        
        # Find walls
        put_walls = []
        call_walls = []
        
        for strike, data in options_chain.strikes.items():
            call_oi = data.call.open_interest
            put_oi = data.put.open_interest
            
            # Check for call wall (resistance - above spot)
            call_pct = call_oi / total_oi
            if call_pct >= self.wall_threshold and strike > spot:
                call_walls.append(self._build_wall(
                    strike=strike,
                    wall_type='CALL_WALL',
                    oi=call_oi,
                    oi_pct=call_pct,
                    volume=data.call.volume,
                    spot=spot,
                    total_oi=total_oi,
                    whale_analysis=whale_analysis
                ))
            
            # Check for put wall (support - below spot)
            put_pct = put_oi / total_oi
            if put_pct >= self.wall_threshold and strike < spot:
                put_walls.append(self._build_wall(
                    strike=strike,
                    wall_type='PUT_WALL',
                    oi=put_oi,
                    oi_pct=put_pct,
                    volume=data.put.volume,
                    spot=spot,
                    total_oi=total_oi,
                    whale_analysis=whale_analysis
                ))
        
        # Sort by strength
        put_walls.sort(key=lambda w: w.strength_score, reverse=True)
        call_walls.sort(key=lambda w: w.strength_score, reverse=True)
        
        # Also sort by distance for nearest
        put_by_distance = sorted(put_walls, key=lambda w: abs(w.distance_from_spot))
        call_by_distance = sorted(call_walls, key=lambda w: abs(w.distance_from_spot))
        
        # Limit to max walls
        put_walls = put_walls[:self.max_walls]
        call_walls = call_walls[:self.max_walls]
        
        return WallAnalysis(
            symbol=options_chain.underlying,
            spot_price=spot,
            timestamp=datetime.utcnow(),
            
            put_walls=put_walls,
            call_walls=call_walls,
            
            strongest_put_wall=put_walls[0] if put_walls else None,
            strongest_call_wall=call_walls[0] if call_walls else None,
            nearest_put_wall=put_by_distance[0] if put_by_distance else None,
            nearest_call_wall=call_by_distance[0] if call_by_distance else None,
            
            total_walls=len(put_walls) + len(call_walls),
            wall_intensity=self._calc_intensity(put_walls + call_walls, total_oi),
            wall_imbalance=self._calc_imbalance(put_walls, call_walls),
            
            support_levels=[w.strike for w in sorted(put_walls, key=lambda w: -w.strike)],
            resistance_levels=[w.strike for w in sorted(call_walls, key=lambda w: w.strike)]
        )
    
    def _build_wall(
        self,
        strike: float,
        wall_type: str,
        oi: int,
        oi_pct: float,
        volume: int,
        spot: float,
        total_oi: int,
        whale_analysis: Optional['WhaleAnalysis']
    ) -> OptionWall:
        """Build OptionWall object with all metrics."""
        distance = abs(strike - spot) / spot * 100
        side = 'ABOVE' if strike > spot else 'BELOW'
        
        # Calculate strength
        strength = self._calc_wall_strength(oi_pct, distance, volume)
        
        # Check if major wall
        is_major = oi_pct >= self.major_wall_threshold
        
        # Get whale activity if available
        whale_vol = 0.0
        whale_sentiment = 'NEUTRAL'
        if whale_analysis:
            for notable in whale_analysis.notable_strikes:
                if notable['strike'] == strike:
                    whale_vol = notable['total_volume']
                    whale_sentiment = notable['net_bias']
        
        return OptionWall(
            strike=strike,
            wall_type=wall_type,
            open_interest=oi,
            oi_percentage=oi_pct,
            oi_change_24h=0.0,  # Would need historical data
            volume=volume,
            volume_vs_avg=1.0,  # Would need historical data
            distance_from_spot=distance,
            side=side,
            strength_score=strength,
            is_major_wall=is_major,
            whale_volume_at_strike=whale_vol,
            whale_sentiment=whale_sentiment
        )
    
    def _calc_wall_strength(self, oi_pct: float, distance: float, volume: int) -> float:
        """
        Calculate wall strength score (0-1).
        
        Factors:
        - OI concentration (primary)
        - Proximity to spot (closer = stronger)
        - Volume activity
        """
        # OI concentration factor
        oi_factor = min(oi_pct / 0.30, 1.0)  # 30% = max
        
        # Distance factor (closer = stronger)
        # Within 1% = 1.0, at 10% = 0.0
        distance_factor = max(0, 1 - distance / 10.0)
        
        # Combine with weights
        return oi_factor * 0.7 + distance_factor * 0.3
    
    def _calc_intensity(self, walls: List[OptionWall], total_oi: int) -> float:
        """Calculate overall wall intensity (how concentrated is OI)."""
        if not walls:
            return 0.0
        
        wall_oi = sum(w.open_interest for w in walls)
        return wall_oi / total_oi
    
    def _calc_imbalance(self, put_walls: List[OptionWall], call_walls: List[OptionWall]) -> float:
        """
        Calculate wall imbalance.
        
        Positive = More call walls (resistance stronger)
        Negative = More put walls (support stronger)
        """
        put_strength = sum(w.strength_score for w in put_walls)
        call_strength = sum(w.strength_score for w in call_walls)
        
        total = put_strength + call_strength
        if total == 0:
            return 0.0
        
        return (call_strength - put_strength) / total
```

---

## 4. S/R Levels Module (NEW)

### 4.1 S/R Level Calculator (`output/sr_levels.py`)

```python
# binance_signal_generator/output/sr_levels.py

from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum

class LevelType(Enum):
    PUT_WALL = "PUT_WALL"
    CALL_WALL = "CALL_WALL"
    MAX_PAIN = "MAX_PAIN"
    WHALE_CLUSTER = "WHALE_CLUSTER"

@dataclass
class SRLevel:
    """Single support or resistance level"""
    level: int                  # 1, 2, or 3
    price: float
    type: str                   # Level type
    strength: float             # 0-1
    confidence: float           # How confident we are in this level
    source: str                 # Human-readable description
    wall_data: Optional[Dict]   # Raw wall data if applicable

@dataclass
class SRLevels:
    """Complete support/resistance structure"""
    # Support levels (below current price)
    support: List[SRLevel]
    
    # Resistance levels (above current price)
    resistance: List[SRLevel]
    
    # Risk levels for signal
    stop_loss: Optional[SRLevel]
    take_profit_levels: List[SRLevel]
    
    # Risk metrics
    risk_reward_ratio: float
    stop_distance_pct: float
    avg_tp_distance_pct: float

class SRLevelCalculator:
    """
    Calculates support/resistance levels from detected walls.
    
    Purpose:
        Convert wall analysis into actionable S/R levels
        for signal generation and risk management.
    
    Output:
        2-3 support and resistance levels with:
        - Price
        - Strength/confidence
        - Source (which wall, max pain, etc.)
    """
    
    def __init__(self, config: 'Config'):
        self.config = config
        self.max_levels = 3
    
    def calculate(
        self,
        wall_analysis: 'WallAnalysis',
        max_pain_strike: float,
        spot_price: float,
        direction: 'SignalDirection'
    ) -> SRLevels:
        """
        Calculate S/R levels from walls and max pain.
        
        Args:
            wall_analysis: Detected walls
            max_pain_strike: Max pain strike
            spot_price: Current price
            direction: Signal direction (LONG/SHORT)
        
        Returns:
            SRLevels with support, resistance, SL, and TPs
        """
        # Build support levels (below spot)
        support = self._build_support_levels(
            wall_analysis.put_walls,
            max_pain_strike,
            spot_price
        )
        
        # Build resistance levels (above spot)
        resistance = self._build_resistance_levels(
            wall_analysis.call_walls,
            spot_price
        )
        
        # Determine stop loss
        stop_loss = self._determine_stop_loss(
            support if direction == 'LONG' else resistance,
            direction
        )
        
        # Determine take profits
        take_profits = self._determine_take_profits(
            resistance if direction == 'LONG' else support,
            spot_price
        )
        
        # Calculate risk metrics
        risk_reward = self._calc_risk_reward(spot_price, stop_loss, take_profits)
        stop_dist = self._calc_stop_distance(spot_price, stop_loss)
        avg_tp_dist = self._calc_avg_tp_distance(spot_price, take_profits)
        
        return SRLevels(
            support=support,
            resistance=resistance,
            stop_loss=stop_loss,
            take_profit_levels=take_profits,
            risk_reward_ratio=risk_reward,
            stop_distance_pct=stop_dist,
            avg_tp_distance_pct=avg_tp_dist
        )
    
    def _build_support_levels(
        self,
        put_walls: List['OptionWall'],
        max_pain: float,
        spot: float
    ) -> List[SRLevel]:
        """Build support levels from put walls and max pain."""
        support = []
        
        # Add put walls
        for i, wall in enumerate(sorted(put_walls, key=lambda w: -w.strike)[:self.max_levels], 1):
            support.append(SRLevel(
                level=i,
                price=wall.strike,
                type='PUT_WALL',
                strength=wall.strength_score,
                confidence=wall.strength_score * 0.9,
                source=f"Put Wall @ {wall.strike:.2f} ({wall.oi_percentage:.1%} OI)",
                wall_data={
                    'strike': wall.strike,
                    'oi': wall.open_interest,
                    'oi_pct': wall.oi_percentage,
                    'whale_volume': wall.whale_volume_at_strike
                }
            ))
        
        # Add max pain if below spot and not already included
        if max_pain < spot and max_pain > 0:
            max_pain_dist = (spot - max_pain) / spot * 100
            if max_pain_dist > 0.5:  # Only add if meaningful distance
                support.append(SRLevel(
                    level=len(support) + 1,
                    price=max_pain,
                    type='MAX_PAIN',
                    strength=0.65,
                    confidence=0.60,
                    source=f"Max Pain @ {max_pain:.2f}",
                    wall_data={'strike': max_pain}
                ))
        
        # Sort by proximity to spot (nearest first)
        support.sort(key=lambda s: abs(s.price - spot))
        
        # Re-number levels
        for i, level in enumerate(support, 1):
            level.level = i
        
        return support
    
    def _build_resistance_levels(
        self,
        call_walls: List['OptionWall'],
        spot: float
    ) -> List[SRLevel]:
        """Build resistance levels from call walls."""
        resistance = []
        
        for i, wall in enumerate(sorted(call_walls, key=lambda w: w.strike)[:self.max_levels], 1):
            resistance.append(SRLevel(
                level=i,
                price=wall.strike,
                type='CALL_WALL',
                strength=wall.strength_score,
                confidence=wall.strength_score * 0.9,
                source=f"Call Wall @ {wall.strike:.2f} ({wall.oi_percentage:.1%} OI)",
                wall_data={
                    'strike': wall.strike,
                    'oi': wall.open_interest,
                    'oi_pct': wall.oi_percentage,
                    'whale_volume': wall.whale_volume_at_strike
                }
            ))
        
        return resistance
    
    def _determine_stop_loss(
        self,
        levels: List[SRLevel],
        direction: 'SignalDirection'
    ) -> Optional[SRLevel]:
        """
        Determine which level to use for stop loss.
        
        For LONG: Use nearest support (S1)
        For SHORT: Use nearest resistance (R1)
        """
        if not levels:
            return None
        
        # Use nearest level (first in list)
        return levels[0]
    
    def _determine_take_profits(
        self,
        levels: List[SRLevel],
        spot: float
    ) -> List[SRLevel]:
        """
        Determine take profit levels.
        
        Use up to 3 levels with position split:
        - TP1: 50% of position
        - TP2: 30% of position
        - TP3: 20% of position
        """
        return levels[:3]
    
    def _calc_risk_reward(
        self,
        spot: float,
        stop_loss: Optional[SRLevel],
        take_profits: List[SRLevel]
    ) -> float:
        """Calculate risk/reward ratio."""
        if not stop_loss or not take_profits:
            return 0.0
        
        risk = abs(spot - stop_loss.price)
        if risk == 0:
            return 0.0
        
        # Weighted average TP
        weights = [0.5, 0.3, 0.2]
        reward = sum(
            abs(tp.price - spot) * weights[i]
            for i, tp in enumerate(take_profits)
            if i < len(weights)
        )
        
        return reward / risk
    
    def _calc_stop_distance(self, spot: float, stop_loss: Optional[SRLevel]) -> float:
        """Calculate stop loss distance as % of spot."""
        if not stop_loss:
            return 0.0
        return abs(stop_loss.price - spot) / spot * 100
    
    def _calc_avg_tp_distance(self, spot: float, take_profits: List[SRLevel]) -> float:
        """Calculate average take profit distance as % of spot."""
        if not take_profits:
            return 0.0
        
        weights = [0.5, 0.3, 0.2]
        total_weight = sum(weights[:len(take_profits)])
        
        return sum(
            abs(tp.price - spot) / spot * 100 * weights[i]
            for i, tp in enumerate(take_profits)
            if i < len(weights)
        ) / total_weight
```

---

## 5. Signal Generator (Updated)

### 5.1 Signal Generator (`output/signal_generator.py`)

```python
# binance_signal_generator/output/signal_generator.py

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict
import json

@dataclass
class EntryZone:
    min_price: float
    max_price: float
    ideal_price: float

@dataclass
class TakeProfitLevel:
    level: int
    price: float
    ratio: float             # Position ratio to close
    wall_type: str           # Which wall this TP is based on
    wall_strike: float

@dataclass
class TradingSignal:
    # Identity
    signal_id: str
    timestamp: datetime
    symbol: str
    asset_rank: int
    activity_score: float
    
    # Direction
    direction: str
    confidence_score: float
    signal_strength: str      # STRONG, MODERATE, WEAK
    
    # Entry
    entry_zone: EntryZone
    
    # Risk Management
    stop_loss: float
    stop_loss_type: str       # WALL_BASED
    stop_loss_wall: Dict      # Which wall SL is based on
    
    # Take Profits
    take_profit_levels: List[TakeProfitLevel]
    
    # Support/Resistance
    support_levels: List[Dict]
    resistance_levels: List[Dict]
    
    # Whale Metrics
    whale_metrics: Dict
    
    # Options Metrics
    options_metrics: Dict
    
    # Futures Metrics
    futures_metrics: Dict

class SignalGenerator:
    """
    Generates final trading signals with all components.
    
    Output includes:
    - Entry zone
    - Stop loss from nearest wall
    - Multiple take profits from resistance/support walls
    - Support/resistance levels (2-3 each)
    - Whale activity metrics
    """
    
    def generate(
        self,
        asset: 'RankedAsset',
        options_signal: 'OptionsSignal',
        whale_analysis: 'WhaleAnalysis',
        wall_analysis: 'WallAnalysis',
        sr_levels: 'SRLevels',
        futures_data: 'FuturesData',
        validation: 'ValidationResult'
    ) -> Optional[TradingSignal]:
        """
        Generate complete trading signal.
        """
        if not sr_levels.stop_loss:
            logger.warning(f"No stop loss level for {asset.symbol}")
            return None
        
        # Entry zone
        entry = self._calc_entry_zone(
            futures_data.price,
            options_signal.direction,
            sr_levels
        )
        
        # Take profits
        take_profits = self._build_take_profits(sr_levels)
        
        # Calculate final confidence with whale boost
        final_confidence = min(
            options_signal.confidence + whale_analysis.confidence_boost,
            1.0
        )
        
        # Determine strength
        strength = self._determine_strength(final_confidence)
        
        return TradingSignal(
            signal_id=self._generate_id(asset.symbol, options_signal.direction),
            timestamp=datetime.utcnow(),
            symbol=asset.symbol,
            asset_rank=asset.rank,
            activity_score=asset.activity_score,
            
            direction=options_signal.direction.value,
            confidence_score=final_confidence,
            signal_strength=strength,
            
            entry_zone=entry,
            
            stop_loss=sr_levels.stop_loss.price,
            stop_loss_type='WALL_BASED',
            stop_loss_wall=sr_levels.stop_loss.wall_data or {},
            
            take_profit_levels=take_profits,
            
            support_levels=[self._sr_to_dict(s) for s in sr_levels.support],
            resistance_levels=[self._sr_to_dict(r) for r in sr_levels.resistance],
            
            whale_metrics={
                'whale_buy_volume': whale_analysis.whale_buy_volume,
                'whale_sell_volume': whale_analysis.whale_sell_volume,
                'whale_net_volume': whale_analysis.whale_net_volume,
                'whale_net_direction': whale_analysis.whale_net_direction,
                'whale_activity_score': whale_analysis.whale_activity_score,
                'large_trades_count': whale_analysis.large_trades_count,
                'avg_trade_size': whale_analysis.avg_trade_size
            },
            
            options_metrics=options_signal.to_dict(),
            
            futures_metrics={
                'price': futures_data.price,
                'volume_24h': futures_data.volume_24h,
                'open_interest': futures_data.open_interest,
                'funding_rate': futures_data.funding_rate,
                'trend': validation.trend.value,
                'volatility_state': validation.volatility_state.value
            }
        )
    
    def _calc_entry_zone(
        self,
        current_price: float,
        direction: str,
        sr_levels: SRLevels
    ) -> EntryZone:
        """Calculate entry zone based on current price and S/R."""
        # For LONG: Entry zone is slightly above support
        # For SHORT: Entry zone is slightly below resistance
        
        if direction == 'LONG':
            # Entry between current and just above nearest support
            support_price = sr_levels.support[0].price if sr_levels.support else current_price * 0.99
            min_entry = max(support_price, current_price * 0.998)
            max_entry = current_price * 1.002
            ideal = (min_entry + max_entry) / 2
        else:
            # Entry between current and just below nearest resistance
            resistance_price = sr_levels.resistance[0].price if sr_levels.resistance else current_price * 1.01
            max_entry = min(resistance_price, current_price * 1.002)
            min_entry = current_price * 0.998
            ideal = (min_entry + max_entry) / 2
        
        return EntryZone(
            min_price=min_entry,
            max_price=max_entry,
            ideal_price=ideal
        )
    
    def _build_take_profits(self, sr_levels: SRLevels) -> List[TakeProfitLevel]:
        """Build take profit levels from S/R."""
        ratios = [0.5, 0.3, 0.2]  # Position split
        
        tps = []
        for i, level in enumerate(sr_levels.take_profit_levels):
            if i >= len(ratios):
                break
            
            tps.append(TakeProfitLevel(
                level=i + 1,
                price=level.price,
                ratio=ratios[i],
                wall_type=level.type,
                wall_strike=level.price
            ))
        
        return tps
    
    def _determine_strength(self, confidence: float) -> str:
        """Determine signal strength label."""
        if confidence >= 0.75:
            return 'STRONG'
        elif confidence >= 0.55:
            return 'MODERATE'
        else:
            return 'WEAK'
    
    def _generate_id(self, symbol: str, direction: str) -> str:
        """Generate unique signal ID."""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
        return f"SIG_{timestamp}_{symbol}_{direction.value}"
    
    def _sr_to_dict(self, level: SRLevel) -> dict:
        """Convert SRLevel to dictionary."""
        return {
            'level': level.level,
            'price': level.price,
            'type': level.type,
            'strength': level.strength,
            'source': level.source
        }
```

---

## Module Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MODULE DEPENDENCY GRAPH                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  cli.py                                                            │
│     │                                                               │
│     └── pipeline/orchestrator.py                                   │
│              │                                                      │
│              ├── ranking/activity_scorer.py                        │
│              │        └── data/options_fetcher.py                  │
│              │                                                      │
│              ├── ranking/asset_selector.py                         │
│              │        └── ranking/activity_scorer.py               │
│              │                                                      │
│              ├── data/options_fetcher.py                           │
│              ├── data/futures_fetcher.py                           │
│              │                                                      │
│              ├── analysis/* (all analyzers)                        │
│              │        └── data/options_fetcher.py                  │
│              │                                                      │
│              ├── analysis/wall_detector.py                         │
│              │        └── whale/whale_detector.py                  │
│              │                                                      │
│              ├── whale/whale_detector.py                           │
│              │        └── data/options_fetcher.py                  │
│              │                                                      │
│              ├── output/sr_levels.py                                │
│              │        └── analysis/wall_detector.py                │
│              │                                                      │
│              ├── output/signal_generator.py                        │
│              │        ├── output/sr_levels.py                       │
│              │        ├── whale/whale_detector.py                  │
│              │        └── ranking/asset_selector.py                │
│              │                                                      │
│              └── output/database.py                                 │
│                                                                      │
│  config/loader.py ──────────► (all modules)                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```
