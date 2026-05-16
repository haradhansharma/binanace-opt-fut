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
│  └──────────────┘  └──────────────┘  └──────────────┘             │
├─────────────────────────────────────────────────────────────────────┤
│                         INFRASTRUCTURE LAYER                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Binance SDK │  │   SQLite     │  │  YAML Config │             │
│  │  (binance-   │  │   Storage    │  │   Loader     │             │
│  │  connector)  │  │              │  │              │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. Single Responsibility
Each module has one reason to change:
- `options_fetcher.py` - Only fetches Options data
- `iv_analyzer.py` - Only calculates implied volatility metrics
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

class NewCustomAnalyzer(BaseAnalyzer):  # Extension
    def analyze(self, data: OptionsData) -> CustomResult: ...
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
│   (binance-connector SDK)                               │                │
│ ┌───────────────┐ │                                    │ ┌────────────┐ │
│ │OptionsFetcher │ │                                    │ │  SignalGen │ │
│ │ (binance.     │ │                                    │ │            │ │
│ │  options)     │ │                                    │ │ - create() │ │
│ │               │ │                                    │ │ - calc_sl()│ │
│ │ - get_chain() │ │                                    │ │ - calc_tp()│ │
│ │ - get_oi()    │ │                                    │ └────────────┘ │
│ │ - get_trades()│ │                                    │                │
│ └───────────────┘ │                                    │ ┌────────────┐ │
│                   │                                    │ │  Database  │ │
│ ┌───────────────┐ │                                    │ │            │ │
│ │FuturesFetcher │ │                                    │ │ - save()   │ │
│ │ (binance.     │ │                                    │ │ - rotate() │ │
│ │  um_futures)  │ │                                    │ │ - query()  │ │
│ │               │ │                                    │ └────────────┘ │
│ │ - get_price() │ │                                    └────────────────┘
│ │ - get_oi()    │ │
│ │ - get_fund()  │ │
│ │ - get_klines()│ │
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
│   │ │ Options API  │ │  ← binance.options SDK                       │
│   │ │ - /eapi/v1/  │ │                                              │
│   │ │   public/... │ │                                              │
│   │ └──────────────┘ │                                              │
│   │ ┌──────────────┐ │                                              │
│   │ │ Futures API  │ │  ← binance.um_futures SDK                    │
│   │ │ - /fapi/v1/  │ │                                              │
│   │ │   ...        │ │                                              │
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

The system uses the **official Binance Connector Python SDK** for reliable API interactions:

```python
# SDK initialization
from binance.options import Options          # For Options API
from binance.um_futures import UMFutures     # For USDT-M Futures

# Options client
options_client = Options(
    key=api_key,
    secret=api_secret,
    base_url='https://eapi.binance.com'      # Production
)

# Futures client  
futures_client = UMFutures(
    key=api_key,
    secret=api_secret,
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

- **GitHub**: https://github.com/binance/binance-connector-python
- **Options Client**: https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_options
- **Futures Client**: https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_coin_futures

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
  # Note: Scheduling handled externally via cronjob
  timeout:
    total_seconds: 600
    fetch_seconds: 120
    analysis_seconds: 180

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
  futures:
    liquidity:
      min_24h_volume: 1000000
    trend:
      ema_period: 20

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
| Data Fetch (Top 5) | 2 minutes | Full Options+Futures data |
| Options Analysis | 3 minutes | IV, PCR, OI, MaxPain, Whale, Walls |
| Signal Output | 1 minute | JSON output, SQLite save |
| **Total** | **~7 minutes** | Single execution |

### Optimization Strategies

1. **Parallel Data Fetching**: Fetch Options and Futures data concurrently
2. **Incremental Analysis**: Cache intermediate results
3. **Lazy Loading**: Load heavy modules only when needed
4. **Connection Pooling**: Reuse HTTP connections
