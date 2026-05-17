# Architecture Design

## System Overview

The Binance Options-Driven Futures Signal Generator follows a **layered architecture** with clear separation of concerns. Each layer has a specific responsibility and communicates through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │    CLI      │  │   Logger    │  │  Database   │                 │
│  │  (Entry)    │  │  (Output)   │  │  (Persist)  │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
├─────────────────────────────────────────────────────────────────────┤
│                         APPLICATION LAYER                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    SIGNAL ORCHESTRATOR                       │   │
│  │    Coordinates: Fetch → Analyze → Validate → Output         │   │
│  └─────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                           DOMAIN LAYER                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   OPTIONS    │  │    FUTURES   │  │    SIGNAL    │             │
│  │   ANALYZER   │  │  VALIDATOR   │  │  GENERATOR   │             │
│  │   + GEX      │  │  + Sentiment │  │              │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
├─────────────────────────────────────────────────────────────────────┤
│                         INFRASTRUCTURE LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Binance SDK │  │   SQLite     │  │  YAML Config │             │
│  │  (official)  │  │   Storage    │  │   Loader     │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. Single Responsibility
Each module has one reason to change:
- `options_fetcher.py` - Only fetches Options data
- `iv_analyzer.py` - Only calculates implied volatility metrics
- `gamma_exposure.py` - Only calculates GEX metrics
- `sentiment.py` - Only analyzes market sentiment
- `signal_generator.py` - Only produces final signals

### 2. Dependency Inversion
High-level modules don't depend on low-level modules. Both depend on abstractions:

```python
# Abstraction
class DataFetcher(Protocol):
    def fetch(self, symbol: str) -> Data: ...

# Implementation
class BinanceOptionsFetcher(DataFetcher):
    def fetch(self, symbol: str) -> OptionsData: ...

# Consumer (depends on abstraction, not implementation)
class OptionsAnalyzer:
    def __init__(self, fetcher: DataFetcher):
        self.fetcher = fetcher
```

### 3. Open/Closed Principle
The system is open for extension but closed for modification:

```python
# Add new analyzer without modifying existing code
class BaseAnalyzer(ABC):
    @abstractmethod
    def analyze(self, data: Data) -> AnalysisResult: ...

class IVAnalyzer(BaseAnalyzer):
    def analyze(self, data: OptionsData) -> IVResult: ...

class GammaExposureAnalyzer(BaseAnalyzer):  # NEW Extension
    def analyze(self, data: OptionsData) -> GEXResult: ...

class SentimentAnalyzer(BaseAnalyzer):  # NEW Extension
    def analyze(self, data: FuturesData) -> SentimentResult: ...
```

## Component Diagram

```
                    ┌─────────────────────────────────┐
                    │         CONFIG LOADER           │
                    │      (config/loader.py)         │
                    │                                 │
                    │  Loads YAML → Validates →      │
                    │  Returns Config Object          │
                    └───────────────┬─────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                        SIGNAL ORCHESTRATOR                        │
│                      (cli.py / orchestrator)                      │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     EXECUTION FLOW                        │   │
│  │                                                           │   │
│  │  1. Load Config ──────────────────────────────────────┐  │   │
│  │  2. Initialize Components ───────────────────────────┐│  │   │
│  │  3. Execute Pipeline:                                 ││  │   │
│  │     ┌──────────┐   ┌──────────┐   ┌──────────┐       ││  │   │
│  │     │  FETCH   │──▶│ ANALYZE  │──▶│ VALIDATE │       ││  │   │
│  │     └──────────┘   └──────────┘   └──────────┘       ││  │   │
│  │           │                              │            ││  │   │
│  │           ▼                              ▼            ││  │   │
│  │     ┌──────────┐                   ┌──────────┐       ││  │   │
│  │     │  CACHE   │                   │  OUTPUT  │       ││  │   │
│  │     └──────────┘                   └──────────┘       ││  │   │
│  │                                                        ││  │   │
│  └────────────────────────────────────────────────────────┘│  │   │
│                                                            │  │   │
└────────────────────────────────────────────────────────────┘  │   │
                                                                │  │
        ┌───────────────────────────────────────────────────────┘  │
        │                                                          │
        ▼                                                          ▼
┌───────────────────┐                                    ┌────────────────┐
│   DATA LAYER      │                                    │  OUTPUT LAYER  │
│   (Binance SDK)   │                                    │                │
│ ┌───────────────┐ │                                    │ ┌────────────┐ │
│ │OptionsFetcher │ │                                    │ │  SignalGen │ │
│ │               │ │                                    │ │            │ │
│ │ - get_chain() │ │                                    │ │ - create() │ │
│ │ - get_oi()    │ │                                    │ │ - calc_sl()│ │
│ │ - get_trades()│ │                                    │ │ - calc_tp()│ │
│ └───────────────┘ │                                    │ └────────────┘ │
│                   │                                    │                │
│ ┌───────────────┐ │                                    │ ┌────────────┐ │
│ │FuturesFetcher │ │                                    │ │  Database  │ │
│ │               │ │                                    │ │            │ │
│ │ - get_price() │ │                                    │ │ - save()   │ │
│ │ - get_oi()    │ │                                    │ │ - rotate() │ │
│ │ - get_fund()  │ │                                    │ │ - query()  │ │
│ │ - get_ls_ratio│ │ ← NEW: Sentiment data              │ └────────────┘ │
│ │ - get_klines()│ │                                    └────────────────┘
│ └───────────────┘ │
└───────────────────┘
```

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW DIAGRAM                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   EXTERNAL                                                          │
│   ┌──────────────────┐                                              │
│   │  Binance API     │                                              │
│   │ ┌──────────────┐ │                                              │
│   │ │ Options API  │ │  ← Options SDK                               │
│   │ │ - /eapi/v1/  │ │                                              │
│   │ │   public/... │ │                                              │
│   │ └──────────────┘ │                                              │
│   │ ┌──────────────┐ │                                              │
│   │ │ Futures API  │ │  ← Futures SDK                               │
│   │ │ - /fapi/v1/  │ │                                              │
│   │ │ - /futures/  │ │  ← Sentiment APIs (L/S Ratios, Funding)      │
│   │ │   data/...   │ │                                              │
│   │ └──────────────┘ │                                              │
│   └────────┬─────────┘                                              │
│            │                                                        │
│            ▼                                                        │
│   ┌────────────────────────────────────────────────────────────┐   │
│   │                    DATA INGESTION                          │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │   │
│   │  │ Rate Limiter│  │   Retry     │  │   Cache     │        │   │
│   │  │   (SDK)     │─▶│   Handler   │─▶│   Layer     │        │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘        │   │
│   └────────────────────────────────────────────────────────────┘   │
│            │                                                        │
│            ▼                                                        │
│   ┌────────────────────────────────────────────────────────────┐   │
│   │                 PROCESSING PIPELINE                        │   │
│   │                                                            │   │
│   │  OPTIONS DATA              FUTURES DATA                   │   │
│   │  ┌─────────────┐           ┌─────────────┐                │   │
│   │  │ IV Analyzer │           │  Liquidity  │                │   │
│   │  │ PCR Analyzer│           │   Checker   │                │   │
│   │  │ OI Analyzer │           │  Trend      │                │   │
│   │  │ MaxPain Calc│           │  Detector   │                │   │
│   │  │ GEX Calc    │← NEW      │Sentiment Anl│← NEW           │   │
│   │  └──────┬──────┘           └──────┬──────┘                │   │
│   │         │                         │                       │   │
│   │         ▼                         ▼                       │   │
│   │  ┌─────────────┐           ┌─────────────┐                │   │
│   │  │   Signal    │◀─────────▶│  Validation │                │   │
│   │  │   Scorer    │           │   Engine    │                │   │
│   │  └──────┬──────┘           └─────────────┘                │   │
│   │         │                                                  │   │
│   └─────────┼──────────────────────────────────────────────────┘   │
│             │                                                        │
│             ▼                                                        │
│   ┌────────────────────────────────────────────────────────────┐   │
│   │                    OUTPUT LAYER                            │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │   │
│   │  │   Signal    │  │   SQLite    │  │    JSON     │        │   │
│   │  │  Generator  │─▶│   Storage   │─▶│   Output    │        │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘        │   │
│   └────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## SDK Integration Architecture

The system uses the **official Binance Python SDK** for reliable API interactions:

```python
# SDK initialization
from binance_sdk_derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
from binance_sdk_derivatives_trading_options import DerivativesTradingOptions

# Options client
options_client = DerivativesTradingOptions(
    api_key=api_key,
    api_secret=api_secret,
    base_url='https://eapi.binance.com'      # Production
)

# Futures client  
futures_client = DerivativesTradingUsdsFutures(
    api_key=api_key,
    api_secret=api_secret,
    base_url='https://fapi.binance.com'      # Production
)
```

### SDK Benefits

| Feature | Benefit |
|---------|---------|
| **Request Signing** | Automatic HMAC signing for authenticated endpoints |
| **Rate Limiting** | Built-in rate limit handling |
| **Error Handling** | Standardized exception classes |
| **Type Hints** | Better IDE support and code completion |
| **Connection Pooling** | Efficient HTTP connection reuse |

### SDK References

- **Options SDK**: https://pypi.org/project/binance-sdk-derivatives-trading-options/
- **Futures SDK**: https://pypi.org/project/binance-sdk-derivatives-trading-usds-futures/

## Error Handling Strategy

```python
# Hierarchical error handling
class SignalGeneratorError(Exception):
    """Base exception for all signal generator errors"""
    pass

class DataFetchError(SignalGeneratorError):
    """Failed to fetch data from Binance"""
    pass

class AnalysisError(SignalGeneratorError):
    """Error during data analysis"""
    pass

class ValidationError(SignalGeneratorError):
    """Signal validation failed"""
    pass

class ConfigurationError(SignalGeneratorError):
    """Invalid configuration"""
    pass
```

### Error Recovery Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  API Call    │────▶│   Success?   │──YES─▶│   Continue   │
└──────────────┘     └──────┬───────┘       └──────────────┘
                            │
                           NO
                            │
                            ▼
                     ┌──────────────┐
                     │ Retry Count  │
                     │    < Max?    │
                     └──────┬───────┘
                       YES  │   NO
                            │    │
                     ┌──────┴──┐ │
                     │  Wait   │ │
                     │+ Retry  │ │
                     └──────┬──┘ │
                            │    │
                            ▼    ▼
                     ┌──────────────┐
                     │    Log       │
                     │   Error      │
                     │ Skip Cycle   │
                     └──────────────┘
```

## Configuration Architecture

```yaml
# config.yaml - Hierarchical structure
binance:
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
  rate_limit:
    requests_per_second: 10
    burst: 20

pipeline:
  timeout:
    total_seconds: 600
    fetch_seconds: 120
    analysis_seconds: 180

# NEW: Intraday configuration
intraday:
  enabled: true
  oi_period: "15m"        # 5m, 15m, 1h, 4h
  volume_interval: "15m"  # 5m, 15m, 1h, 4h
  auto_mode: true         # Auto-select based on volatility

# NEW: Asset-specific whale thresholds
whale:
  asset_thresholds:
    BTCUSDT:
      min_premium: 500000
      block_threshold: 2000000
    ETHUSDT:
      min_premium: 200000
      block_threshold: 1000000
    default:
      min_premium: 100000
      block_threshold: 500000

# NEW: Sentiment analysis settings
sentiment:
  ls_extreme_high: 2.0      # Contrarian signal threshold
  ls_extreme_low: 0.5       # Contrarian signal threshold
  funding_extreme_threshold: 0.001
  use_contrarian: true
  weights:
    position_ratio: 0.4
    account_ratio: 0.3
    funding_rate: 0.3

# NEW: Gamma exposure settings
gamma_exposure:
  enabled: true
  significant_threshold: 0.05
  include_in_sr: true

analysis:
  options:
    iv:
      enabled: true
      lookback_days: 30
      threshold_high: 0.75
      threshold_low: 0.25
    pcr:
      enabled: true
      threshold_put: 1.2
      threshold_call: 0.8
    max_pain:
      enabled: true
      distance_threshold: 2.0  # %

output:
  json:
    enabled: true              # Primary output to stdout
    pretty_print: false
  database:
    enabled: true              # Secondary SQLite storage
    path: ./data/signals.db
    rotation: weekly
    retention_weeks: 4
  signals:
    min_confidence: 0.6
    max_per_execution: 5

logging:
  level: INFO
  file: ./logs/signal_generator.log
  console: false              # JSON output goes to stdout
```

## Performance Considerations

### Execution Budget (Single Run)

| Phase | Time Budget | Operations |
|-------|-------------|------------|
| Activity Scan | 30 seconds | Quick API calls for all assets |
| Asset Selection | 10 seconds | Score and rank |
| Data Fetch (Top 5) | 2 minutes | Full Options+Futures+Sentiment data |
| Options Analysis | 3 minutes | IV, PCR, OI, MaxPain, GEX, Whale, Walls, Sentiment |
| Signal Output | 1 minute | JSON output, SQLite save |
| **Total** | **~7 minutes** | Single execution |

### Optimization Strategies

1. **Parallel Data Fetching**: Fetch Options, Futures, and Sentiment data concurrently
2. **Incremental Analysis**: Cache intermediate results
3. **Lazy Loading**: Load heavy modules only when needed
4. **Connection Pooling**: Reuse HTTP connections

## New Modules Architecture

### Gamma Exposure Module

```python
# binance_signal_generator/analysis/gamma_exposure.py

@dataclass
class GammaExposureResult:
    """Result of gamma exposure analysis"""
    total_gex: float           # Total gamma exposure
    gex_regime: str            # POSITIVE, NEGATIVE, NEUTRAL
    gamma_flip: float          # Price where GEX flips
    support_levels: List[Dict] # Gamma-based support
    resistance_levels: List[Dict]  # Gamma-based resistance
    dealer_hedge_pressure: str  # BUY_DIPS, SELL_RIPS

class GammaExposureCalculator:
    """
    Calculates dealer gamma exposure from options chain.
    
    Formula:
        GEX = Σ (Gamma × OI × 100 × Spot² × 0.01)
    
    Interpretation:
        - Positive GEX: Dealers buy dips, sell rips (stabilizing)
        - Negative GEX: Dealers sell dips, buy rips (accelerating)
    """
    
    def calculate(self, options_chain: OptionsChain) -> GammaExposureResult:
        """Calculate GEX from options chain data."""
        ...
```

### Sentiment Analysis Module

```python
# binance_signal_generator/analysis/sentiment.py

@dataclass
class SentimentResult:
    """Result of sentiment analysis"""
    position_ratio: float      # Top trader L/S position ratio
    account_ratio: float       # Top trader L/S account ratio
    funding_rate: float        # Current funding rate
    funding_rate_avg_7d: float # 7-day average funding
    funding_rate_extreme: bool # Is funding extreme?
    combined_score: float      # Combined sentiment score (0-1)
    signal: str                # LONG, SHORT, NEUTRAL
    is_contrarian: bool        # Contrarian signal detected?

class SentimentAnalyzer:
    """
    Analyzes market sentiment from top trader ratios and funding rates.
    
    Data Sources:
        - Top Trader L/S Position Ratio (FREE API)
        - Top Trader L/S Account Ratio (FREE API)
        - Funding Rate History (Weight: 5)
    
    Signal Generation:
        - Combined sentiment score from weighted inputs
        - Contrarian signals at extreme readings
    """
    
    def analyze(
        self,
        position_ratio: float,
        account_ratio: float,
        funding_rate: float,
        funding_history: List[float]
    ) -> SentimentResult:
        """Calculate combined sentiment score."""
        ...
```

### Asset-Specific Whale Detection

```python
# binance_signal_generator/whale/whale_detector.py

class WhaleDetector:
    """
    Detects whale activity with asset-specific thresholds.
    
    Thresholds by Asset:
        - BTC: $500k min, $2M block
        - ETH: $200k min, $1M block
        - Others: $100k min, $500k block
    """
    
    ASSET_THRESHOLDS = {
        'BTCUSDT': {'min_premium': 500000, 'block_threshold': 2000000},
        'ETHUSDT': {'min_premium': 200000, 'block_threshold': 1000000},
        'DEFAULT': {'min_premium': 100000, 'block_threshold': 500000}
    }
    
    def get_thresholds(self, symbol: str) -> Dict:
        """Get thresholds for specific asset."""
        return self.ASSET_THRESHOLDS.get(
            symbol, 
            self.ASSET_THRESHOLDS['DEFAULT']
        )
```
