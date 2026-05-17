# Quick Start Usage Guide

> **Binance Options-Driven Futures Signal Generator**
> Get trading signals in 5 minutes

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Running the System](#4-running-the-system)
5. [Understanding the Output](#5-understanding-the-output)
6. [Common Usage Scenarios](#6-common-usage-scenarios)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

### What You Need

| Requirement | Details |
|-------------|---------|
| Python | Version 3.9 or higher (3.11 recommended) |
| Binance Account | With API access enabled |
| API Key | From [Binance API Management](https://www.binance.com/en/my/settings/api-management) |
| API Permissions | Enable Reading, Futures, and Options |

### API Key Setup

1. Go to **Binance → Profile → API Management**
2. Create a new API key
3. Enable these permissions:
   - ✅ **Enable Reading**
   - ✅ **Enable Futures** (for USDT-M Futures data)
   - ✅ **Enable Options** (for Options data)
4. Copy your API Key and Secret Key

---

## 2. Installation

### Step 1: Navigate to Project

```bash
cd /path/to/binanace-opt-fut
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Linux/macOS:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install the package
pip install -e .
```

### Step 4: Verify Installation

```bash
python -m binance_signal_generator --version

# Expected output:
# binance-signals 2.0.0
```

---

## 3. Configuration

### Step 1: Create Config File

```bash
# Copy the example config
cp config/config.example.yaml config.yaml
```

### Step 2: Add Your API Credentials

Edit `config.yaml` and add your Binance API credentials:

**Option A: Hardcode (Not Recommended for Production)**

```yaml
binance:
  api_key: "your-api-key-here"
  api_secret: "your-api-secret-here"
  testnet: false
```

**Option B: Environment Variables (Recommended)**

```bash
# Set environment variables
export BINANCE_API_KEY="your-api-key-here"
export BINANCE_API_SECRET="your-api-secret-here"
```

Then in `config.yaml`:

```yaml
binance:
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
  testnet: false
```

### Step 3: Key Configuration Settings

Here are the most important settings to check:

```yaml
# How many assets to analyze (default: 5)
ranking:
  top_assets_count: 5
  min_activity_score: 0.15

# Intraday settings (15-min execution)
intraday:
  enabled: true
  oi_period: "15m"
  volume_interval: "15m"

# Minimum signal confidence to output
output:
  signals:
    min_confidence: 0.30

# Logging level (DEBUG for dev, INFO/WARNING for production)
logging:
  level: "INFO"
```

### Step 4: Validate Configuration

```bash
python -m binance_signal_generator --config config.yaml --validate-config

# Expected output:
# Configuration is valid
```

---

## 4. Running the System

### Basic Run (Default Settings)

```bash
# Run with default adaptive selection
python -m binance_signal_generator --config config.yaml
```

### Most Common Commands

```bash
# Run with pretty-printed output (easier to read)
python -m binance_signal_generator --config config.yaml --pretty

# Run for specific symbols
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT --pretty

# Run without saving to database (testing)
python -m binance_signal_generator --config config.yaml --dry-run --pretty

# Save output to file
python -m binance_signal_generator --config config.yaml --output signals.json

# Debug mode with verbose logging
python -m binance_signal_generator --config config.yaml --dry-run -vv --pretty
```

### Command Options Summary

| Option | Description | Example |
|--------|-------------|---------|
| `--config` / `-c` | Path to config file | `--config config.yaml` |
| `--symbols` | Specific symbols to analyze | `--symbols BTCUSDT ETHUSDT` |
| `--dry-run` | Don't save to database | `--dry-run` |
| `--pretty` | Format JSON output | `--pretty` |
| `--output` / `-o` | Save to file | `--output signals.json` |
| `--top-n` | Number of assets to analyze | `--top-n 3` |
| `--min-confidence` | Min signal confidence | `--min-confidence 0.40` |
| `-v` / `-vv` | Verbose logging | `-vv` |
| `--quiet` / `-q` | Minimal output | `--quiet` |

---

## 5. Understanding the Output

### Output Structure

The system outputs JSON with this structure:

```json
{
  "execution_id": "EXEC_20260517_053558_10642a23",
  "timestamp": "2026-05-17T05:35:58.734777Z",
  "execution_duration_seconds": 29.39,
  "assets_analyzed": 2,
  "signals_generated": 2,
  "signals": [...],
  "selected_assets": [...],
  "metadata": {...}
}
```

### Signal Breakdown

Each signal contains these key sections:

#### A. Core Signal Info

```json
{
  "signal_id": "SIG_20260517_053622_BTCUSDT",
  "symbol": "BTCUSDT",
  "direction": "LONG",           // LONG, SHORT, or NEUTRAL
  "confidence_score": 0.55,      // 0.0-1.0, higher = stronger
  "signal_strength": "MODERATE"  // WEAK, MODERATE, STRONG, VERY_STRONG
}
```

#### B. Entry & Risk Management

```json
{
  "entry_zone": {
    "min": 77739.549,    // Lower bound for entry
    "max": 78520.851,    // Upper bound for entry
    "ideal": 78130.2     // Ideal entry price
  },
  "stop_loss": {
    "price": 75000.0,        // Stop loss price
    "type": "WALL_BASED",    // Derived from Options wall
    "distance_pct": 4.01     // Distance from entry (%)
  },
  "take_profit_levels": [
    {"level": 1, "price": 79302.15, "ratio": 1.5},
    {"level": 2, "price": 80474.10, "ratio": 3.0},
    {"level": 3, "price": 82036.71, "ratio": 5.0}
  ],
  "risk_reward_ratio": 1.5
}
```

#### C. Support & Resistance Levels

```json
{
  "support_levels": [
    {"level": 1, "price": 75000.0, "oi": 111, "type": "PUT_WALL"}
  ],
  "resistance_levels": [
    {"level": 1, "price": 94000.0, "gex": -5202517096.1, "type": "GAMMA_RESISTANCE"}
  ]
}
```

#### D. Whale Activity

```json
{
  "whale_metrics": {
    "whale_buy_volume": 3785.55,     // Bullish whale volume ($)
    "whale_sell_volume": 4326.35,    // Bearish whale volume ($)
    "whale_net_volume": -540.80,     // Net = buy - sell
    "whale_direction": "NEUTRAL",    // BULLISH, BEARISH, NEUTRAL
    "whale_activity_score": 0.504,   // 0-1 normalized
    "large_trades_count": 60
  }
}
```

#### E. Options Metrics

```json
{
  "options_metrics": {
    "pcr_combined": 1.6462,          // Put/Call Ratio
    "iv_percentile": 0.35,           // IV percentile (0-1)
    "max_pain_distance": -21.83,     // % from max pain

    // Gamma Exposure (GEX)
    "gex_regime": "POSITIVE",        // POSITIVE = stable, NEGATIVE = volatile
    "dealer_hedge_pressure": "BUY_DIPS",
    "gamma_flip": 70352.79,
    "total_gex": 77936192248.75,

    // Sentiment Analysis
    "top_trader_position_ratio": 1.0,  // >1 = long bias, <1 = short bias
    "top_trader_account_ratio": 1.21,
    "current_funding_rate": 0.0001,
    "funding_rate_avg_7d": 0.00008,
    "funding_rate_extreme": false,
    "sentiment_score": 0.37,
    "combined_sentiment": "BULLISH",
    "is_contrarian_signal": false
  }
}
```

---

## 6. Common Usage Scenarios

### Scenario 1: Quick Check for BTC & ETH

```bash
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT --pretty
```

Use this when you want to quickly check signals for specific assets.

### Scenario 2: Daily Analysis with File Output

```bash
python -m binance_signal_generator --config config.yaml \
  --output signals_$(date +%Y%m%d_%H%M%S).json
```

Use this for scheduled runs where you want to save the output.

### Scenario 3: Development & Debugging

```bash
python -m binance_signal_generator --config config.yaml \
  --dry-run -vv --pretty
```

Use this during development to see detailed logs without saving to database.

### Scenario 4: Lower Thresholds for More Signals

```bash
python -m binance_signal_generator --config config.yaml \
  --min-confidence 0.25 --min-activity 0.10 --pretty
```

Use this if you're not getting enough signals with default thresholds.

### Scenario 5: Production Cron Job

Add to crontab (`crontab -e`):

```cron
# Run every 15 minutes
*/15 * * * * cd /home/user/binanace-opt-fut && /home/user/binanace-opt-fut/venv/bin/python -m binance_signal_generator --config config.yaml --output /var/log/signals/$(date +\%Y\%m\%d_\%H\%M\%S).json 2>> /var/log/signal_generator.log
```

---

## 7. Troubleshooting

### Problem: "No signals generated"

**Cause**: Activity threshold or confidence threshold too high.

**Solution**:

```bash
# Lower thresholds
python -m binance_signal_generator --config config.yaml \
  --min-confidence 0.20 --min-activity 0.10 -vv
```

Or edit `config.yaml`:

```yaml
ranking:
  min_activity_score: 0.10  # Lower this

output:
  signals:
    min_confidence: 0.20    # Lower this
```

### Problem: "API Error: Invalid API key"

**Cause**: API credentials are wrong or missing permissions.

**Solution**:

1. Verify API key has correct permissions (Reading, Futures, Options)
2. Check that credentials are set correctly:

```bash
# Test with environment variables
export BINANCE_API_KEY="your-key"
export BINANCE_API_SECRET="your-secret"
python -m binance_signal_generator --config config.yaml --validate-config
```

### Problem: "Rate limit exceeded"

**Cause**: Too many API calls.

**Solution**: Reduce rate in `config.yaml`:

```yaml
binance:
  rate_limit:
    requests_per_second: 5   # Lower this
    burst: 10                # Lower this
```

### Problem: "Connection timeout"

**Cause**: Network issues or Binance API slow.

**Solution**: Increase timeout in `config.yaml`:

```yaml
binance:
  timeout:
    connect_seconds: 30   # Increase this
    read_seconds: 60      # Increase this
```

### Problem: Too many debug logs

**Cause**: Logging level set to DEBUG.

**Solution**: In `config.yaml`:

```yaml
logging:
  level: "INFO"  # or "WARNING" for less logs
```

Or use `--quiet` flag:

```bash
python -m binance_signal_generator --config config.yaml --quiet
```

---

## Quick Reference Card

```bash
# INSTALLATION
pip install -e .

# CONFIGURATION
cp config/config.example.yaml config.yaml
# Edit config.yaml with your API keys

# VALIDATE
python -m binance_signal_generator --config config.yaml --validate-config

# RUN (Basic)
python -m binance_signal_generator --config config.yaml

# RUN (Pretty output)
python -m binance_signal_generator --config config.yaml --pretty

# RUN (Specific symbols)
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT --pretty

# RUN (Debug mode)
python -m binance_signal_generator --config config.yaml --dry-run -vv --pretty

# RUN (Save to file)
python -m binance_signal_generator --config config.yaml --output signals.json
```

---

## Signal Interpretation Guide

| Metric | Bullish Signal | Bearish Signal |
|--------|----------------|----------------|
| PCR | < 0.8 (call heavy) | > 1.2 (put heavy) |
| IV Percentile | Low IV (< 0.25) | High IV (> 0.75) |
| Whale Net Volume | Positive | Negative |
| Top Trader L/S Ratio | > 1.0 | < 1.0 |
| GEX Regime | POSITIVE (stable) | NEGATIVE (volatile) |
| Funding Rate | Negative (contrarian) | Positive (contrarian) |
| Dealer Pressure | BUY_DIPS | SELL_RIPS |

---

## Next Steps

1. **Read the full documentation**: `docs/README.md`
2. **Understand the pipeline**: `docs/PIPELINE.md`
3. **Configure for your needs**: `docs/CONFIGURATION.md`
4. **See all CLI options**: `docs/CLI_COMMANDS.md`

---

## 8. Framework Integration & Programmatic Usage

This section covers how to integrate the signal generator with frameworks like Django, Flask, FastAPI, standalone cron jobs, and AI agents.

### 8.1 Programmatic Usage (Python Library)

The signal generator can be imported and used as a Python library. The **main feature** is automatic asset selection based on activity ranking.

#### Primary Usage: Auto-Select Top Assets (Recommended)

```python
import asyncio
from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig

async def get_top_signals(top_n=5, min_confidence=0.30):
    """
    AUTO-SELECT top assets by activity ranking.

    This is the PRIMARY usage - system automatically:
    1. Scans ALL available assets
    2. Scores each by activity (OI change, volume, IV, whale activity)
    3. Ranks and selects top N
    4. Generates signals for selected assets

    Args:
        top_n: Number of top assets to select (default: 5)
        min_confidence: Minimum signal confidence

    Returns:
        ExecutionResult with selected_assets and signals
    """
    config = load_config("config/config.yaml")

    pipeline_config = PipelineConfig(
        top_n_assets=top_n,           # Select top N by activity
        min_activity_score=0.15,      # Minimum activity to qualify
        min_signal_confidence=min_confidence,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(
        config=config,
        pipeline_config=pipeline_config,
    )

    try:
        # NO symbols specified = AUTO SELECTION
        result = await orchestrator.run(symbols=None)

        # Access selected assets (show which were auto-selected)
        print(f"Auto-selected {len(result.selected_assets)} assets:")
        for asset in result.selected_assets:
            print(f"  #{asset['rank']}: {asset['symbol']} (score: {asset['activity_score']:.3f}, driver: {asset['primary_driver']})")

        return result
    finally:
        await orchestrator.close()

# Run auto-selection
if __name__ == "__main__":
    result = asyncio.run(get_top_signals(top_n=5))

    print(f"\nGenerated {len(result.signals)} signals:")
    for signal in result.signals:
        print(f"  {signal.symbol}: {signal.direction.value} @ {signal.confidence_score:.2f}")
```

#### Understanding Auto-Selection Output

```python
# The result contains BOTH selected_assets AND signals

result = asyncio.run(get_top_signals(top_n=5))

# 1. Which assets were auto-selected (by ranking)
for asset in result.selected_assets:
    print(f"Rank {asset['rank']}: {asset['symbol']}")
    print(f"  Activity Score: {asset['activity_score']:.3f}")
    print(f"  Primary Driver: {asset['primary_driver']}")  # e.g., "TOTAL_VOLUME", "OI_CHANGE"

# 2. Generated signals for selected assets
for signal in result.signals:
    print(f"{signal.symbol}: {signal.direction.value} (confidence: {signal.confidence_score:.2f})")
```

#### Secondary Usage: Manual Symbol Override (Optional)

```python
async def get_signals_for_symbols(symbols, min_confidence=0.30):
    """
    Manually specify symbols (bypasses auto-selection).

    Use this ONLY when you need specific assets.
    For normal operation, use get_top_signals() instead.
    """
    config = load_config("config/config.yaml")

    pipeline_config = PipelineConfig(
        top_n_assets=len(symbols),
        min_signal_confidence=min_confidence,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(config=config, pipeline_config=pipeline_config)

    try:
        # Symbols specified = MANUAL OVERRIDE (bypasses ranking)
        result = await orchestrator.run(symbols=symbols)
        return result
    finally:
        await orchestrator.close()

# Usage: Only when you need specific symbols
result = asyncio.run(get_signals_for_symbols(["BTCUSDT", "ETHUSDT"]))
```

#### Activity Scoring Components

The auto-selection uses these components for ranking:

| Component | Weight | Description |
|-----------|--------|-------------|
| OI Change | 25% | Open Interest momentum (15m/daily) |
| Volume Spike | 20% | Unusual volume activity |
| IV Percentile | 15% | Implied volatility interest |
| PCR Extreme | 15% | Put/Call ratio extremes |
| Whale Activity | 15% | Large player involvement |
| Total Volume | 10% | Overall volume size |

```python
# Access activity score breakdown
result = asyncio.run(get_top_signals())

for asset in result.selected_assets:
    score = asset['activity_score']
    driver = asset['primary_driver']  # What drove the selection

    # Activity score = weighted sum of all components
    # Higher score = more "interesting" asset
```

### 8.2 Django Integration

#### Option A: Django Management Command (Auto-Selection)

Create a custom management command that uses **auto-selection**:

```python
# your_app/management/commands/generate_signals.py

from django.core.management.base import BaseCommand
from django.utils import timezone
import asyncio
import json

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig

class Command(BaseCommand):
    help = 'Generate trading signals - AUTO-SELECTS top assets by activity ranking'

    def add_arguments(self, parser):
        # Primary: Auto-selection by ranking
        parser.add_argument('--top-n', type=int, default=5,
            help='Number of top assets to AUTO-SELECT by ranking (default: 5)')

        # Optional: Override auto-selection
        parser.add_argument('--symbols', nargs='+', type=str,
            help='[OPTIONAL] Manually specify symbols (bypasses auto-selection)')

        parser.add_argument('--min-activity', type=float, default=0.15,
            help='Minimum activity score for auto-selection')
        parser.add_argument('--min-confidence', type=float, default=0.30,
            help='Minimum signal confidence')

    def handle(self, *args, **options):
        async def run():
            config = load_config('config/config.yaml')

            pipeline_config = PipelineConfig(
                top_n_assets=options['top_n'],
                min_activity_score=options['min_activity'],
                min_signal_confidence=options['min_confidence'],
                save_to_database=False,
            )

            orchestrator = PipelineOrchestrator(config=config, pipeline_config=pipeline_config)

            try:
                # AUTO-SELECTION: symbols=None triggers ranking
                result = await orchestrator.run(symbols=options['symbols'])

                # Show which assets were auto-selected
                self.stdout.write(self.style.HTTP_INFO(
                    f"\nAuto-selected {len(result.selected_assets)} assets by activity ranking:"
                ))
                for asset in result.selected_assets:
                    self.stdout.write(f"  #{asset['rank']}: {asset['symbol']} "
                        f"(score: {asset['activity_score']:.3f}, driver: {asset['primary_driver']})")

                # Save to Django model
                self._save_signals(result)

                self.stdout.write(self.style.SUCCESS(
                    f"\nGenerated {len(result.signals)} signals"
                ))
            finally:
                await orchestrator.close()

        asyncio.run(run())

    def _save_signals(self, result):
        from your_app.models import TradingSignalModel

        for signal in result.signals:
            TradingSignalModel.objects.create(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                direction=signal.direction.value,
                confidence=signal.confidence_score,
                entry_price=signal.entry_zone.ideal,
                stop_loss=signal.stop_loss.price,
                take_profit_1=signal.take_profit_levels[0].price if signal.take_profit_levels else None,
                whale_metrics=signal.whale_metrics,
                options_metrics=signal.options_metrics,
                created_at=timezone.now(),
            )
```

Run it:

```bash
# AUTO-SELECT top 5 assets by activity (RECOMMENDED)
python manage.py generate_signals --top-n 5

# AUTO-SELECT top 10 assets
python manage.py generate_signals --top-n 10 --min-activity 0.10

# [OPTIONAL] Manual override for specific symbols
python manage.py generate_signals --symbols BTCUSDT ETHUSDT
```

#### Option B: Django REST API (Auto-Selection)

```python
# your_app/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import asyncio

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig


class AutoSelectSignalsView(APIView):
    """
    AUTO-SELECT top assets by activity ranking and generate signals.

    This is the PRIMARY endpoint - uses the system's adaptive ranking.
    """

    def post(self, request):
        # Auto-selection parameters
        top_n = request.data.get('top_n', 5)
        min_activity = request.data.get('min_activity', 0.15)
        min_confidence = request.data.get('min_confidence', 0.30)

        result = asyncio.run(self._auto_select_and_generate(top_n, min_activity, min_confidence))

        return Response({
            'execution_id': result.execution_id,
            'timestamp': result.timestamp.isoformat(),
            'auto_selection': {
                'method': 'ACTIVITY_RANKING',
                'assets_scanned': result.assets_analyzed,
                'selected_assets': result.selected_assets,  # Show which were selected
            },
            'signals_count': len(result.signals),
            'signals': [self._format_signal(s) for s in result.signals],
            'errors': result.errors,
        })

    async def _auto_select_and_generate(self, top_n, min_activity, min_confidence):
        config = load_config('config/config.yaml')

        pipeline_config = PipelineConfig(
            top_n_assets=top_n,
            min_activity_score=min_activity,
            min_signal_confidence=min_confidence,
            save_to_database=False,
        )

        orchestrator = PipelineOrchestrator(config=config, pipeline_config=pipeline_config)

        try:
            # symbols=None = AUTO-SELECTION by ranking
            return await orchestrator.run(symbols=None)
        finally:
            await orchestrator.close()

    def _format_signal(self, signal):
        return {
            'signal_id': signal.signal_id,
            'symbol': signal.symbol,
            'direction': signal.direction.value,
            'confidence': signal.confidence_score,
            'entry_zone': {
                'min': signal.entry_zone.min,
                'max': signal.entry_zone.max,
                'ideal': signal.entry_zone.ideal,
            },
            'stop_loss': signal.stop_loss.price,
            'take_profit': [
                {'level': tp.level, 'price': tp.price}
                for tp in signal.take_profit_levels
            ],
            'whale_direction': signal.whale_metrics.get('whale_direction'),
            'gex_regime': signal.options_metrics.get('gex_regime'),
            'sentiment': signal.options_metrics.get('combined_sentiment'),
        }


class ManualSignalsView(APIView):
    """
    Manual symbol override (bypasses auto-selection).
    Use only when you need specific symbols.
    """

    def post(self, request):
        symbols = request.data.get('symbols')  # Required

        if not symbols:
            return Response({'error': 'symbols required for manual override'},
                          status=status.HTTP_400_BAD_REQUEST)

        result = asyncio.run(self._generate_for_symbols(symbols))

        return Response({
            'method': 'MANUAL_OVERRIDE',
            'symbols': symbols,
            'signals': [self._format_signal(s) for s in result.signals],
        })

    async def _generate_for_symbols(self, symbols):
        config = load_config('config/config.yaml')
        pipeline_config = PipelineConfig(top_n_assets=len(symbols))
        orchestrator = PipelineOrchestrator(config=config, pipeline_config=pipeline_config)
        try:
            return await orchestrator.run(symbols=symbols)
        finally:
            await orchestrator.close()

    def _format_signal(self, signal):
        return {
            'symbol': signal.symbol,
            'direction': signal.direction.value,
            'confidence': signal.confidence_score,
            'entry': signal.entry_zone.ideal,
            'stop_loss': signal.stop_loss.price,
        }
```

Add to `urls.py`:

```python
from django.urls import path
from your_app.views import AutoSelectSignalsView, ManualSignalsView

urlpatterns = [
    # PRIMARY: Auto-selection by ranking
    path('api/signals/auto/', AutoSelectSignalsView.as_view()),

    # SECONDARY: Manual override
    path('api/signals/manual/', ManualSignalsView.as_view()),
]
```

**API Usage:**

```bash
# PRIMARY: Auto-select top 5 assets (recommended)
curl -X POST http://localhost:8000/api/signals/auto/ \
  -H "Content-Type: application/json" \
  -d '{"top_n": 5, "min_activity": 0.15}'

# Response includes which assets were auto-selected:
# {
#   "auto_selection": {
#     "method": "ACTIVITY_RANKING",
#     "selected_assets": [
#       {"rank": 1, "symbol": "BTCUSDT", "activity_score": 0.283, "primary_driver": "TOTAL_VOLUME"},
#       {"rank": 2, "symbol": "ETHUSDT", "activity_score": 0.245, "primary_driver": "OI_CHANGE"}
#     ]
#   },
#   "signals": [...]
# }

# SECONDARY: Manual override (only when needed)
curl -X POST http://localhost:8000/api/signals/manual/ \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTCUSDT", "ETHUSDT"]}'
```

### 8.3 Flask Integration (Auto-Selection)

```python
# app.py

from flask import Flask, jsonify, request
import asyncio

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig

app = Flask(__name__)

# Load config once at startup
CONFIG = load_config('config/config.yaml')


async def auto_select_signals(top_n=5, min_activity=0.15, min_confidence=0.30):
    """
    AUTO-SELECT top assets by activity ranking.

    This is the PRIMARY function - system automatically:
    1. Scans ALL available assets
    2. Scores by activity (OI change, volume, IV, whale activity)
    3. Ranks and selects top N
    4. Generates signals for selected assets
    """
    pipeline_config = PipelineConfig(
        top_n_assets=top_n,
        min_activity_score=min_activity,
        min_signal_confidence=min_confidence,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(config=CONFIG, pipeline_config=pipeline_config)

    try:
        # symbols=None = AUTO-SELECTION
        return await orchestrator.run(symbols=None)
    finally:
        await orchestrator.close()


async def get_signals_for_symbols(symbols, min_confidence=0.30):
    """
    Manual override - bypasses auto-selection.
    Use only when you need specific symbols.
    """
    pipeline_config = PipelineConfig(
        top_n_assets=len(symbols),
        min_signal_confidence=min_confidence,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(config=CONFIG, pipeline_config=pipeline_config)

    try:
        return await orchestrator.run(symbols=symbols)
    finally:
        await orchestrator.close()


@app.route('/api/signals/auto', methods=['POST'])
def auto_select():
    """
    PRIMARY ENDPOINT: Auto-select top assets by activity ranking.

    Request body (optional):
    {
        "top_n": 5,
        "min_activity": 0.15,
        "min_confidence": 0.30
    }
    """
    data = request.get_json() or {}

    top_n = data.get('top_n', 5)
    min_activity = data.get('min_activity', 0.15)
    min_confidence = data.get('min_confidence', 0.30)

    # Run auto-selection
    result = asyncio.run(auto_select_signals(top_n, min_activity, min_confidence))

    return jsonify({
        'success': True,
        'method': 'AUTO_SELECTION',
        'execution_id': result.execution_id,
        'timestamp': result.timestamp.isoformat(),
        'auto_selection': {
            'assets_scanned': result.assets_analyzed,
            'selected_assets': result.selected_assets,  # Which assets were ranked and selected
        },
        'signals_count': len(result.signals),
        'signals': [
            {
                'signal_id': s.signal_id,
                'symbol': s.symbol,
                'rank': s.asset_rank,
                'activity_score': s.activity_score,
                'direction': s.direction.value,
                'confidence': s.confidence_score,
                'entry': s.entry_zone.ideal,
                'stop_loss': s.stop_loss.price,
                'whale_direction': s.whale_metrics.get('whale_direction'),
                'gex_regime': s.options_metrics.get('gex_regime'),
                'sentiment': s.options_metrics.get('combined_sentiment'),
            }
            for s in result.signals
        ],
        'errors': result.errors,
    })


@app.route('/api/signals/manual', methods=['POST'])
def manual_select():
    """
    SECONDARY: Manual symbol override (bypasses auto-selection).
    Use only when you need specific symbols.
    """
    data = request.get_json() or {}
    symbols = data.get('symbols')

    if not symbols:
        return jsonify({'error': 'symbols required for manual override'}), 400

    result = asyncio.run(get_signals_for_symbols(symbols))

    return jsonify({
        'method': 'MANUAL_OVERRIDE',
        'signals': [
            {
                'symbol': s.symbol,
                'direction': s.direction.value,
                'confidence': s.confidence_score,
                'entry': s.entry_zone.ideal,
                'stop_loss': s.stop_loss.price,
            }
            for s in result.signals
        ],
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
```

Run with Gunicorn (production):

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
```

**API Usage:**

```bash
# PRIMARY: Auto-select top 5 assets (RECOMMENDED)
curl -X POST http://localhost:5000/api/signals/auto \
  -H "Content-Type: application/json" \
  -d '{"top_n": 5}'

# Response shows which assets were auto-selected:
# {
#   "method": "AUTO_SELECTION",
#   "auto_selection": {
#     "selected_assets": [
#       {"rank": 1, "symbol": "BTCUSDT", "activity_score": 0.283, "primary_driver": "TOTAL_VOLUME"},
#       {"rank": 2, "symbol": "ETHUSDT", "activity_score": 0.245, "primary_driver": "OI_CHANGE"}
#     ]
#   },
#   "signals": [...]
# }

# SECONDARY: Manual override (only when needed)
curl -X POST http://localhost:5000/api/signals/manual \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTCUSDT", "ETHUSDT"]}'
```

### 8.4 FastAPI Integration (Auto-Selection)

```python
# main.py

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig

app = FastAPI(
    title="Binance Signal Generator API",
    description="API for generating trading signals with AUTO-SELECTION by activity ranking",
    version="2.0.0",
)

# Load config at startup
CONFIG = load_config('config/config.yaml')


# ============== Request/Response Models ==============

class AutoSelectRequest(BaseModel):
    """Request for AUTO-SELECTION by activity ranking (PRIMARY endpoint)"""
    top_n: int = 5
    min_activity: float = 0.15
    min_confidence: float = 0.30


class ManualSelectRequest(BaseModel):
    """Request for manual symbol override (SECONDARY endpoint)"""
    symbols: List[str]
    min_confidence: float = 0.30


class SelectedAsset(BaseModel):
    """Asset selected by auto-ranking"""
    symbol: str
    rank: int
    activity_score: float
    primary_driver: str


class SignalResponse(BaseModel):
    """Generated trading signal"""
    signal_id: str
    symbol: str
    rank: int
    activity_score: float
    direction: str
    confidence: float
    entry_price: float
    stop_loss: float
    whale_direction: Optional[str]
    gex_regime: Optional[str]
    sentiment: Optional[str]


class AutoSelectResponse(BaseModel):
    """Response from AUTO-SELECTION endpoint"""
    method: str = "AUTO_SELECTION"
    execution_id: str
    auto_selection: dict
    signals_count: int
    signals: List[SignalResponse]


# ============== Core Functions ==============

async def auto_select_and_generate(top_n=5, min_activity=0.15, min_confidence=0.30):
    """
    AUTO-SELECT top assets by activity ranking.

    This is the PRIMARY function - the system's main feature.
    """
    pipeline_config = PipelineConfig(
        top_n_assets=top_n,
        min_activity_score=min_activity,
        min_signal_confidence=min_confidence,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(config=CONFIG, pipeline_config=pipeline_config)

    try:
        # symbols=None = AUTO-SELECTION by ranking
        return await orchestrator.run(symbols=None)
    finally:
        await orchestrator.close()


async def generate_for_symbols(symbols, min_confidence=0.30):
    """Manual override - bypasses auto-selection."""
    pipeline_config = PipelineConfig(
        top_n_assets=len(symbols),
        min_signal_confidence=min_confidence,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(config=CONFIG, pipeline_config=pipeline_config)

    try:
        return await orchestrator.run(symbols=symbols)
    finally:
        await orchestrator.close()


def format_signal(s):
    """Format signal for API response."""
    return SignalResponse(
        signal_id=s.signal_id,
        symbol=s.symbol,
        rank=s.asset_rank,
        activity_score=s.activity_score,
        direction=s.direction.value,
        confidence=round(s.confidence_score, 3),
        entry_price=round(s.entry_zone.ideal, 2),
        stop_loss=round(s.stop_loss.price, 2),
        whale_direction=s.whale_metrics.get('whale_direction'),
        gex_regime=s.options_metrics.get('gex_regime'),
        sentiment=s.options_metrics.get('combined_sentiment'),
    )


# ============== API Endpoints ==============

@app.post("/api/signals/auto", response_model=AutoSelectResponse)
async def auto_select_signals(request: AutoSelectRequest):
    """
    PRIMARY ENDPOINT: Auto-select top assets by activity ranking.

    The system automatically:
    1. Scans ALL available assets
    2. Scores each by activity (OI change, volume, IV, whale activity, etc.)
    3. Ranks and selects top N
    4. Generates signals for selected assets

    - **top_n**: Number of top assets to select (default: 5)
    - **min_activity**: Minimum activity score for selection (default: 0.15)
    - **min_confidence**: Minimum signal confidence (default: 0.30)
    """
    result = await auto_select_and_generate(
        top_n=request.top_n,
        min_activity=request.min_activity,
        min_confidence=request.min_confidence,
    )

    return AutoSelectResponse(
        execution_id=result.execution_id,
        auto_selection={
            "method": "ACTIVITY_RANKING",
            "assets_scanned": result.assets_analyzed,
            "selected_assets": result.selected_assets,
        },
        signals_count=len(result.signals),
        signals=[format_signal(s) for s in result.signals],
    )


@app.post("/api/signals/manual")
async def manual_select_signals(request: ManualSelectRequest):
    """
    SECONDARY: Manual symbol override (bypasses auto-selection).

    Use this ONLY when you need specific assets.
    For normal operation, use /api/signals/auto instead.
    """
    result = await generate_for_symbols(
        symbols=request.symbols,
        min_confidence=request.min_confidence,
    )

    return {
        "method": "MANUAL_OVERRIDE",
        "symbols": request.symbols,
        "signals_count": len(result.signals),
        "signals": [format_signal(s) for s in result.signals],
    }


@app.get("/api/signals/raw/{symbol}")
async def get_raw_signal(symbol: str):
    """Get complete raw signal data for a specific symbol."""
    result = await generate_for_symbols(symbols=[symbol])

    if not result.signals:
        raise HTTPException(status_code=404, detail="No signal generated")

    signal = result.signals[0]

    return JSONResponse(content={
        "signal_id": signal.signal_id,
        "timestamp": signal.timestamp.isoformat(),
        "symbol": signal.symbol,
        "direction": signal.direction.value,
        "confidence_score": signal.confidence_score,
        "signal_strength": signal.signal_strength.value,
        "entry_zone": {
            "min": signal.entry_zone.min,
            "max": signal.entry_zone.max,
            "ideal": signal.entry_zone.ideal,
        },
        "stop_loss": {
            "price": signal.stop_loss.price,
            "type": signal.stop_loss.type,
            "distance_pct": signal.stop_loss.distance_pct,
        },
        "take_profit_levels": [
            {"level": tp.level, "price": tp.price, "ratio": tp.ratio}
            for tp in signal.take_profit_levels
        ],
        "support_levels": signal.support_levels,
        "resistance_levels": signal.resistance_levels,
        "whale_metrics": signal.whale_metrics,
        "options_metrics": signal.options_metrics,
    })


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Run with Uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**API Usage:**

```bash
# PRIMARY: Auto-select top 5 assets (RECOMMENDED)
curl -X POST http://localhost:8000/api/signals/auto \
  -H "Content-Type: application/json" \
  -d '{"top_n": 5, "min_activity": 0.15}'

# Response shows which assets were auto-selected:
# {
#   "method": "AUTO_SELECTION",
#   "execution_id": "EXEC_20260517_120000_abc123",
#   "auto_selection": {
#     "method": "ACTIVITY_RANKING",
#     "assets_scanned": 25,
#     "selected_assets": [
#       {"rank": 1, "symbol": "BTCUSDT", "activity_score": 0.283, "primary_driver": "TOTAL_VOLUME"},
#       {"rank": 2, "symbol": "ETHUSDT", "activity_score": 0.245, "primary_driver": "OI_CHANGE"},
#       {"rank": 3, "symbol": "SOLUSDT", "activity_score": 0.198, "primary_driver": "WHALE_ACTIVITY"}
#     ]
#   },
#   "signals_count": 3,
#   "signals": [...]
# }

# SECONDARY: Manual override (only when needed)
curl -X POST http://localhost:8000/api/signals/manual \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTCUSDT", "ETHUSDT"]}'
```

**FastAPI Interactive Docs:**

Access at `http://localhost:8000/docs` for Swagger UI with full API documentation.

### 8.5 Standalone Cron Job (Auto-Selection)

#### Cron Script with Auto-Selection

```python
# cron_signal_generator.py

#!/usr/bin/env python3
"""
Standalone script for cron execution.
AUTO-SELECTS top assets by activity ranking and saves signals.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, '/path/to/binanace-opt-fut/src')

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig

# Configuration
CONFIG_PATH = '/path/to/binanace-opt-fut/config/config.yaml'
OUTPUT_DIR = '/var/log/signals'
WEBHOOK_URL = os.environ.get('SIGNAL_WEBHOOK_URL')  # Optional webhook

# Auto-selection parameters
TOP_N_ASSETS = 5           # Number of top assets to AUTO-SELECT
MIN_ACTIVITY_SCORE = 0.15  # Minimum activity for selection
MIN_SIGNAL_CONFIDENCE = 0.30


async def auto_select_and_save():
    """
    AUTO-SELECT top assets by activity ranking and save signals.

    This is the PRIMARY cron function - uses adaptive asset selection.
    """
    # Ensure output directory exists
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # Load config
    config = load_config(CONFIG_PATH)

    # Pipeline config with AUTO-SELECTION
    pipeline_config = PipelineConfig(
        top_n_assets=TOP_N_ASSETS,
        min_activity_score=MIN_ACTIVITY_SCORE,
        min_signal_confidence=MIN_SIGNAL_CONFIDENCE,
        save_to_database=False,
    )

    orchestrator = PipelineOrchestrator(config=config, pipeline_config=pipeline_config)

    try:
        # AUTO-SELECTION: symbols=None triggers activity ranking
        result = await orchestrator.run(symbols=None)

        # Log which assets were auto-selected
        print(f"\n{'='*60}")
        print(f"AUTO-SELECTED {len(result.selected_assets)} assets by activity ranking:")
        print(f"{'='*60}")
        for asset in result.selected_assets:
            print(f"  #{asset['rank']}: {asset['symbol']:<12} "
                  f"score={asset['activity_score']:.3f} "
                  f"driver={asset['primary_driver']}")

        # Create output filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_file = f"{OUTPUT_DIR}/signals_{timestamp}.json"

        # Convert to dict
        output_data = {
            "method": "AUTO_SELECTION",
            "execution_id": result.execution_id,
            "timestamp": result.timestamp.isoformat(),
            "duration_seconds": result.execution_duration_seconds,
            "auto_selection": {
                "assets_scanned": result.assets_analyzed,
                "selected_assets": result.selected_assets,
            },
            "signals_count": len(result.signals),
            "signals": [
                {
                    "signal_id": s.signal_id,
                    "symbol": s.symbol,
                    "rank": s.asset_rank,
                    "activity_score": s.activity_score,
                    "direction": s.direction.value,
                    "confidence": s.confidence_score,
                    "entry": s.entry_zone.ideal,
                    "stop_loss": s.stop_loss.price,
                    "take_profit": [
                        {"level": tp.level, "price": tp.price}
                        for tp in s.take_profit_levels
                    ],
                    "whale_direction": s.whale_metrics.get('whale_direction'),
                    "gex_regime": s.options_metrics.get('gex_regime'),
                    "sentiment": s.options_metrics.get('combined_sentiment'),
                }
                for s in result.signals
            ],
            "errors": result.errors,
        }

        # Save to file
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\nGenerated {len(result.signals)} signals -> {output_file}")

        # Optional: Send to webhook
        if WEBHOOK_URL and result.signals:
            await send_to_webhook(output_data)

        return result

    finally:
        await orchestrator.close()


async def send_to_webhook(data):
    """Send signals to webhook (e.g., Telegram bot, Slack)."""
    import aiohttp

    # Create a readable summary for webhook
    summary = f"""
🚀 **Binance Signal Generator**

**Auto-Selected Assets:**
{chr(10).join([f"#{a['rank']} {a['symbol']} (score: {a['activity_score']:.3f})" for a in data['auto_selection']['selected_assets']])}

**Signals Generated:** {data['signals_count']}
{chr(10).join([f"• {s['symbol']}: {s['direction']} @ {s['confidence']:.2f}" for s in data['signals']])}
"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL,
                json={"text": summary, "data": data},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    print(f"Webhook notification sent successfully")
                else:
                    print(f"Webhook failed: {response.status}")
    except Exception as e:
        print(f"Webhook error: {e}")


if __name__ == '__main__':
    print(f"\n[{datetime.utcnow().isoformat()}] Starting AUTO-SELECTION signal generation...")
    asyncio.run(auto_select_and_save())
```

#### Sample Cron Output

```
============================================================
AUTO-SELECTED 5 assets by activity ranking:
============================================================
  #1: BTCUSDT     score=0.283 driver=TOTAL_VOLUME
  #2: ETHUSDT     score=0.245 driver=OI_CHANGE
  #3: SOLUSDT     score=0.198 driver=WHALE_ACTIVITY
  #4: BNBUSDT     score=0.167 driver=IV_INTEREST
  #5: XRPUSDT     score=0.142 driver=PCR_EXTREME

Generated 3 signals -> /var/log/signals/signals_20260517_120000.json
```

#### Crontab Entry

```bash
# Edit crontab
crontab -e

# Add entry (run every 15 minutes)
*/15 * * * * /path/to/binanace-opt-fut/venv/bin/python /path/to/binanace-opt-fut/cron_signal_generator.py >> /var/log/signal_generator.log 2>&1
```

#### Systemd Timer (Alternative to Cron)

```ini
# /etc/systemd/system/signal-generator.service

[Unit]
Description=Binance Signal Generator
After=network.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/path/to/binanace-opt-fut
ExecStart=/path/to/binanace-opt-fut/venv/bin/python cron_signal_generator.py
Environment="BINANCE_API_KEY=your-key"
Environment="BINANCE_API_SECRET=your-secret"

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/signal-generator.timer

[Unit]
Description=Run signal generator every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable signal-generator.timer
sudo systemctl start signal-generator.timer
```

### 8.6 AI Agent Integration (Auto-Selection)

#### Using with OpenAI / GPT API

```python
# ai_agent_integration.py

import asyncio
import json
from openai import OpenAI

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig


class SignalAnalysisAgent:
    """
    AI-powered signal analysis agent.
    AUTO-SELECTS top assets and uses LLM for enhanced analysis.
    """

    def __init__(self, config_path="config/config.yaml", openai_api_key=None):
        self.config = load_config(config_path)
        self.client = OpenAI(api_key=openai_api_key)

    async def auto_select_signals(self, top_n=5, min_activity=0.15):
        """
        AUTO-SELECT top assets by activity ranking.

        PRIMARY METHOD: Uses adaptive asset selection.
        """
        pipeline_config = PipelineConfig(
            top_n_assets=top_n,
            min_activity_score=min_activity,
            min_signal_confidence=0.30,
            save_to_database=False,
        )

        orchestrator = PipelineOrchestrator(
            config=self.config,
            pipeline_config=pipeline_config,
        )

        try:
            # symbols=None = AUTO-SELECTION
            return await orchestrator.run(symbols=None)
        finally:
            await orchestrator.close()

    def analyze_with_ai(self, result):
        """Use AI to analyze and explain auto-selected signals."""

        # Format selected assets
        selected_text = "\n".join([
            f"#{a['rank']} {a['symbol']} (score: {a['activity_score']:.3f}, driver: {a['primary_driver']})"
            for a in result.selected_assets
        ])

        # Format signals for AI analysis
        signals_text = "\n".join([
            f"""
            Signal {i+1}: {s.symbol} (Rank #{s.asset_rank})
            - Direction: {s.direction.value}
            - Confidence: {s.confidence_score:.2f}
            - Activity Score: {s.activity_score:.3f}
            - Entry Zone: ${s.entry_zone.ideal:,.2f}
            - Stop Loss: ${s.stop_loss.price:,.2f}
            - Whale Direction: {s.whale_metrics.get('whale_direction', 'N/A')}
            - GEX Regime: {s.options_metrics.get('gex_regime', 'N/A')}
            - Dealer Pressure: {s.options_metrics.get('dealer_hedge_pressure', 'N/A')}
            - Sentiment: {s.options_metrics.get('combined_sentiment', 'N/A')}
            """
            for i, s in enumerate(result.signals)
        ])

        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional crypto trading analyst.
                    Analyze the provided trading signals and give:
                    1. Overall market sentiment interpretation
                    2. Why these assets were auto-selected (based on activity scores)
                    3. Risk assessment for each signal
                    4. Recommended position sizing
                    5. Key levels to watch"""
                },
                {
                    "role": "user",
                    "content": f"""
Auto-selected assets by activity ranking:
{selected_text}

Generated signals:
{signals_text}

Analyze these signals and explain why these assets were selected.
"""
                }
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        return response.choices[0].message.content

    async def run(self, top_n=5):
        """AUTO-SELECT top assets and get AI analysis."""
        # Get signals via AUTO-SELECTION
        result = await self.auto_select_signals(top_n=top_n)

        if not result.signals:
            return {"error": "No signals generated", "raw_result": result}

        # Get AI analysis
        ai_analysis = self.analyze_with_ai(result)

        return {
            "method": "AUTO_SELECTION",
            "selected_assets": result.selected_assets,
            "signals": [
                {
                    "symbol": s.symbol,
                    "rank": s.asset_rank,
                    "activity_score": s.activity_score,
                    "direction": s.direction.value,
                    "confidence": s.confidence_score,
                    "entry": s.entry_zone.ideal,
                    "stop_loss": s.stop_loss.price,
                }
                for s in result.signals
            ],
            "ai_analysis": ai_analysis,
            "timestamp": result.timestamp.isoformat(),
        }


# Usage
async def main():
    agent = SignalAnalysisAgent(
        config_path="config/config.yaml",
        openai_api_key="your-openai-api-key",
    )

    # AUTO-SELECT top 5 assets and analyze
    result = await agent.run(top_n=5)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

#### Function Calling / Tool Use Pattern (Auto-Selection)

```python
# ai_tool_integration.py

import asyncio
import json
from openai import OpenAI

from binance_signal_generator.config.loader import load_config
from binance_signal_generator.pipeline.orchestrator import PipelineOrchestrator, PipelineConfig


# Define the tool schema for OpenAI function calling
SIGNAL_GENERATOR_TOOL = {
    "type": "function",
    "function": {
        "name": "auto_select_trading_signals",
        "description": "AUTO-SELECT top cryptocurrency assets by activity ranking and generate trading signals. Uses Options market analysis (IV, PCR, OI, whale activity) to rank and select the most active assets.",
        "parameters": {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "description": "Number of top assets to AUTO-SELECT by ranking (default: 5)",
                    "default": 5,
                },
                "min_activity": {
                    "type": "number",
                    "description": "Minimum activity score for selection (default: 0.15)",
                    "default": 0.15,
                },
            },
            "required": [],
        },
    },
}


class TradingAgent:
    """
    AI Agent with function calling capability.
    Uses AUTO-SELECTION by default.
    """

    def __init__(self, openai_api_key=None):
        self.client = OpenAI(api_key=openai_api_key)
        self.config = load_config("config/config.yaml")

    async def auto_select_signals(self, top_n=5, min_activity=0.15):
        """AUTO-SELECT signals by activity ranking."""
        pipeline_config = PipelineConfig(
            top_n_assets=top_n,
            min_activity_score=min_activity,
            min_signal_confidence=0.30,
            save_to_database=False,
        )

        orchestrator = PipelineOrchestrator(
            config=self.config,
            pipeline_config=pipeline_config,
        )

        try:
            result = await orchestrator.run(symbols=None)  # AUTO-SELECTION

            return {
                "method": "AUTO_SELECTION",
                "selected_assets": result.selected_assets,
                "signals": [
                    {
                        "symbol": s.symbol,
                        "rank": s.asset_rank,
                        "activity_score": s.activity_score,
                        "direction": s.direction.value,
                        "confidence": round(s.confidence_score, 3),
                        "entry": round(s.entry_zone.ideal, 2),
                        "stop_loss": round(s.stop_loss.price, 2),
                        "whale_direction": s.whale_metrics.get("whale_direction"),
                        "gex_regime": s.options_metrics.get("gex_regime"),
                        "sentiment": s.options_metrics.get("combined_sentiment"),
                    }
                    for s in result.signals
                ],
                "errors": result.errors,
            }
        finally:
            await orchestrator.close()

    def chat(self, user_message):
        """Interactive chat with function calling."""

        messages = [
            {
                "role": "system",
                "content": """You are a cryptocurrency trading assistant.
                You have access to a signal generator that AUTO-SELECTS the top assets by activity ranking.
                The system analyzes Options market data (IV, PCR, OI, whale activity) to find the most interesting assets.
                Use the auto_select_trading_signals function when users ask about trading signals.
                Always explain which assets were auto-selected and why.""",
            },
            {"role": "user", "content": user_message},
        ]

        # First call - may request function
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            tools=[SIGNAL_GENERATOR_TOOL],
            tool_choice="auto",
        )

        message = response.choices[0].message

        # Check if function was called
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "auto_select_trading_signals":
                    # Parse arguments
                    args = json.loads(tool_call.function.arguments)

                    # Execute the AUTO-SELECTION function
                    result = asyncio.run(
                        self.auto_select_signals(
                            top_n=args.get("top_n", 5),
                            min_activity=args.get("min_activity", 0.15),
                        )
                    )

                    # Add function result to messages
                    messages.append(message)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })

                    # Get final response
                    final_response = self.client.chat.completions.create(
                        model="gpt-4",
                        messages=messages,
                    )

                    return final_response.choices[0].message.content

        return message.content


# Usage
if __name__ == "__main__":
    agent = TradingAgent(openai_api_key="your-openai-api-key")

    # Interactive queries - all use AUTO-SELECTION
    print(agent.chat("What are the top trading opportunities right now?"))
    print(agent.chat("Find me the 5 most active crypto assets"))
    print(agent.chat("Which assets have the most whale activity?"))
```

**Sample AI Agent Interaction:**

```
User: "What are the top trading opportunities right now?"

AI Agent Response:
Based on my analysis of the Binance Options market, here are the top trading opportunities:

**Auto-Selected Assets by Activity Ranking:**
1. BTCUSDT (Activity Score: 0.283) - Driven by high total volume
2. ETHUSDT (Activity Score: 0.245) - Significant OI changes detected
3. SOLUSDT (Activity Score: 0.198) - Notable whale activity

**Signal Analysis:**
- BTCUSDT: LONG with 40% confidence. Entry around $78,130.
  Whale activity is NEUTRAL, GEX regime is POSITIVE (stable).
- ETHUSDT: LONG with 55% confidence. Entry around $2,850.
  Bullish sentiment from top traders (L/S ratio: 1.36).

These assets were selected because they show the highest combined activity
scores from OI changes, volume spikes, IV interest, and whale movements.
```

### 8.7 Quick Reference: Integration Patterns

| Use Case | Pattern | Primary Endpoint |
|----------|---------|------------------|
| Django REST API | `AutoSelectSignalsView` | `POST /api/signals/auto/` |
| Flask endpoint | `auto_select_signals()` | `POST /api/signals/auto` |
| FastAPI | `auto_select_signals()` | `POST /api/signals/auto` |
| Cron job | `auto_select_and_save()` | Saves to file with selected assets |
| AI Agent | `auto_select_trading_signals` tool | Function calling with OpenAI |

### 8.8 Key Concept: Auto-Selection vs Manual Override

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AUTO-SELECTION (PRIMARY)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  orchestrator.run(symbols=None)  →  AUTO-SELECT by ranking         │
│                                                                     │
│  1. Scans ALL available assets                                      │
│  2. Scores by activity (OI change, volume, IV, whale, PCR)         │
│  3. Ranks and selects top N                                         │
│  4. Returns: selected_assets + signals                              │
│                                                                     │
│  Use this for: Normal operation, cron jobs, AI agents              │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                    MANUAL OVERRIDE (SECONDARY)                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  orchestrator.run(symbols=["BTCUSDT", "ETHUSDT"])                  │
│                                                                     │
│  1. Bypasses activity scan                                          │
│  2. Analyzes only specified symbols                                 │
│  3. No ranking or selection                                         │
│                                                                     │
│  Use this for: Debugging, specific asset requests                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

*Last Updated: 2026-05-17*
