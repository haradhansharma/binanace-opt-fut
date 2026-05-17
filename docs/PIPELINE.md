# Data Pipeline

## Pipeline Overview

The signal generation pipeline executes in **6 stages** with adaptive asset selection, sentiment analysis, gamma exposure calculation, and whale activity detection.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     COMPLETE PIPELINE FLOW                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STAGE 1       STAGE 2       STAGE 3       STAGE 4                 │
│  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐             │
│  │OPTIONS │    │ ASSET  │    │  DATA  │    │OPTIONS │             │
│  │ACTIVITY│───▶│RANKING │───▶│ FETCH  │───▶│ANALYSIS│             │
│  │  SCAN  │    │TOP 5   │    │+SENTI- │    │+ GEX   │             │
│  │        │    │        │    │MENT    │    │        │             │
│  └────────┘    └────────┘    └────────┘    └────────┘             │
│    30 sec        10 sec        2 min         2 min                 │
│                                                                     │
│  STAGE 5                    STAGE 6                                │
│  ┌────────────────┐         ┌────────────────┐                     │
│  │  WHALE + WALL  │────────▶│ SIGNAL OUTPUT  │                     │
│  │  + SENTIMENT   │         │  + S/R LEVELS  │                     │
│  │  + GEX         │         │  + GAMMA S/R   │                     │
│  └────────────────┘         └────────────────┘                     │
│       1 min                       1 min                            │
│                                                                     │
│  TOTAL: ~7 minutes per 15-min cycle                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: Options Activity Scan

### Purpose
Quick scan of all available assets to rank by Options market activity. This enables **adaptive asset selection** - the system automatically focuses on the most active assets.

### Activity Score Components

```python
# binance_signal_generator/ranking/activity_scorer.py

@dataclass
class ActivityMetrics:
    """Activity metrics for a single asset"""
    symbol: str
    oi_change_pct: float          # Open Interest change %
    volume_spike_score: float     # Volume vs average
    iv_percentile: float          # Current IV percentile
    pcr_extremeness: float        # How extreme is PCR
    whale_activity: float         # Whale activity indicator
    total_options_volume: float   # Total options volume ($)
    num_strikes_active: int       # Strikes with significant OI

class ActivityScorer:
    """
    Scores assets by Options activity level.
    Used to prioritize which assets to analyze in detail.
    """
    
    WEIGHTS = {
        'oi_change': 0.25,
        'volume_spike': 0.20,
        'iv_percentile': 0.15,
        'pcr_extreme': 0.15,
        'whale_activity': 0.15,
        'total_volume': 0.10
    }
    
    def calculate_activity_score(self, metrics: ActivityMetrics) -> float:
        """
        Calculate normalized activity score (0-1).
        
        Higher score = More interesting activity = Higher priority
        """
        score = (
            self.WEIGHTS['oi_change'] * self._normalize_oi_change(metrics.oi_change_pct) +
            self.WEIGHTS['volume_spike'] * metrics.volume_spike_score +
            self.WEIGHTS['iv_percentile'] * metrics.iv_percentile +
            self.WEIGHTS['pcr_extreme'] * metrics.pcr_extremeness +
            self.WEIGHTS['whale_activity'] * metrics.whale_activity +
            self.WEIGHTS['total_volume'] * self._normalize_volume(metrics.total_options_volume)
        )
        return min(score, 1.0)
```

### Multi-Timeframe Support (NEW)

```python
# Intraday timeframe configuration
INTRADAY_CONFIG = {
    'oi_periods': ['5m', '15m', '1h', '4h'],
    'volume_intervals': ['5m', '15m', '1h', '4h'],
    'auto_select': True  # Based on volatility
}

# Auto-selection logic
def select_timeframe(atr_pct: float) -> str:
    """Select timeframe based on market volatility."""
    if atr_pct > 3.0:
        return '5m'   # High volatility - faster analysis
    elif atr_pct > 1.5:
        return '15m'  # Medium volatility
    else:
        return '1h'   # Low volatility - longer timeframe
```

---

## Stage 2: Asset Ranking & Selection

### Purpose
Rank all assets by activity score and select the **Top 5** for detailed analysis.

```python
# binance_signal_generator/ranking/asset_selector.py

@dataclass
class RankedAsset:
    symbol: str
    activity_score: float
    rank: int
    primary_driver: str      # What's driving the activity
    quick_metrics: dict      # Summary for logging

class AssetSelector:
    """
    Selects top N assets for detailed analysis.
    """
    
    def __init__(self, config: Config):
        self.top_n = config.ranking.top_assets_count  # Default: 5
        self.min_activity_threshold = config.ranking.min_activity_score
    
    def select_top_assets(
        self, 
        activity_metrics: Dict[str, ActivityMetrics]
    ) -> List[RankedAsset]:
        """
        Rank and select top assets.
        
        Returns:
            List of RankedAsset for top N assets
        """
        # Calculate scores
        scored = []
        for symbol, metrics in activity_metrics.items():
            score = self.scorer.calculate_activity_score(metrics)
            if score >= self.min_activity_threshold:
                scored.append((symbol, score, metrics))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Select top N
        selected = []
        for rank, (symbol, score, metrics) in enumerate(scored[:self.top_n], 1):
            selected.append(RankedAsset(
                symbol=symbol,
                activity_score=score,
                rank=rank,
                primary_driver=self._identify_driver(metrics),
                quick_metrics={
                    'oi_change': metrics.oi_change_pct,
                    'volume': metrics.total_options_volume,
                    'iv_pct': metrics.iv_percentile
                }
            ))
        
        return selected
```

### Selection Output

```
┌─────────────────────────────────────────────────────────────────────┐
│               ASSET SELECTION OUTPUT (Example)                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Ranked Assets for This Cycle:                                     │
│                                                                     │
│  Rank │ Symbol   │ Score │ Primary Driver      │ Quick Metrics    │
│  ─────┼──────────┼───────┼─────────────────────┼──────────────────│
│   1   │ BTCUSDT  │ 0.28  │ TOTAL_VOLUME        │ OI:+1.5%, Vol:10M│
│   2   │ ETHUSDT  │ 0.22  │ PCR_EXTREME         │ OI:+1.6%, Vol:3.3M│
│                                                                     │
│  Total candidates: 6 → Selected: 2 (after liquidity filter)        │
│  Selection threshold: 0.15                                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stage 3: Data Fetch (Top 5 Assets)

### Purpose
Fetch complete Options, Futures, and **Sentiment data** for selected assets using the **official Binance SDK**.

```python
async def fetch_selected_assets(
    self, 
    selected: List[RankedAsset]
) -> Dict[str, FullMarketData]:
    """
    Fetch complete data for selected assets in parallel.
    Includes Options, Futures, and Sentiment data.
    """
    async with asyncio.TaskGroup() as tg:
        tasks = {
            asset.symbol: tg.create_task(
                self._fetch_single_asset(asset.symbol)
            )
            for asset in selected
        }
    
    return {
        symbol: task.result() 
        for symbol, task in tasks.items()
    }

async def _fetch_single_asset(self, symbol: str) -> FullMarketData:
    """
    Fetch all data for a single asset using SDK.
    
    NEW: Sentiment data (L/S ratios + Funding rate)
    """
    
    # Parallel fetch
    async with asyncio.TaskGroup() as tg:
        # Options data
        options_task = tg.create_task(
            self.options_fetcher.get_option_chain(symbol)
        )
        # Futures data
        futures_task = tg.create_task(
            self.futures_fetcher.get_all_data(symbol)
        )
        # Sentiment data (NEW)
        sentiment_task = tg.create_task(
            self.futures_fetcher.get_sentiment_data(symbol)
        )
        # Recent trades for whale detection
        trades_task = tg.create_task(
            self.options_fetcher.get_recent_trades(symbol, limit=500)
        )
    
    return FullMarketData(
        symbol=symbol,
        options=options_task.result(),
        futures=futures_task.result(),
        sentiment=sentiment_task.result(),  # NEW
        recent_trades=trades_task.result(),
        timestamp=datetime.utcnow()
    )
```

### SDK API Calls Used

| SDK Module | Method | API Endpoint | Weight | Purpose |
|------------|--------|--------------|--------|---------|
| Options | `option_chain()` | `/eapi/v1/optionChain` | 1 | Full options chain |
| Options | `recent_trades()` | `/eapi/v1/trades` | 1 | Whale detection |
| Options | `open_interest()` | `/eapi/v1/openInterest` | 1 | OI data |
| Futures | `ticker_24hr()` | `/fapi/v1/ticker/24hr` | 1 | Price & volume |
| Futures | `open_interest()` | `/fapi/v1/openInterest` | 1 | Futures OI |
| **Futures** | `top_trader_long_short_ratio_positions()` | `/futures/data/topLongShortPositionRatio` | **0 (FREE)** | Sentiment |
| **Futures** | `top_trader_long_short_ratio_accounts()` | `/futures/data/topLongShortAccountRatio` | **0 (FREE)** | Sentiment |
| **Futures** | `get_funding_rate_history()` | `/fapi/v1/fundingRate` | **5** | Funding history |

---

## Stage 4: Options Analysis + GEX + Sentiment

### Analysis Pipeline (for each asset)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OPTIONS ANALYSIS FLOW                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────┐                                                  │
│   │ OptionsData │                                                  │
│   │ + Sentiment │                                                  │
│   └──────┬──────┘                                                  │
│          │                                                         │
│          ▼                                                         │
│   ┌──────────────────────────────────────────────────────────┐    │
│   │               PARALLEL ANALYZERS                         │    │
│   │                                                          │    │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │    │
│   │  │    IV    │ │   PCR    │ │   OI     │ │ MaxPain  │   │    │
│   │  │ Analyzer │ │ Analyzer │ │ Analyzer │ │  Calc    │   │    │
│   │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘   │    │
│   │       │            │            │            │          │    │
│   │  ┌──────────┐ ┌──────────┐                               │    │
│   │  │   GEX    │ │Sentiment │ ← NEW                         │    │
│   │  │  Calc    │ │ Analyzer │                               │    │
│   │  └────┬─────┘ └────┬─────┘                               │    │
│   │       │            │                                      │    │
│   │       └────────────┴────────────────────────────────────┘   │
│   │                         │                                │    │
│   └─────────────────────────┼────────────────────────────────┘    │
│                             │                                      │
│                             ▼                                      │
│                  ┌──────────────────┐                             │
│                  │  SIGNAL SCORER   │                             │
│                  │  (Weighted Sum)  │                             │
│                  └────────┬─────────┘                             │
│                           │                                        │
│                           ▼                                        │
│                  ┌──────────────────┐                             │
│                  │ OptionsSignal    │                             │
│                  │ - Direction      │                             │
│                  │ - Confidence     │                             │
│                  │ - GEX Metrics    │                             │
│                  │ - Sentiment      │                             │
│                  └──────────────────┘                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Signal Scoring with Weights

```python
class SignalScorer:
    """
    Combines all analyzer outputs into unified signal.
    """
    
    DEFAULT_WEIGHTS = {
        'iv': 0.20,
        'pcr': 0.25,
        'oi': 0.20,
        'max_pain': 0.15,
        'sentiment': 0.20      # NEW: Sentiment weight
    }
    
    def score(
        self, 
        analyses: Dict[str, Analysis],
        sentiment_result: SentimentResult,
        gex_result: GammaExposureResult
    ) -> OptionsSignal:
        """
        Calculate combined signal score.
        """
        directional_score = 0.0
        
        # Standard analyzers
        for name, analysis in analyses.items():
            weight = self.DEFAULT_WEIGHTS.get(name, 0)
            if analysis.signal == SignalDirection.LONG:
                directional_score += weight * analysis.confidence
            elif analysis.signal == SignalDirection.SHORT:
                directional_score -= weight * analysis.confidence
        
        # Add sentiment analysis (NEW)
        sentiment_weight = self.DEFAULT_WEIGHTS['sentiment']
        if sentiment_result.signal == 'LONG':
            directional_score += sentiment_weight * abs(sentiment_result.combined_score)
        elif sentiment_result.signal == 'SHORT':
            directional_score -= sentiment_weight * abs(sentiment_result.combined_score)
        
        # Determine final direction
        if directional_score > 0.30:
            direction = SignalDirection.LONG
        elif directional_score < -0.30:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL
        
        return OptionsSignal(
            direction=direction,
            confidence=min(abs(directional_score), 1.0),
            raw_score=directional_score,
            components=analyses,
            gex_metrics=gex_result,         # NEW
            sentiment_metrics=sentiment_result  # NEW
        )
```

---

## Stage 5: Whale & Wall & Sentiment & GEX Detection

### Purpose
Detect whale activity, identify Options walls, analyze sentiment, and calculate gamma exposure for S/R levels.

### Whale Detection (Asset-Specific Thresholds)

```python
class WhaleDetector:
    """
    Detects whale activity with asset-specific thresholds.
    
    Thresholds:
        BTC: $500k min, $2M block
        ETH: $200k min, $1M block
        Others: $100k min, $500k block
    """
    
    ASSET_THRESHOLDS = {
        'BTCUSDT': {'min_premium': 500000, 'block_threshold': 2000000},
        'ETHUSDT': {'min_premium': 200000, 'block_threshold': 1000000},
        'DEFAULT': {'min_premium': 100000, 'block_threshold': 500000}
    }
```

### Wall Detection Module

```python
class WallDetector:
    """
    Detects Options walls for support/resistance levels.
    
    Wall Definition: Strike with OI > 0.5% of total OI
    """
    
    def detect(self, options_chain: OptionsChain) -> WallAnalysis:
        """
        Detect put and call walls from OI distribution.
        """
        spot = options_chain.spot_price
        total_oi = sum(
            s.call.open_interest + s.put.open_interest 
            for s in options_chain.strikes.values()
        )
        
        put_walls = []
        call_walls = []
        
        for strike, data in options_chain.strikes.items():
            call_oi = data.call.open_interest
            put_oi = data.put.open_interest
            
            # Check for call wall (resistance)
            if call_oi / total_oi >= self.wall_threshold:
                call_walls.append(OptionWall(...))
            
            # Check for put wall (support)
            if put_oi / total_oi >= self.wall_threshold:
                put_walls.append(OptionWall(...))
        
        return WallAnalysis(
            put_walls=put_walls[:self.max_walls],
            call_walls=call_walls[:self.max_walls]
        )
```

### Gamma Exposure Calculator

```python
class GammaExposureCalculator:
    """
    Calculates dealer gamma exposure from options chain.
    
    Formula:
        GEX = Σ (Gamma × OI × 100 × Spot² × 0.01)
    
    Interpretation:
        - Positive GEX: Dealers buy dips, sell rips
        - Negative GEX: Dealers sell dips, buy rips
    """
    
    def calculate(self, options_chain: OptionsChain) -> GammaExposureResult:
        """Calculate GEX from options chain data."""
        total_gex = 0.0
        gex_by_strike = {}
        
        for strike, data in options_chain.strikes.items():
            # Calculate GEX for calls (positive)
            call_gex = data.call.gamma * data.call.open_interest * 100 * spot² * 0.01
            
            # Calculate GEX for puts (negative)
            put_gex = -data.put.gamma * data.put.open_interest * 100 * spot² * 0.01
            
            strike_gex = call_gex + put_gex
            gex_by_strike[strike] = strike_gex
            total_gex += strike_gex
        
        return GammaExposureResult(
            total_gex=total_gex,
            gex_regime="POSITIVE" if total_gex > 0 else "NEGATIVE",
            dealer_hedge_pressure="BUY_DIPS" if total_gex > 0 else "SELL_RIPS",
            gamma_flip=self._find_gamma_flip(gex_by_strike),
            ...
        )
```

### Sentiment Analyzer

```python
class SentimentAnalyzer:
    """
    Analyzes market sentiment from top trader ratios and funding rates.
    
    Data Sources:
        - Top Trader L/S Position Ratio (FREE)
        - Top Trader L/S Account Ratio (FREE)
        - Funding Rate History (Weight: 5)
    """
    
    def analyze(
        self,
        position_ratio: float,
        account_ratio: float,
        funding_rate: float,
        funding_history: List[Dict]
    ) -> SentimentResult:
        """Calculate combined sentiment score."""
        
        # Normalize scores
        position_score = self._normalize_ratio(position_ratio)
        account_score = self._normalize_ratio(account_ratio)
        funding_score = self._normalize_funding(funding_rate)
        
        # Combined weighted score
        combined_score = (
            0.40 * position_score +
            0.30 * account_score +
            0.30 * funding_score
        )
        
        return SentimentResult(
            position_ratio=position_ratio,
            account_ratio=account_ratio,
            combined_score=combined_score,
            ...
        )
```

---

## Stage 6: Signal Output with S/R Levels

### Primary Output: JSON to Stdout

```json
{
  "signal_id": "SIG_20260517_053622_BTCUSDT",
  "timestamp": "2026-05-17T05:36:22.710409Z",
  "symbol": "BTCUSDT",
  "direction": "LONG",
  "confidence_score": 0.405,
  "signal_strength": "WEAK",
  
  "entry_zone": {"min": 77739.549, "max": 78520.851, "ideal": 78130.2},
  
  "stop_loss": {
    "price": 75000.0,
    "type": "WALL_BASED",
    "distance_pct": 4.01
  },
  
  "take_profit_levels": [...],
  
  "support_levels": [
    {"level": 1, "price": 75000.0, "oi": 111, "distance_pct": 4.05}
  ],
  
  "resistance_levels": [
    {"level": 1, "price": 94000.0, "gex": -5202517096.1, "type": "GAMMA_RESISTANCE"}
  ],
  
  "whale_metrics": {
    "whale_buy_volume": 3785.55,
    "whale_sell_volume": 4326.35,
    "whale_net_volume": -540.80,
    "whale_direction": "NEUTRAL",
    "large_trades_count": 60
  },
  
  "options_metrics": {
    "pcr_combined": 1.6462,
    "iv_percentile": 0.35,
    "max_pain_distance": -21.8302,
    "gex_regime": "POSITIVE",
    "dealer_hedge_pressure": "BUY_DIPS",
    "gamma_flip": 70352.79,
    "total_gex": 77936192248.75,
    "top_trader_position_ratio": 1.0,
    "top_trader_account_ratio": 1.21,
    "current_funding_rate": 0.0,
    "sentiment_score": 0.052,
    "combined_sentiment": "NEUTRAL"
  }
}
```

---

## Complete Pipeline Orchestration

```python
class SignalPipeline:
    """
    Main pipeline orchestrator with all 6 stages.
    """
    
    async def execute(self) -> List[TradingSignal]:
        """
        Execute complete pipeline.
        """
        signals = []
        
        try:
            # Stage 1: Activity Scan
            logger.info("Stage 1: Scanning all assets for activity...")
            activity_metrics = await self.activity_scorer.scan_all_assets()
            
            # Stage 2: Asset Selection
            logger.info("Stage 2: Ranking and selecting top assets...")
            selected_assets = self.asset_selector.select_top_assets(activity_metrics)
            
            if not selected_assets:
                logger.info("No assets meet activity threshold")
                return signals
            
            # Stage 3: Data Fetch (including Sentiment)
            logger.info("Stage 3: Fetching detailed data + sentiment...")
            market_data = await self.data_fetcher.fetch_selected_assets(selected_assets)
            
            # Stages 4-6: Process each asset
            for asset in selected_assets:
                data = market_data[asset.symbol]
                
                # Stage 4: Options Analysis + GEX
                options_signal = self.options_engine.analyze(data.options)
                gex_result = self.gamma_exposure.calculate(data.options)
                
                # Stage 5: Whale + Wall + Sentiment
                whale_analysis = self.whale_detector.analyze(data.recent_trades, asset.symbol)
                wall_analysis = self.wall_detector.detect(data.options)
                sentiment_result = self.sentiment_analyzer.analyze(
                    data.sentiment.position_ratio,
                    data.sentiment.account_ratio,
                    data.sentiment.funding_rate,
                    data.sentiment.funding_history
                )
                
                # Stage 5b: Futures Validation
                validation = self.futures_validator.validate(options_signal, data.futures)
                
                if not validation.passed:
                    continue
                
                # Stage 6: Signal Generation with Gamma S/R
                sr_levels = self.sr_calculator.calculate(
                    wall_analysis,
                    gex_result,
                    options_signal.max_pain,
                    data.futures.price,
                    options_signal.direction
                )
                
                signal = self.signal_generator.generate(
                    asset=asset,
                    options_signal=options_signal,
                    whale_analysis=whale_analysis,
                    wall_analysis=wall_analysis,
                    gex_result=gex_result,
                    sentiment_result=sentiment_result,
                    sr_levels=sr_levels,
                    futures_data=data.futures
                )
                
                signals.append(signal)
            
            # Output
            self.json_output.write(signals, selected_assets, metadata)
            
            return signals
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise
```

---

## API Call Summary

### Per Pipeline Run (Top 2 Assets Example)

| API Endpoint | Weight | Calls | Total | Purpose |
|--------------|--------|-------|-------|---------|
| `/eapi/v1/exchangeInfo` | 1 | 1 | 1 | Option symbols |
| `/futures/data/openInterestHist` | 0 | 6 | 0 | OI history |
| `/fapi/v1/klines` | 2 | 6 | 12 | Volume history |
| `/eapi/v1/ticker` | 1 | 2 | 2 | Options tickers |
| `/eapi/v1/mark` | 1 | 2 | 2 | Mark prices |
| `/eapi/v1/openInterest` | 1 | 2 | 2 | Options OI |
| `/eapi/v1/blockTrades` | 1 | 2 | 2 | Block trades |
| `/fapi/v1/ticker/24hr` | 1 | 2 | 2 | Futures ticker |
| `/fapi/v1/openInterest` | 1 | 2 | 2 | Futures OI |
| `/futures/data/topLongShortPositionRatio` | 0 | 2 | 0 | L/S position |
| `/futures/data/topLongShortAccountRatio` | 0 | 2 | 0 | L/S account |
| `/fapi/v1/fundingRate` | 5 | 2 | 10 | Funding history |

**Total Weight Per Run: ~35** (well within 2400 limit - uses ~1.5%)
