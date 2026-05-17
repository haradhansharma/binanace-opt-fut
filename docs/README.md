# Binance Options-Driven Futures Signal Generator

A production-ready Python package that generates **intraday trading signals** for Binance Futures based on comprehensive analysis of Binance Options data.

## Overview

This system operates on a **15-minute scheduled execution** cycle, automatically selecting the **top 5 assets** based on Options activity ranking, then analyzing Options market data to derive actionable insights for Futures trading decisions. It produces trading signals with **multi-level support/resistance (from Options walls and Gamma levels)** and defined risk parameters.

```
┌─────────────────────────────────────────────────────────────────────┐
│                INTRADAY SIGNAL GENERATION FLOW                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   OPTIONS    │    │   ASSET      │    │   WHALE      │          │
│  │  ACTIVITY    │───▶│   RANKING    │───▶│  DETECTION   │          │
│  │   SCAN       │    │  (Top 5)     │    │ (Asset-Spec) │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                   │                   │                   │
│         ▼                   ▼                   ▼                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  IV / PCR /  │    │  Signal      │    │  S/R Levels  │          │
│  │  OI / Walls  │    │  Generation  │    │  (2-3 Level) │          │
│  │  GEX / Sent. │    │              │    │  + Gamma S/R │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│                                                 │                   │
│                                                 ▼                   │
│                                    ┌──────────────────────┐        │
│                                    │   SIGNAL OUTPUT      │        │
│                                    │   • Entry + SL/TP    │        │
│                                    │   • Support (2-3)    │        │
│                                    │   • Resistance (2-3) │        │
│                                    │   • Whale Metrics    │        │
│                                    │   • Gamma Exposure   │        │
│                                    │   • Sentiment Score  │        │
│                                    └──────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Adaptive Asset Selection** | Automatically selects top 5 assets based on Options activity ranking |
| **Intraday Focus** | Signals optimized for intraday trading (15-min execution) with multi-timeframe support |
| **Multi-Level S/R** | 2-3 support and resistance levels from Options walls + Gamma levels |
| **Whale Activity Tracking** | Monitors whale buy/sell volume with asset-specific thresholds |
| **Options Analysis** | IV, PCR, Open Interest, Max Pain, Wall Detection |
| **Gamma Exposure (GEX)** | Dealer gamma positioning, flip levels, hedge pressure analysis |
| **Sentiment Analysis** | Top Trader L/S Ratios + Funding Rate analysis for market sentiment |
| **Smart SL/TP** | Risk levels calculated from wall-based and gamma-based support/resistance |
| **Configuration** | YAML-based, fully parameterizable |
| **Database** | SQLite with auto-rotation (weekly/monthly) |

## New Features (v2.0)

### 1. Asset-Specific Whale Thresholds
Different whale detection thresholds for different assets:
- **BTC**: $500,000 min premium, $2,000,000 block threshold
- **ETH**: $200,000 min premium, $1,000,000 block threshold
- **Others**: $100,000 min premium, $500,000 block threshold

### 2. Gamma Exposure Calculator (GEX)
Dealer positioning analysis including:
- Total Gamma Exposure (GEX) calculation
- Gamma flip level detection
- Support/Resistance from gamma levels
- Dealer hedge pressure indication (BUY_DIPS / SELL_RIPS)

### 3. Multi-Timeframe Intraday Support
Flexible intraday analysis with configurable timeframes:
- **OI Periods**: 5m, 15m, 1h, 4h
- **Volume Intervals**: 5m, 15m, 1h, 4h
- Automatic or manual timeframe selection

### 4. Sentiment Analysis Module
Market sentiment from multiple sources:
- **Top Trader Position Ratio**: Top 20% traders' long/short positioning
- **Top Trader Account Ratio**: Top 20% accounts' positioning
- **Funding Rate Analysis**: 7-day history with extreme detection
- **Combined Sentiment Score**: Weighted combination with contrarian signals

## Quick Start

### Prerequisites

- Python 3.9+ (Python 3.11 recommended)
- Binance API Key and Secret (with Options and Futures permissions)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/binance-options-futures-signal-generator.git
cd binance-options-futures-signal-generator

# Create virtual environment (RECOMMENDED)
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install the package with dependencies
pip install -e .

# Install development dependencies (optional)
pip install -e ".[dev]"
```

### Dependencies

This project uses the **official Binance SDK** for API interactions:

| Package | Purpose | Documentation |
|---------|---------|---------------|
| `binance-sdk-derivatives-trading-usds-futures` | USDT-M Futures SDK | [PyPI](https://pypi.org/project/binance-sdk-derivatives-trading-usds-futures/) |
| `binance-sdk-derivatives-trading-options` | Binance Options SDK | [PyPI](https://pypi.org/project/binance-sdk-derivatives-trading-options/) |

### Configuration

```bash
# Copy example config
cp config.example.yaml config.yaml

# Edit with your API credentials
nano config.yaml
```

### Run Signal Generation

```bash
# Execute signal generation
python -m binance_signal_generator

# With custom config
python -m binance_signal_generator --config /path/to/config.yaml

# Verbose mode for debugging
python -m binance_signal_generator --config config.yaml --dry-run -vv

# Output: JSON to stdout + SQLite database
```

> **Note**: Scheduling (cronjob) and notifications (Telegram) are handled externally. This system only generates and outputs signals.

## Project Structure

```
binance-options-futures-signal-generator/
├── src/
│   └── binance_signal_generator/
│       ├── __init__.py
│       ├── cli.py
│       ├── config/
│       │   ├── loader.py
│       │   └── validators.py
│       ├── data/
│       │   ├── options_fetcher.py
│       │   ├── futures_fetcher.py    # Includes sentiment & funding APIs
│       │   └── cache.py
│       ├── ranking/
│       │   ├── __init__.py
│       │   ├── activity_scorer.py    # Score assets by Options activity
│       │   └── asset_selector.py     # Select top N assets
│       ├── analysis/
│       │   ├── iv_analyzer.py
│       │   ├── pcr_analyzer.py
│       │   ├── oi_analyzer.py
│       │   ├── wall_detector.py      # Detect Options walls
│       │   ├── max_pain.py
│       │   ├── gamma_exposure.py     # NEW: GEX calculator
│       │   ├── sentiment.py          # NEW: L/S ratios + funding
│       │   └── signal_scorer.py
│       ├── whale/
│       │   ├── __init__.py
│       │   ├── whale_detector.py     # Asset-specific thresholds
│       │   └── volume_analyzer.py
│       ├── validation/
│       │   └── futures_validator.py
│       ├── output/
│       │   ├── signal_generator.py
│       │   ├── sr_levels.py          # S/R + Gamma levels
│       │   └── database.py
│       └── utils/
├── config/
│   └── config.example.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PIPELINE.md
│   ├── MODULES.md
│   ├── CONFIGURATION.md
│   └── DEVELOPMENT.md
├── tests/
├── pyproject.toml
└── README.md
```

## Pipeline Execution

```
EXECUTION FLOW (Single Run)
─────────────────────────────────────────────────────────────────────

┌─────────────────┐
│ 1. OPTIONS      │  (~30 sec)
│    ACTIVITY SCAN│  Scan all assets for activity scoring
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. ASSET        │  (~10 sec)
│    RANKING      │  Rank assets, select Top 5
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. DATA FETCH   │  (~2 min)
│    Top 5 Assets │  Full Options+Futures+Sentiment data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. ANALYSIS     │  (~3 min)
│    + GEX        │  IV→PCR→OI→Walls→GEX→Whale→Sentiment
│    + Sentiment  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. SIGNAL       │  (~1 min)
│    OUTPUT       │  JSON Output + SQLite Save
└─────────────────┘

TOTAL: ~7 minutes per execution
```

> **Scheduling**: Handled externally via cronjob or task scheduler

## Asset Selection (Adaptive Ranking)

The system dynamically selects assets based on Options activity scoring:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ASSET RANKING ALGORITHM                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Activity Score = Σ (                                               │
│    w1 × OI_Change_%           # Open Interest momentum             │
│    + w2 × Volume_Spike        # Unusual volume activity            │
│    + w3 × IV_Percentile       # Volatility interest                │
│    + w4 × PCR_Extremes        # Sentiment extremes                 │
│    + w5 × Whale_Activity      # Large player involvement           │
│  )                                                                  │
│                                                                     │
│  Rankings updated each cycle → Top 5 selected for analysis         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Output Format

### Complete Signal Structure

```json
{
  "signal_id": "SIG_20260517_053622_BTCUSDT",
  "timestamp": "2026-05-17T05:36:22.710409Z",
  "symbol": "BTCUSDT",
  "asset_rank": 1,
  "activity_score": 0.283,
  "direction": "LONG",
  "confidence_score": 0.405,
  "signal_strength": "WEAK",
  "entry_zone": {"min": 77739.549, "max": 78520.851, "ideal": 78130.2},
  "stop_loss": {"price": 75000.0, "type": "WALL_BASED", "distance_pct": 4.01},
  "take_profit_levels": [
    {"level": 1, "price": 79302.153, "ratio": 1.5, "distance_pct": 1.5},
    {"level": 2, "price": 80474.106, "ratio": 3.0, "distance_pct": 3.0},
    {"level": 3, "price": 82036.71, "ratio": 5.0, "distance_pct": 5.0}
  ],
  "support_levels": [
    {"level": 1, "price": 75000.0, "oi": 111, "distance_pct": 4.05}
  ],
  "resistance_levels": [
    {"level": 1, "price": 94000.0, "gex": -5202517096.1, "strength": 0.67, "type": "GAMMA_RESISTANCE"}
  ],
  "whale_metrics": {
    "whale_buy_volume": 3785.55,
    "whale_sell_volume": 4326.35,
    "whale_net_volume": -540.80,
    "whale_direction": "NEUTRAL",
    "whale_activity_score": 0.504,
    "large_trades_count": 60
  },
  "options_metrics": {
    "pcr_combined": 1.6462,
    "iv_percentile": 0.35,
    "max_pain_distance": -21.8302,
    "wall_intensity": 0.0155,
    "gex_regime": "POSITIVE",
    "dealer_hedge_pressure": "BUY_DIPS",
    "gamma_flip": 70352.79,
    "total_gex": 77936192248.75,
    "gamma_risk_score": 1.0,
    "top_trader_position_ratio": 1.0,
    "top_trader_account_ratio": 1.21,
    "current_funding_rate": 0.0,
    "funding_rate_avg_7d": 0.0,
    "funding_rate_extreme": false,
    "sentiment_score": 0.052,
    "combined_sentiment": "NEUTRAL",
    "is_contrarian_signal": false
  },
  "futures_metrics": {
    "price": 78130.2,
    "volume_24h": 92944.894,
    "open_interest": 102430.047,
    "funding_rate": 0.0
  },
  "risk_reward_ratio": 0.79
}
```

## Gamma Exposure (GEX) Analysis

```
┌─────────────────────────────────────────────────────────────────────┐
│                  GAMMA EXPOSURE ANALYSIS                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GEX CALCULATION:                                                  │
│  ─────────────────                                                 │
│  GEX = Σ (Gamma × OI × 100 × Spot² × 0.01)                        │
│                                                                     │
│  INTERPRETATION:                                                   │
│  ───────────────                                                   │
│  Positive GEX (>0):                                               │
│    • Dealers BUY dips, SELL rips                                  │
│    • Price tends to stabilize                                     │
│    • Lower volatility expected                                    │
│                                                                     │
│  Negative GEX (<0):                                               │
│    • Dealers SELL dips, BUY rips                                  │
│    • Price tends to accelerate                                    │
│    • Higher volatility expected                                   │
│                                                                     │
│  GAMMA FLIP LEVEL:                                                │
│  ──────────────────                                                │
│  Price where GEX transitions from positive to negative            │
│  Acts as key support/resistance level                             │
│                                                                     │
│  SIGNAL INTEGRATION:                                               │
│  ───────────────────                                               │
│  • GEX regime influences confidence                               │
│  • Gamma flip added to S/R levels                                 │
│  • Dealer hedge pressure guides entry timing                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Sentiment Analysis

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SENTIMENT ANALYSIS MODULE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  DATA SOURCES:                                                     │
│  ──────────────                                                    │
│  1. Top Trader Long/Short Position Ratio (Weight: 0 FREE)          │
│     • Top 20% traders by margin balance                           │
│     • Ratio > 1.0 = Long bias, < 1.0 = Short bias                 │
│                                                                     │
│  2. Top Trader Long/Short Account Ratio (Weight: 0 FREE)           │
│     • Top 20% accounts positioning                                │
│     • More sensitive to crowd sentiment                           │
│                                                                     │
│  3. Funding Rate History (Weight: 5 per request)                   │
│     • 7-day funding rate history                                  │
│     • Extreme funding = contrarian signals                        │
│                                                                     │
│  SIGNAL GENERATION:                                                │
│  ─────────────────                                                 │
│  • Combined sentiment score (0-1)                                 │
│  • Contrarian signal detection                                    │
│  • Funding rate extreme alerts                                    │
│                                                                     │
│  EXAMPLE OUTPUT:                                                   │
│  ───────────────                                                   │
│  ETHUSDT:                                                          │
│    • Position Ratio: 1.36 (long bias)                             │
│    • Account Ratio: 3.01 (strong long bias)                       │
│    • Funding Rate: 0.0072% (normal)                               │
│    • Combined Sentiment: BULLISH (0.37)                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Whale Activity Detection

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WHALE ACTIVITY METRICS                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ASSET-SPECIFIC THRESHOLDS:                                       │
│  ─────────────────────────                                         │
│  Asset      Min Premium    Block Threshold                        │
│  ────      ────────────    ───────────────                        │
│  BTC       $500,000        $2,000,000                             │
│  ETH       $200,000        $1,000,000                             │
│  Others    $100,000        $500,000                               │
│                                                                     │
│  Detection Methods:                                                │
│  ─────────────────                                                 │
│  1. Options Block Trades     → Large premium transactions         │
│  2. Unusual OI Changes       → Sudden position builds/unwinds     │
│  3. Volume Spikes            → Abnormal trading activity          │
│                                                                     │
│  Metrics Calculated:                                               │
│  ──────────────────                                                │
│  • whale_buy_volume    : Total $ of whale bullish trades          │
│  • whale_sell_volume   : Total $ of whale bearish trades          │
│  • whale_net_volume    : buy_volume - sell_volume                 │
│  • whale_net_direction : BULLISH / BEARISH / NEUTRAL              │
│  • whale_activity_score: Normalized score (0-1)                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and design decisions |
| [PIPELINE.md](docs/PIPELINE.md) | Data pipeline with all analysis modules |
| [MODULES.md](docs/MODULES.md) | Module specifications including GEX and sentiment |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Configuration parameters including intraday settings |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development roadmap with completed features |
| [SIGNAL_GENERATION_FLOW.md](docs/SIGNAL_GENERATION_FLOW.md) | Complete A-Z signal generation process |
| [CLI_COMMANDS.md](docs/CLI_COMMANDS.md) | CLI reference and examples |

---

## Requirements

### System Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | Python 3.11 recommended |
| SQLite3 | Built-in | No installation needed |
| Virtual Environment | Recommended | For dependency isolation |

### API Requirements

- **Binance API Key** - Get from [Binance API Management](https://www.binance.com/en/my/settings/api-management)
- **API Permissions**:
  - ✅ Enable Reading
  - ✅ Enable Futures (for Futures data)
  - ✅ Enable Options (for Options data)

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `binance-sdk-derivatives-trading-usds-futures` | Latest | Official Binance Futures SDK |
| `binance-sdk-derivatives-trading-options` | Latest | Official Binance Options SDK |
| `pyyaml` | >=6.0 | Configuration file parsing |
| `aiohttp` | >=3.8.0 | Async HTTP client |
| `pydantic` | >=2.0 | Data validation |

All dependencies are automatically installed via `pip install -e .`

## External Components

| Component | Responsibility | Handled By |
|-----------|---------------|------------|
| Scheduling | Run every 15 minutes | External cronjob / task scheduler |
| Notifications | Send alerts | External Telegram bot / notification system |
| Signal Generation | Analyze & output signals | **This system** |

## API Rate Limits

The system is designed to stay well within Binance rate limits:

| API | Weight | Calls/Cycle | Total Weight |
|-----|--------|-------------|--------------|
| Exchange Info | 1 | 1 | 1 |
| OI History | 0 (FREE) | 6 | 0 |
| Klines | 2 | 6 | 12 |
| Options Tickers | 1 | 2 | 2 |
| Options OI | 1 | 2 | 2 |
| Block Trades | 1 | 2 | 2 |
| Futures Ticker | 1 | 2 | 2 |
| **Top Trader L/S Position** | 0 (FREE) | 2 | 0 |
| **Top Trader L/S Account** | 0 (FREE) | 2 | 0 |
| **Funding Rate History** | 5 | 2 | 10 |
| **Total per cycle** | | ~41 | **~43** |

**Binance Limit: 2400 weight/minute** → System uses ~2% of limit

## Disclaimer

This software is for **informational purposes only**. Trading cryptocurrencies involves substantial risk of loss. The signals generated are not financial advice.
