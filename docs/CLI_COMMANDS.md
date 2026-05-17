# CLI Commands Reference

> **Binance Options-Driven Futures Signal Generator**
> Complete CLI Reference Guide

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Basic Usage](#basic-usage)
4. [Command-Line Options](#command-line-options)
5. [Output Formats](#output-formats)
6. [Signal Output Schema](#signal-output-schema)
7. [Configuration](#configuration)
8. [Testing Commands](#testing-commands)
9. [Common Workflows](#common-workflows)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Binance Signal Generator CLI (`binance-signals`) is the primary interface for running the signal generation pipeline. It provides a comprehensive set of options for configuring and executing the pipeline, outputting results in JSON format suitable for downstream processing.

### Key Features

- **Adaptive Asset Selection**: Automatically selects top N assets based on Options activity
- **Manual Symbol Override**: Analyze specific symbols on demand
- **Flexible Output**: JSON to stdout or file, with pretty-printing options
- **Dry-Run Mode**: Test without database persistence
- **Verbose Logging**: Multiple verbosity levels for debugging
- **NEW: Sentiment Analysis**: Top Trader L/S ratios + Funding rate
- **NEW: Gamma Exposure**: GEX calculation with dealer pressure

---

## Installation

```bash
# Remove old packages
pip uninstall binance-connector binance-sdk-derivatives-trading-usds-futures -y 2>/dev/null

# Install with correct dependencies
pip install -e . --force-reinstall

# Test the CLI
python -m binance_signal_generator --version
```

### Verify Installation

```bash
# Check version
python -m binance_signal_generator --version

# Expected output:
# binance-signals 2.0.0
```

---

## Basic Usage

### Run with Default Settings

```bash
# Uses adaptive selection, outputs to stdout
python -m binance_signal_generator --config config.yaml
```

### Quick Start Examples

```bash
# Analyze specific symbols
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT --pretty

# Dry run (no database)
python -m binance_signal_generator --config config.yaml --dry-run

# Save output to file
python -m binance_signal_generator --output signals.json

# Run with verbose logging
python -m binance_signal_generator -vv
```

---

## Command-Line Options

### Core Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--config` | `-c` | PATH | `./config.yaml` | Path to configuration file |
| `--symbols` | | SYMBOL [...] | None | Specific symbols to analyze |
| `--dry-run` | | flag | False | Run without saving to database |
| `--top-n` | | N | 5 | Number of top assets to analyze |
| `--min-confidence` | | SCORE | 0.30 | Minimum signal confidence to output |

### Output Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--output` | `-o` | PATH | stdout | Write output to file |
| `--pretty` | | flag | False | Pretty print JSON |
| `--compact` | | flag | False | Output one signal per line |

### Logging Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--verbose` | `-v` | count | 0 | Increase verbosity (-v, -vv) |
| `--quiet` | `-q` | flag | False | Suppress all output except signals |

---

## Output Formats

### Standard JSON Output

```json
{
  "execution_id": "EXEC_20260517_053558_10642a23",
  "timestamp": "2026-05-17T05:35:58.734777Z",
  "execution_duration_seconds": 29.39,
  "assets_analyzed": 2,
  "signals_generated": 2,
  "signals": [...],
  "selected_assets": [
    {
      "symbol": "BTCUSDT",
      "rank": 1,
      "activity_score": 0.283,
      "primary_driver": "TOTAL_VOLUME"
    }
  ],
  "metadata": {
    "config_file": "config/config.yaml",
    "api_calls_made": 41,
    "data_freshness_seconds": 0.0,
    "errors": []
  }
}
```

---

## Signal Output Schema

Each generated signal contains the following fields:

### Core Signal Fields

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | string | Unique identifier (SIG_YYYYMMDD_HHMMSS_SYMBOL) |
| `timestamp` | string | ISO 8601 timestamp |
| `symbol` | string | Trading pair (e.g., BTCUSDT) |
| `direction` | enum | LONG, SHORT, or NEUTRAL |
| `confidence_score` | float | Signal confidence (0.0-1.0) |
| `signal_strength` | enum | WEAK, MODERATE, STRONG, VERY_STRONG |

### Entry & Risk Management

| Field | Type | Description |
|-------|------|-------------|
| `entry_zone` | object | Entry price range (min, max, ideal) |
| `stop_loss` | object | Stop loss price and type |
| `take_profit_levels` | array | Up to 3 TP levels with ratios |
| `support_levels` | array | Support levels from put walls + gamma |
| `resistance_levels` | array | Resistance levels from call walls + gamma |
| `risk_reward_ratio` | float | Calculated R:R ratio |

### Whale Metrics (Asset-Specific Thresholds)

| Field | Type | Description |
|-------|------|-------------|
| `whale_buy_volume` | float | Total bullish whale $ volume |
| `whale_sell_volume` | float | Total bearish whale $ volume |
| `whale_net_volume` | float | Net whale volume (buy - sell) |
| `whale_direction` | string | BULLISH, BEARISH, NEUTRAL |
| `whale_activity_score` | float | Normalized activity (0-1) |
| `large_trades_count` | int | Number of whale trades |

### Options Metrics (with GEX + Sentiment)

| Field | Type | Description |
|-------|------|-------------|
| `pcr_combined` | float | Combined Put/Call ratio |
| `iv_percentile` | float | IV percentile (0-1) |
| `max_pain_distance` | float | Distance to max pain (%) |
| `wall_intensity` | float | Wall strength indicator |
| `wall_imbalance` | float | Put/Call wall imbalance |
| **`gex_regime`** | string | POSITIVE, NEGATIVE, NEUTRAL |
| **`dealer_hedge_pressure`** | string | BUY_DIPS, SELL_RIPS |
| **`gamma_flip`** | float | Price where GEX flips sign |
| **`total_gex`** | float | Total gamma exposure ($) |
| **`gamma_risk_score`** | float | Normalized risk (0-1) |
| **`top_trader_position_ratio`** | float | Top 20% traders L/S position ratio |
| **`top_trader_account_ratio`** | float | Top 20% accounts L/S ratio |
| **`current_funding_rate`** | float | Current funding rate |
| **`funding_rate_avg_7d`** | float | 7-day average funding rate |
| **`funding_rate_extreme`** | bool | Is funding rate extreme? |
| **`sentiment_score`** | float | Combined sentiment (0-1) |
| **`combined_sentiment`** | string | NEUTRAL, BULLISH, BEARISH |
| **`is_contrarian_signal`** | bool | Contrarian signal detected? |

### Futures Metrics

| Field | Type | Description |
|-------|------|-------------|
| `price` | float | Current futures price |
| `volume_24h` | float | 24-hour volume |
| `open_interest` | float | Open interest |
| `funding_rate` | float | Current funding rate |

---

## Complete Signal Example

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
  "entry_zone": {
    "min": 77739.549,
    "max": 78520.851,
    "ideal": 78130.2
  },
  "stop_loss": {
    "price": 75000.0,
    "type": "WALL_BASED",
    "distance_pct": 4.01
  },
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
    "wall_imbalance": 1.0,
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

---

## Pipeline Stages

The CLI executes a 6-stage pipeline:

| Stage | Name | Description |
|-------|------|-------------|
| 1 | Activity Scan | Scan all assets for activity scores |
| 2 | Asset Selection | Select top N assets by activity |
| 3 | Data Fetching | Fetch Options + Futures + Sentiment data |
| 4 | Analysis | Run IV, PCR, OI, Max Pain, GEX, Sentiment |
| 5 | Whale/Wall Detection | Detect whale activity and OI walls |
| 6 | Signal Generation | Create and output trading signals |

---

## Configuration

### Configuration File

```bash
# Copy example config
cp config/config.example.yaml config.yaml

# Edit with your credentials
nano config.yaml
```

### Configuration Sections

| Section | Description |
|---------|-------------|
| `binance` | API credentials and connection settings |
| `ranking` | Asset selection and activity scoring |
| `intraday` | Multi-timeframe settings (NEW) |
| `whale` | Whale detection thresholds per asset (NEW) |
| `sentiment` | L/S ratio and funding analysis (NEW) |
| `gamma_exposure` | GEX calculation settings (NEW) |
| `analysis` | IV, PCR, OI, Max Pain settings |
| `output` | Signal output and filtering |
| `logging` | Logging configuration |

---

## Testing Commands

### Run All Tests

```bash
# Run all unit tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=binance_signal_generator --cov-report=html
```

### Run Specific Tests

```bash
# Configuration tests
pytest tests/unit/test_config.py -v

# Data fetcher tests
pytest tests/unit/test_data.py -v

# Sentiment tests (NEW)
pytest tests/unit/test_sentiment.py -v

# GEX tests (NEW)
pytest tests/unit/test_gamma.py -v

# Pipeline tests
pytest tests/unit/test_pipeline.py -v
```

---

## Common Workflows

### 1. Daily Signal Generation

```bash
python -m binance_signal_generator --config config.yaml --output signals_$(date +%Y%m%d).json
```

### 2. Development/Testing Mode

```bash
python -m binance_signal_generator --config config.yaml --dry-run -vv --pretty
```

### 3. Monitor Specific Assets

```bash
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT --pretty
```

### 4. Scheduled Execution (Cron)

```cron
# Run every 15 minutes
*/15 * * * * cd /path/to/project && ./venv/bin/python -m binance_signal_generator --config config.yaml --output /var/log/signals/$(date +\%Y\%m\%d_\%H\%M\%S).json 2>> /var/log/signal_generator.log
```

---

## Troubleshooting

### Issue: No Signals Generated

```bash
# Lower activity threshold in config.yaml
# ranking.min_activity_score: 0.10

# Lower confidence threshold
python -m binance_signal_generator --min-confidence 0.25

# Check with verbose output
python -m binance_signal_generator -vv
```

### Issue: API Rate Limits

```bash
# Reduce rate in config.yaml
# binance.rate_limit.requests_per_second: 5
```

### Issue: Connection Timeout

```bash
# Increase timeout in config.yaml
# binance.timeout.connect_seconds: 30
# binance.timeout.read_seconds: 60
```

---

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | Pipeline completed with signals generated |
| 1 | Error | Configuration error, API error, or no signals |
| 130 | Interrupted | User interrupted with Ctrl+C |

---

## Support

For issues and feature requests, please refer to:
- Project documentation in `docs/`
- Configuration guide: `docs/CONFIGURATION.md`
- Architecture overview: `docs/ARCHITECTURE.md`
- Development guide: `docs/DEVELOPMENT.md`

---

*Last Updated: 2026-05-17*
