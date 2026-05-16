# Binance Options-Driven Futures Signal Generator

A production-ready Python package that generates **intraday trading signals** for Binance Futures based on comprehensive analysis of Binance Options data.

## Overview

This system operates on a **15-minute scheduled execution** cycle, automatically selecting the **top 5 assets** based on Options activity ranking, then analyzing Options market data to derive actionable insights for Futures trading decisions. It produces trading signals with **multi-level support/resistance (from Options walls)** and defined risk parameters.

```
┌─────────────────────────────────────────────────────────────────────┐
│                INTRADAY SIGNAL GENERATION FLOW                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   OPTIONS    │    │   ASSET      │    │   WHALE      │          │
│  │  ACTIVITY    │───▶│   RANKING    │───▶│  DETECTION   │          │
│  │   SCAN       │    │  (Top 5)     │    │              │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                   │                   │                   │
│         ▼                   ▼                   ▼                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  IV / PCR /  │    │  Signal      │    │  S/R Levels  │          │
│  │  OI / Walls  │    │  Generation  │    │  (2-3 Level) │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│                                                 │                   │
│                                                 ▼                   │
│                                    ┌──────────────────────┐        │
│                                    │   SIGNAL OUTPUT      │        │
│                                    │   • Entry + SL/TP    │        │
│                                    │   • Support (2-3)    │        │
│                                    │   • Resistance (2-3) │        │
│                                    │   • Whale Metrics    │        │
│                                    └──────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Adaptive Asset Selection** | Automatically selects top 5 assets based on Options activity ranking |
| **Intraday Focus** | Signals optimized for intraday trading (15-min execution) |
| **Multi-Level S/R** | 2-3 support and resistance levels from Options walls |
| **Whale Activity Tracking** | Monitors whale buy/sell volume and net flow |
| **Options Analysis** | IV, PCR, Open Interest, Max Pain, Wall Detection |
| **Smart SL/TP** | Risk levels calculated from wall-based support/resistance |
| **Configuration** | YAML-based, fully parameterizable |
| **Database** | SQLite with auto-rotation (weekly/monthly) |

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

This project uses the **official Binance Connector Python SDK** for API interactions:

| Package | Purpose | Documentation |
|---------|---------|---------------|
| `binance-connector` | Official Binance API SDK | [GitHub](https://github.com/binance/binance-connector-python) |
| `binance.um_futures` | USDT-M Futures (BTCUSDT, ETHUSDT, etc.) | [API Docs](https://binance-docs.github.io/apidocs/futures/en/) |
| `binance.options` | Binance Options API | [API Docs](https://binance-docs.github.io/apidocs/options/en/) |

The `binance-connector` package is automatically installed as a dependency. Key modules used:
- `binance.um_futures` - For USDT-M Futures data (the futures contracts we're trading)
- `binance.options` - For Options chain data (the analysis source)

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
│       │   ├── futures_fetcher.py
│       │   └── cache.py
│       ├── ranking/                    # NEW: Asset ranking system
│       │   ├── __init__.py
│       │   ├── activity_scorer.py      # Score assets by Options activity
│       │   └── asset_selector.py       # Select top N assets
│       ├── analysis/
│       │   ├── iv_analyzer.py
│       │   ├── pcr_analyzer.py
│       │   ├── oi_analyzer.py
│       │   ├── wall_detector.py        # NEW: Detect Options walls
│       │   ├── max_pain.py
│       │   └── signal_scorer.py
│       ├── whale/                      # NEW: Whale activity module
│       │   ├── __init__.py
│       │   ├── whale_detector.py       # Detect whale activity
│       │   └── volume_analyzer.py      # Analyze whale volumes
│       ├── validation/
│       │   └── futures_validator.py
│       ├── output/
│       │   ├── signal_generator.py
│       │   ├── sr_levels.py            # NEW: Support/Resistance calculator
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
│ 1. OPTIONS      │  (~30 sec)                                     │
│    ACTIVITY SCAN│  Scan all assets for activity scoring          │
└────────┬────────┘                                                │
         │                                                         │
         ▼                                                         │
┌─────────────────┐                                                │
│ 2. ASSET        │  (~10 sec)                                     │
│    RANKING      │  Rank assets, select Top 5                     │
└────────┬────────┘                                                │
         │                                                         │
         ▼                                                         │
┌─────────────────┐                                                │
│ 3. DATA FETCH   │  (~2 min)                                      │
│    Top 5 Assets │  Full Options+Futures data                     │
└────────┬────────┘                                                │
         │                                                         │
         ▼                                                         │
┌─────────────────┐                                                │
│ 4. ANALYSIS     │  (~3 min)                                      │
│    + WHALE      │  IV→PCR→OI→Walls→Whale→Score                   │
└────────┬────────┘                                                │
         │                                                         │
         ▼                                                         │
┌─────────────────┐                                                │
│ 5. SIGNAL       │  (~1 min)                                      │
│    OUTPUT       │  JSON Output + SQLite Save                     │
└─────────────────┘                                                │

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
  "signal_id": "SIG_20240115_1430_BTCUSDT_LONG",
  "timestamp": "2024-01-15T14:30:00Z",
  "symbol": "BTCUSDT",
  "asset_rank": 1,
  "activity_score": 0.87,
  
  "direction": "LONG",
  "entry_zone": {
    "min": 42150.00,
    "max": 42200.00,
    "ideal": 42175.00
  },
  
  "stop_loss": 41850.00,
  "stop_loss_type": "WALL_BASED",
  "stop_loss_wall": {
    "type": "PUT_WALL",
    "strike": 41800.00,
    "oi_concentration": 0.23
  },
  
  "take_profit_levels": [
    {"level": 1, "price": 42500.00, "ratio": 0.5, "wall": "CALL_WALL_1"},
    {"level": 2, "price": 42800.00, "ratio": 0.3, "wall": "CALL_WALL_2"},
    {"level": 3, "price": 43200.00, "ratio": 0.2, "wall": "CALL_WALL_3"}
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
  
  "confidence_score": 0.78,
  "signal_strength": "STRONG"
}
```

## Support/Resistance from Walls

The system identifies 2-3 levels of support and resistance from Options walls:

```
┌─────────────────────────────────────────────────────────────────────┐
│            WALL-BASED SUPPORT/RESISTANCE DETECTION                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Current Price: $42,175                                            │
│                                                                     │
│  RESISTANCE (above price):              SUPPORT (below price):    │
│  ──────────────────────────              ───────────────────────── │
│                                                                     │
│  R3: $43,500 ████████████ (Call Wall)   S3: $41,200 (Max Pain)   │
│                    15% OI                          Strong Magnet   │
│                                                                     │
│  R2: $42,800 ████████ (Call Wall)        S2: $41,500 ████ (Put)  │
│                    12% OI                     18% OI               │
│                                                                     │
│  R1: $42,500 █████████████ (Call Wall)   S1: $41,850 ████ (Put)  │
│                    23% OI                     22% OI  ← NEAREST    │
│                                                                     │
│  ───────────────────────────────────────────────────────────────   │
│  ENTRY ZONE: $42,150 - $42,200                                     │
│  STOP LOSS:  $41,850 (S1 - Put Wall below)                         │
│  TP1: $42,500 (R1 - Call Wall above)                               │
│  TP2: $42,800 (R2 - Second Call Wall)                              │
│  TP3: $43,500 (R3 - Third Call Wall)                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Whale Activity Detection

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WHALE ACTIVITY METRICS                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  WHALE DEFINITION: Trades > $100,000 notional value               │
│                                                                     │
│  Detection Methods:                                                │
│  ─────────────────                                                 │
│  1. Options Block Trades     → Large premium transactions         │
│  2. Unusual OI Changes       → Sudden position builds/unwinds     │
│  3. Volume Spikes            → Abnormal trading activity          │
│  4. Sweep Activity           → Aggressive option buying           │
│                                                                     │
│  Metrics Calculated:                                               │
│  ──────────────────                                                │
│  • whale_buy_volume    : Total $ of whale bullish trades          │
│  • whale_sell_volume   : Total $ of whale bearish trades          │
│  • whale_net_volume    : buy_volume - sell_volume                 │
│  • whale_net_direction : BULLISH / BEARISH / NEUTRAL              │
│  • whale_activity_score: Normalized score (0-1)                   │
│                                                                     │
│  Signal Impact:                                                    │
│  ─────────────                                                     │
│  • Net positive + High activity → Boost LONG confidence           │
│  • Net negative + High activity → Boost SHORT confidence          │
│  • Low whale activity            → Rely on other analyzers        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and design decisions |
| [PIPELINE.md](docs/PIPELINE.md) | Data pipeline with asset ranking and whale detection |
| [MODULES.md](docs/MODULES.md) | Module specifications including new modules |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Configuration parameters for adaptive selection |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development roadmap with new features |

---

## Output Format

### Primary Output: JSON to Stdout

The system outputs a **complete JSON signal bundle** to stdout for each execution:

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
      "primary_driver": "WHALE_ACTIVITY"
    },
    {
      "rank": 2,
      "symbol": "ETHUSDT",
      "activity_score": 0.82,
      "primary_driver": "VOLUME_SPIKE"
    },
    {
      "rank": 3,
      "symbol": "SOLUSDT",
      "activity_score": 0.75,
      "primary_driver": "OI_CHANGE"
    },
    {
      "rank": 4,
      "symbol": "BNBUSDT",
      "activity_score": 0.68,
      "primary_driver": "IV_INTEREST"
    },
    {
      "rank": 5,
      "symbol": "ARBUSDT",
      "activity_score": 0.61,
      "primary_driver": "PCR_EXTREME"
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

### Secondary Output: SQLite Database

Signals are also persisted to SQLite for historical analysis:

```
./data/signals.db
├── signals          # All generated signals
├── executions       # Execution history
└── asset_rankings   # Historical asset rankings
```

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
| `binance-connector` | >=3.0.0 | Official Binance API SDK |
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

## Disclaimer

This software is for **informational purposes only**. Trading cryptocurrencies involves substantial risk of loss. The signals generated are not financial advice.
