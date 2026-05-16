# Data Pipeline

## Pipeline Overview

The signal generation pipeline executes in **6 stages** with adaptive asset selection and whale activity detection.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     COMPLETE PIPELINE FLOW                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STAGE 1       STAGE 2       STAGE 3       STAGE 4                 │
│  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐             │
│  │OPTIONS │    │ ASSET  │    │  DATA  │    │OPTIONS │             │
│  │ACTIVITY│───▶│RANKING │───▶│ FETCH  │───▶│ANALYSIS│             │
│  │  SCAN  │    │TOP 5   │    │        │    │        │             │
│  └────────┘    └────────┘    └────────┘    └────────┘             │
│    30 sec        10 sec        2 min         2 min                 │
│                                                                     │
│  STAGE 5                    STAGE 6                                │
│  ┌────────────────┐         ┌────────────────┐                     │
│  │  WHALE + WALL  │────────▶│ SIGNAL OUTPUT  │                     │
│  │  DETECTION     │         │  + S/R LEVELS  │                     │
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
    
    def _normalize_oi_change(self, change_pct: float) -> float:
        """Normalize OI change to 0-1 range."""
        # OI change > 20% is max interest
        return min(abs(change_pct) / 20.0, 1.0)
    
    def _normalize_volume(self, volume: float) -> float:
        """Normalize volume to 0-1 range."""
        # Volume > $100M is max interest
        return min(volume / 100_000_000, 1.0)
```

### Quick Scan Implementation

```python
async def scan_all_assets(self) -> Dict[str, ActivityMetrics]:
    """
    Quick scan of all assets for activity scoring.
    Uses lightweight API calls to minimize latency.
    
    Returns:
        Dict of symbol -> ActivityMetrics
    """
    # Get all available options symbols
    symbols = await self.fetcher.get_available_symbols()
    
    results = {}
    for symbol in symbols:
        # Lightweight data fetch
        ticker = await self.fetcher.get_option_ticker(symbol)
        oi_data = await self.fetcher.get_open_interest_summary(symbol)
        
        # Calculate metrics
        metrics = ActivityMetrics(
            symbol=symbol,
            oi_change_pct=self._calc_oi_change(oi_data),
            volume_spike_score=self._calc_volume_spike(ticker),
            iv_percentile=self._calc_iv_percentile(ticker),
            pcr_extremeness=self._calc_pcr_extreme(ticker),
            whale_activity=0.0,  # Placeholder, detailed later
            total_options_volume=ticker.total_volume,
            num_strikes_active=oi_data.active_strikes
        )
        results[symbol] = metrics
    
    return results
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
        
        Args:
            activity_metrics: Activity metrics from Stage 1
        
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
    
    def _identify_driver(self, metrics: ActivityMetrics) -> str:
        """Identify primary driver of activity."""
        drivers = {
            'OI_CHANGE': abs(metrics.oi_change_pct) / 20.0,
            'VOLUME_SPIKE': metrics.volume_spike_score,
            'IV_INTEREST': metrics.iv_percentile,
            'PCR_EXTREME': metrics.pcr_extremeness,
            'WHALE_ACTIVITY': metrics.whale_activity
        }
        return max(drivers, key=drivers.get)
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
│   1   │ BTCUSDT  │ 0.87  │ WHALE_ACTIVITY      │ OI:+12%, Vol:85M │
│   2   │ ETHUSDT  │ 0.82  │ VOLUME_SPIKE        │ OI:+8%, Vol:62M  │
│   3   │ SOLUSDT  │ 0.75  │ OI_CHANGE           │ OI:+25%, Vol:38M │
│   4   │ BNBUSDT  │ 0.68  │ IV_INTEREST         │ OI:+5%, Vol:25M  │
│   5   │ ARBUSDT  │ 0.61  │ PCR_EXTREME         │ OI:+3%, Vol:18M  │
│                                                                     │
│  Total candidates: 47 → Selected: 5                               │
│  Selection threshold: 0.50                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Stage 3: Data Fetch (Top 5 Assets)

### Purpose
Fetch complete Options and Futures data for selected assets using the **official Binance Connector SDK**.

```python
async def fetch_selected_assets(
    self, 
    selected: List[RankedAsset]
) -> Dict[str, FullMarketData]:
    """
    Fetch complete data for selected assets in parallel.
    Uses binance.options and binance.um_futures SDK modules.
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
    
    SDK Modules:
    - binance.options: Options chain, trades, open interest
    - binance.um_futures: Price, funding rate, klines
    """
    
    # Parallel fetch Options and Futures
    async with asyncio.TaskGroup() as tg:
        # Options data via binance.options SDK
        options_task = tg.create_task(
            self.options_fetcher.get_option_chain(symbol)
        )
        # Futures data via binance.um_futures SDK
        futures_task = tg.create_task(
            self.futures_fetcher.get_all_data(symbol)
        )
        # Recent trades for whale detection
        trades_task = tg.create_task(
            self.options_fetcher.get_recent_trades(symbol, limit=500)
        )
    
    return FullMarketData(
        symbol=symbol,
        options=options_task.result(),
        futures=futures_task.result(),
        recent_trades=trades_task.result(),
        timestamp=datetime.utcnow()
    )
```

### SDK API Calls Used

| SDK Module | Method | API Endpoint | Purpose |
|------------|--------|--------------|---------|
| `binance.options` | `option_chain()` | `GET /eapi/v1/optionChain` | Full options chain |
| `binance.options` | `recent_trades()` | `GET /eapi/v1/trades` | Whale detection |
| `binance.options` | `open_interest()` | `GET /eapi/v1/openInterest` | OI data |
| `binance.um_futures` | `ticker_24hr()` | `GET /fapi/v1/ticker/24hr` | Price & volume |
| `binance.um_futures` | `open_interest()` | `GET /fapi/v1/openInterest` | Futures OI |
| `binance.um_futures` | `funding_rate()` | `GET /fapi/v1/fundingRate` | Funding rate |
| `binance.um_futures` | `mark_price()` | `GET /fapi/v1/premiumIndex` | Mark price |
| `binance.um_futures` | `klines()` | `GET /fapi/v1/klines` | Trend analysis |

---

## Stage 4: Options Analysis

### Analysis Pipeline (for each asset)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OPTIONS ANALYSIS FLOW                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────┐                                                  │
│   │ OptionsData │                                                  │
│   │ + Trades    │                                                  │
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
│   │       └────────────┴────────────┴────────────┘          │    │
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
│                  │ - Score Breakdown│                             │
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
        'whale': 0.20      # NEW: Whale activity weight
    }
    
    def score(
        self, 
        analyses: Dict[str, Analysis],
        whale_analysis: WhaleAnalysis
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
        
        # Add whale analysis
        whale_weight = self.DEFAULT_WEIGHTS['whale']
        if whale_analysis.net_direction == 'BULLISH':
            directional_score += whale_weight * whale_analysis.activity_score
        elif whale_analysis.net_direction == 'BEARISH':
            directional_score -= whale_weight * whale_analysis.activity_score
        
        # Determine final direction
        if directional_score > 0.35:
            direction = SignalDirection.LONG
        elif directional_score < -0.35:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL
        
        return OptionsSignal(
            direction=direction,
            confidence=min(abs(directional_score), 1.0),
            raw_score=directional_score,
            components=analyses
        )
```

---

## Stage 5: Whale & Wall Detection

### Purpose
Detect whale activity and identify Options walls for S/R levels.

### Whale Detection Module

```python
# binance_signal_generator/whale/whale_detector.py

@dataclass
class WhaleTrade:
    """Individual whale trade"""
    timestamp: datetime
    option_type: str        # CALL or PUT
    strike: float
    premium: float          # $ value
    contracts: int
    direction: str          # BUY or SELL
    aggressor: str          # BUYER or SELLER initiated
    is_block: bool          # Block trade or not

@dataclass  
class WhaleAnalysis:
    """Aggregated whale activity analysis"""
    whale_buy_volume: float       # Total bullish whale $ volume
    whale_sell_volume: float      # Total bearish whale $ volume
    whale_net_volume: float       # Buy - Sell
    whale_net_direction: str      # BULLISH, BEARISH, NEUTRAL
    whale_activity_score: float   # Normalized 0-1
    large_trades_count: int       # Number of whale trades
    avg_trade_size: float         # Average trade size
    notable_strikes: List[float]  # Strikes with whale activity
    confidence_boost: float       # How much to boost signal confidence

class WhaleDetector:
    """
    Detects and analyzes whale activity in Options market.
    
    Whale Definition: Trades with premium > $100,000
    """
    
    def __init__(self, config: Config):
        self.whale_threshold = config.whale.min_premium  # $100k default
        self.block_trade_threshold = config.whale.block_threshold  # $500k
    
    def analyze(self, recent_trades: List[Trade], options_chain: OptionsChain) -> WhaleAnalysis:
        """
        Analyze recent trades for whale activity.
        """
        # Filter whale trades
        whale_trades = [
            self._parse_trade(t) 
            for t in recent_trades 
            if t.premium >= self.whale_threshold
        ]
        
        # Aggregate volumes
        buy_volume = sum(t.premium for t in whale_trades 
                        if self._is_bullish(t))
        sell_volume = sum(t.premium for t in whale_trades 
                         if self._is_bearish(t))
        net_volume = buy_volume - sell_volume
        
        # Determine direction
        if net_volume > self.whale_threshold:
            direction = 'BULLISH'
        elif net_volume < -self.whale_threshold:
            direction = 'BEARISH'
        else:
            direction = 'NEUTRAL'
        
        # Calculate activity score
        total_volume = buy_volume + sell_volume
        activity_score = min(total_volume / 50_000_000, 1.0)  # Normalize to $50M
        
        # Find notable strikes
        strike_activity = defaultdict(float)
        for t in whale_trades:
            strike_activity[t.strike] += t.premium
        notable_strikes = sorted(
            strike_activity.keys(), 
            key=lambda s: strike_activity[s], 
            reverse=True
        )[:5]
        
        return WhaleAnalysis(
            whale_buy_volume=buy_volume,
            whale_sell_volume=sell_volume,
            whale_net_volume=net_volume,
            whale_net_direction=direction,
            whale_activity_score=activity_score,
            large_trades_count=len(whale_trades),
            avg_trade_size=total_volume / max(len(whale_trades), 1),
            notable_strikes=notable_strikes,
            confidence_boost=self._calc_confidence_boost(net_volume, activity_score)
        )
    
    def _is_bullish(self, trade: WhaleTrade) -> bool:
        """Determine if trade is bullish."""
        # Long calls or short puts = bullish
        if trade.option_type == 'CALL' and trade.direction == 'BUY':
            return True
        if trade.option_type == 'PUT' and trade.direction == 'SELL':
            return True
        return False
    
    def _is_bearish(self, trade: WhaleTrade) -> bool:
        """Determine if trade is bearish."""
        # Long puts or short calls = bearish
        if trade.option_type == 'PUT' and trade.direction == 'BUY':
            return True
        if trade.option_type == 'CALL' and trade.direction == 'SELL':
            return True
        return False
    
    def _calc_confidence_boost(self, net_volume: float, activity_score: float) -> float:
        """Calculate how much whale activity should boost signal confidence."""
        # Strong whale activity in one direction = +0.15 max boost
        return min(abs(net_volume) / 20_000_000, 0.15) * activity_score
```

### Wall Detection Module

```python
# binance_signal_generator/analysis/wall_detector.py

@dataclass
class OptionWall:
    """An Options wall (large OI concentration)"""
    strike: float
    type: str              # 'CALL_WALL' or 'PUT_WALL'
    oi: int                # Open Interest
    oi_percentage: float   # % of total OI
    distance_pct: float    # Distance from current price %
    strength: float        # 0-1 strength score
    volume: int            # Volume at strike

@dataclass
class WallAnalysis:
    """Complete wall analysis for an asset"""
    put_walls: List[OptionWall]      # Support levels (sorted by distance)
    call_walls: List[OptionWall]     # Resistance levels (sorted by distance)
    strongest_put_wall: OptionWall   # Largest put OI
    strongest_call_wall: OptionWall  # Largest call OI
    wall_intensity: float            # Overall wall intensity (0-1)

class WallDetector:
    """
    Detects Options walls for support/resistance levels.
    
    Wall Definition: Strike with OI > 15% of total OI
    """
    
    def __init__(self, config: Config):
        self.wall_threshold = config.walls.min_oi_percentage  # 0.15 default
        self.max_walls = config.walls.max_levels  # 3 levels
    
    def detect(self, options_chain: OptionsChain) -> WallAnalysis:
        """
        Detect put and call walls from OI distribution.
        """
        spot = options_chain.spot_price
        total_oi = sum(
            s.call.open_interest + s.put.open_interest 
            for s in options_chain.strikes.values()
        )
        
        # Collect all walls
        put_walls = []
        call_walls = []
        
        for strike, data in options_chain.strikes.items():
            call_oi = data.call.open_interest
            put_oi = data.put.open_interest
            
            # Check for call wall (resistance)
            if call_oi / total_oi >= self.wall_threshold:
                call_walls.append(OptionWall(
                    strike=strike,
                    type='CALL_WALL',
                    oi=call_oi,
                    oi_percentage=call_oi / total_oi,
                    distance_pct=(strike - spot) / spot * 100,
                    strength=self._calc_strength(call_oi, total_oi, strike, spot, 'CALL'),
                    volume=data.call.volume
                ))
            
            # Check for put wall (support)
            if put_oi / total_oi >= self.wall_threshold:
                put_walls.append(OptionWall(
                    strike=strike,
                    type='PUT_WALL',
                    oi=put_oi,
                    oi_percentage=put_oi / total_oi,
                    distance_pct=(spot - strike) / spot * 100,
                    strength=self._calc_strength(put_oi, total_oi, strike, spot, 'PUT'),
                    volume=data.put.volume
                ))
        
        # Sort by distance (closest first)
        put_walls.sort(key=lambda w: abs(w.distance_pct))
        call_walls.sort(key=lambda w: abs(w.distance_pct))
        
        # Limit to max walls
        put_walls = put_walls[:self.max_walls]
        call_walls = call_walls[:self.max_walls]
        
        # Find strongest
        strongest_put = max(put_walls, key=lambda w: w.oi) if put_walls else None
        strongest_call = max(call_walls, key=lambda w: w.oi) if call_walls else None
        
        return WallAnalysis(
            put_walls=put_walls,
            call_walls=call_walls,
            strongest_put_wall=strongest_put,
            strongest_call_wall=strongest_call,
            wall_intensity=self._calc_intensity(put_walls + call_walls, total_oi)
        )
    
    def _calc_strength(self, oi: int, total_oi: int, strike: float, spot: float, wall_type: str) -> float:
        """
        Calculate wall strength score (0-1).
        
        Factors:
        - OI concentration
        - Proximity to spot
        - Volume activity
        """
        concentration = oi / total_oi
        
        # Distance factor (closer = stronger)
        distance = abs(strike - spot) / spot
        distance_factor = max(0, 1 - distance * 10)  # Penalize distance
        
        return concentration * 0.7 + distance_factor * 0.3
```

---

## Stage 6: Signal Output with S/R Levels

### Primary Output: JSON to Stdout

The final output is a **complete JSON signal bundle** written to stdout:

```json
{
  "execution_id": "EXEC_20240115_143000",
  "timestamp": "2024-01-15T14:30:00Z",
  "execution_duration_seconds": 420,
  "assets_analyzed": 5,
  "signals_generated": 3,
  
  "selected_assets": [
    {
      "rank": 1,
      "symbol": "BTCUSDT",
      "activity_score": 0.87,
      "primary_driver": "WHALE_ACTIVITY",
      "quick_metrics": {
        "oi_change_pct": 12.5,
        "volume_usd": 85000000,
        "iv_percentile": 0.65
      }
    }
  ],
  
  "signals": [
    {
      "signal_id": "SIG_20240115_1430_BTCUSDT_LONG",
      "timestamp": "2024-01-15T14:30:00Z",
      "symbol": "BTCUSDT",
      "asset_rank": 1,
      "activity_score": 0.87,
      
      "direction": "LONG",
      "confidence_score": 0.78,
      "signal_strength": "STRONG",
      
      "entry_zone": {
        "min": 42150.00,
        "max": 42200.00,
        "ideal": 42175.00
      },
      
      "stop_loss": {
        "price": 41850.00,
        "type": "WALL_BASED",
        "wall": {
          "type": "PUT_WALL",
          "strike": 41800.00,
          "oi_concentration": 0.23
        },
        "distance_pct": 0.78
      },
      
      "take_profit_levels": [
        {"level": 1, "price": 42500.00, "ratio": 0.5, "distance_pct": 0.77, "wall_type": "CALL_WALL"},
        {"level": 2, "price": 42800.00, "ratio": 0.3, "distance_pct": 1.48, "wall_type": "CALL_WALL"},
        {"level": 3, "price": 43200.00, "ratio": 0.2, "distance_pct": 2.43, "wall_type": "CALL_WALL"}
      ],
      
      "support_levels": [
        {"level": 1, "price": 41850.00, "type": "PUT_WALL", "strength": 0.85},
        {"level": 2, "price": 41500.00, "type": "PUT_WALL", "strength": 0.72},
        {"level": 3, "price": 41200.00, "type": "MAX_PAIN", "strength": 0.65}
      ],
      
      "resistance_levels": [
        {"level": 1, "price": 42500.00, "type": "CALL_WALL", "strength": 0.88},
        {"level": 2, "price": 42800.00, "type": "CALL_WALL", "strength": 0.75},
        {"level": 3, "price": 43500.00, "type": "CALL_WALL", "strength": 0.62}
      ],
      
      "whale_metrics": {
        "whale_buy_volume": 12500000.00,
        "whale_sell_volume": 3200000.00,
        "whale_net_volume": 9300000.00,
        "whale_net_direction": "BULLISH",
        "whale_activity_score": 0.78,
        "large_trades_count": 47,
        "avg_trade_size": 265957.45
      },
      
      "options_metrics": {
        "iv_rank": 0.65,
        "pcr": 0.82,
        "max_pain": 42000.00,
        "max_pain_distance_pct": 0.4,
        "put_wall": 41800.00,
        "call_wall": 42500.00,
        "oi_concentration": 0.71
      },
      
      "futures_metrics": {
        "liquidity_score": 0.92,
        "trend_alignment": "BULLISH",
        "volatility_state": "NORMAL",
        "funding_rate": 0.0001
      },
      
      "risk_reward_ratio": 2.1
    }
  ],
  
  "metadata": {
    "config_file": "/path/to/config.yaml",
    "api_calls_made": 42,
    "data_freshness_seconds": 15
  }
}
```

### JSON Output Fields Reference

| Field | Description | Type |
|-------|-------------|------|
| `execution_id` | Unique execution identifier | string |
| `timestamp` | UTC timestamp of execution | string (ISO 8601) |
| `execution_duration_seconds` | Total pipeline duration | number |
| `assets_analyzed` | Number of assets analyzed | number |
| `signals_generated` | Number of signals produced | number |
| `selected_assets` | List of top 5 ranked assets | array |
| `signals` | List of trading signals | array |

#### Signal Object Fields

| Field | Description | Type |
|-------|-------------|------|
| `signal_id` | Unique signal identifier | string |
| `symbol` | Trading pair | string |
| `direction` | LONG or SHORT | string |
| `confidence_score` | Signal confidence (0-1) | number |
| `entry_zone` | Entry price range | object |
| `stop_loss` | SL with wall details | object |
| `take_profit_levels` | Up to 3 TP levels | array |
| `support_levels` | 2-3 support levels | array |
| `resistance_levels` | 2-3 resistance levels | array |
| `whale_metrics` | Whale activity data | object |
| `options_metrics` | Options analysis data | object |
| `futures_metrics` | Futures validation data | object |
| `risk_reward_ratio` | Calculated R:R ratio | number |

### Support/Resistance Level Generator

```python
# binance_signal_generator/output/sr_levels.py

@dataclass
class SRLevel:
    """Single support or resistance level"""
    level: int              # 1, 2, or 3
    price: float
    type: str               # 'PUT_WALL', 'CALL_WALL', 'MAX_PAIN'
    strength: float         # 0-1
    source: str             # Description

@dataclass
class SRLevels:
    """Complete support/resistance structure"""
    support: List[SRLevel]      # S1, S2, S3 (nearest to farthest)
    resistance: List[SRLevel]   # R1, R2, R3 (nearest to farthest)
    stop_loss_level: SRLevel    # Which S/R is used for SL
    tp_levels: List[SRLevel]    # Which S/R used for TPs

class SRLevelCalculator:
    """
    Calculates support/resistance levels from walls.
    Generates 2-3 levels for both support and resistance.
    """
    
    def __init__(self, config: Config):
        self.max_levels = 3
    
    def calculate(
        self,
        wall_analysis: WallAnalysis,
        max_pain: float,
        spot_price: float,
        direction: SignalDirection
    ) -> SRLevels:
        """
        Calculate S/R levels from walls and max pain.
        """
        # Support levels (below spot)
        support = []
        
        # Add put walls as support
        for i, wall in enumerate(wall_analysis.put_walls[:self.max_levels], 1):
            support.append(SRLevel(
                level=i,
                price=wall.strike,
                type='PUT_WALL',
                strength=wall.strength,
                source=f"Put Wall @ {wall.strike} ({wall.oi_percentage:.1%} OI)"
            ))
        
        # Add max pain if below spot and space available
        if max_pain < spot_price and len(support) < self.max_levels:
            support.append(SRLevel(
                level=len(support) + 1,
                price=max_pain,
                type='MAX_PAIN',
                strength=0.65,
                source=f"Max Pain @ {max_pain}"
            ))
        
        # Sort by proximity to spot
        support.sort(key=lambda s: abs(s.price - spot_price))
        
        # Resistance levels (above spot)
        resistance = []
        for i, wall in enumerate(wall_analysis.call_walls[:self.max_levels], 1):
            resistance.append(SRLevel(
                level=i,
                price=wall.strike,
                type='CALL_WALL',
                strength=wall.strength,
                source=f"Call Wall @ {wall.strike} ({wall.oi_percentage:.1%} OI)"
            ))
        
        # Sort by proximity to spot
        resistance.sort(key=lambda r: abs(r.price - spot_price))
        
        # Determine SL level
        if direction == SignalDirection.LONG:
            stop_loss_level = support[0] if support else None
        else:
            stop_loss_level = resistance[0] if resistance else None
        
        # Determine TP levels
        if direction == SignalDirection.LONG:
            tp_levels = resistance[:3]
        else:
            tp_levels = support[:3]
        
        return SRLevels(
            support=support,
            resistance=resistance,
            stop_loss_level=stop_loss_level,
            tp_levels=tp_levels
        )
```

### Final Signal Generation

```python
# binance_signal_generator/output/signal_generator.py

class SignalGenerator:
    """
    Generates final trading signals with all components.
    """
    
    def generate(
        self,
        asset: RankedAsset,
        options_signal: OptionsSignal,
        whale_analysis: WhaleAnalysis,
        wall_analysis: WallAnalysis,
        sr_levels: SRLevels,
        futures_data: FuturesData
    ) -> TradingSignal:
        """
        Generate complete trading signal.
        """
        # Entry zone
        entry = self._calc_entry_zone(
            futures_data.price,
            options_signal.direction,
            sr_levels
        )
        
        # Stop Loss from nearest wall
        stop_loss = self._calc_stop_loss(
            sr_levels.stop_loss_level,
            entry,
            options_signal.direction
        )
        
        # Take Profits from resistance/support walls
        take_profits = self._calc_take_profits(
            sr_levels.tp_levels,
            entry,
            stop_loss
        )
        
        return TradingSignal(
            signal_id=self._generate_id(asset.symbol, options_signal.direction),
            timestamp=datetime.utcnow(),
            symbol=asset.symbol,
            asset_rank=asset.rank,
            activity_score=asset.activity_score,
            
            direction=options_signal.direction,
            entry_zone=entry,
            stop_loss=stop_loss,
            stop_loss_type='WALL_BASED',
            stop_loss_wall=self._wall_to_dict(sr_levels.stop_loss_level),
            
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
            
            options_metrics=options_signal.to_metrics(),
            futures_metrics=self._extract_futures_metrics(futures_data),
            
            confidence_score=options_signal.confidence + whale_analysis.confidence_boost,
            signal_strength=self._determine_strength(options_signal.confidence)
        )
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
            
            logger.info(f"Selected {len(selected_assets)} assets: {[a.symbol for a in selected_assets]}")
            
            # Stage 3: Data Fetch
            logger.info("Stage 3: Fetching detailed data...")
            market_data = await self.data_fetcher.fetch_selected_assets(selected_assets)
            
            # Stages 4-6: Process each asset
            for asset in selected_assets:
                data = market_data[asset.symbol]
                
                # Stage 4: Options Analysis
                options_signal = self.options_engine.analyze(data.options)
                
                if options_signal.confidence < self.config.min_confidence:
                    continue
                
                # Stage 5: Whale & Wall Detection
                whale_analysis = self.whale_detector.analyze(
                    data.recent_trades, 
                    data.options
                )
                wall_analysis = self.wall_detector.detect(data.options)
                
                # Stage 5b: Futures Validation
                validation = self.futures_validator.validate(
                    options_signal, 
                    data.futures
                )
                
                if not validation.passed:
                    continue
                
                # Stage 6: Signal Generation
                sr_levels = self.sr_calculator.calculate(
                    wall_analysis,
                    options_signal.max_pain,
                    data.futures.price,
                    options_signal.direction
                )
                
                signal = self.signal_generator.generate(
                    asset=asset,
                    options_signal=options_signal,
                    whale_analysis=whale_analysis,
                    wall_analysis=wall_analysis,
                    sr_levels=sr_levels,
                    futures_data=data.futures
                )
                
                if signal:
                    self.database.save(signal)
                    signals.append(signal)
                    logger.info(f"Signal generated: {signal.signal_id}")
            
            return signals
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise PipelineError(str(e)) from e
```
