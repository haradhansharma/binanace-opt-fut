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
6. [Configuration](#configuration)
7. [Environment Variables](#environment-variables)
8. [Testing Commands](#testing-commands)
9. [Common Workflows](#common-workflows)
10. [Error Handling](#error-handling)
11. [Exit Codes](#exit-codes)
12. [Examples](#examples)

---

## Overview

The Binance Signal Generator CLI (`binance-signals`) is the primary interface for running the signal generation pipeline. It provides a comprehensive set of options for configuring and executing the pipeline, outputting results in JSON format suitable for downstream processing.

### Key Features

- **Adaptive Asset Selection**: Automatically selects top N assets based on Options activity
- **Manual Symbol Override**: Analyze specific symbols on demand
- **Flexible Output**: JSON to stdout or file, with pretty-printing options
- **Dry-Run Mode**: Test without database persistence
- **Configuration Validation**: Validate config before running
- **Verbose Logging**: Multiple verbosity levels for debugging

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

### From Source

```bash
# Clone the repository
git clone <repository-url>
cd binance-options-futures-signal-generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Check version
python -m binance_signal_generator --version

# Expected output:
# binance-signals 1.0.0
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
| `--symbols` | | SYMBOL [...] | None | Specific symbols to analyze (bypasses adaptive selection) |
| `--dry-run` | | flag | False | Run without saving to database |
| `--top-n` | | N | 5 | Number of top assets to analyze |
| `--min-confidence` | | SCORE | 0.50 | Minimum signal confidence to output |

### Output Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--output` | `-o` | PATH | stdout | Write output to file |
| `--pretty` | | flag | False | Pretty print JSON with indentation |
| `--compact` | | flag | False | Output one signal per line |

### Logging Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--verbose` | `-v` | count | 0 | Increase verbosity (-v, -vv) |
| `--quiet` | `-q` | flag | False | Suppress all output except signals |

### Utility Options

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--validate-config` | Validate configuration and exit |
| `--help` | Show help message and exit |

---

## Output Formats

### Standard JSON Output

Default output is a single JSON object with execution metadata and signals:

```json
{
  "execution_id": "EXEC_20250516_123456_abc123",
  "timestamp": "2025-05-16T12:34:56Z",
  "execution_duration_seconds": 45.2,
  "assets_analyzed": 5,
  "signals_generated": 3,
  "selected_assets": [
    {
      "symbol": "BTCUSDT",
      "rank": 1,
      "activity_score": 0.85,
      "primary_driver": "WHALE_ACTIVITY"
    }
  ],
  "signals": [...],
  "metadata": {
    "config_file": "config.yaml",
    "api_calls_made": 42,
    "data_freshness_seconds": 1.5,
    "errors": []
  }
}
```

### Pretty Print Mode

```bash
python -m binance_signal_generator --pretty
```

Outputs formatted JSON with 2-space indentation for readability.

### Compact Mode

```bash
python -m binance_signal_generator --compact
```

Outputs one signal per line, suitable for log processing or streaming:

```json
{"signal_id": "SIG_001", "symbol": "BTCUSDT", ...}
{"signal_id": "SIG_002", "symbol": "ETHUSDT", ...}
```

### File Output

```bash
python -m binance_signal_generator --output signals.json --pretty
```

Writes output to specified file instead of stdout.

---

## Configuration

### Configuration File

The CLI requires a YAML configuration file. Use `config.example.yaml` as a template:

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
| `pipeline` | Pipeline timeout and execution settings |
| `whale` | Whale detection thresholds |
| `walls` | Wall detection parameters |
| `analysis` | IV, PCR, OI, Max Pain analysis settings |
| `validation` | Futures validation rules |
| `output` | Signal output and filtering |
| `logging` | Logging configuration |

### Validate Configuration

```bash
# Validate configuration without running pipeline
python -m binance_signal_generator --config config.yaml --validate-config

# Success output:
# Configuration is valid

# Failure output (to stderr):
# Configuration validation failed: <error message>
```

---

## Environment Variables

### Required Variables

```bash
# Binance API credentials
export BINANCE_API_KEY="your-api-key"
export BINANCE_API_SECRET="your-api-secret"
```

### Optional Variables

```bash
# Use testnet
export BINANCE_USE_TESTNET="true"

# Custom config path
export BINANCE_SIGNALS_CONFIG="/path/to/config.yaml"

# Log level override
export LOG_LEVEL="DEBUG"
```

### Using Environment Variables in Config

The configuration file supports environment variable substitution:

```yaml
binance:
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
  testnet: ${BINANCE_USE_TESTNET:-false}
```

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

### Run Specific Test Files

```bash
# Configuration tests
pytest tests/unit/test_config.py -v

# Data fetcher tests
pytest tests/unit/test_data.py -v

# Analysis tests
pytest tests/unit/test_analysis.py -v

# Whale detection tests
pytest tests/unit/test_whale.py -v

# Wall detection tests
pytest tests/unit/test_wall.py -v

# Pipeline tests
pytest tests/unit/test_pipeline.py -v
```

### Run Specific Test Classes

```bash
# Run specific test class
pytest tests/unit/test_analysis.py::TestIVAnalyzer -v

# Run specific test method
pytest tests/unit/test_whale.py::TestWhaleDetector::test_detect_whale_trade -v
```

### Run with Markers

```bash
# Run only async tests
pytest tests/ -m asyncio

# Run only integration tests (if marked)
pytest tests/ -m integration

# Skip slow tests
pytest tests/ -m "not slow"
```

### Coverage Report

```bash
# Generate coverage report
pytest tests/ --cov=binance_signal_generator --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ --cov=binance_signal_generator --cov-report=html
open htmlcov/index.html  # View report
```

### Test Configuration

Tests use `pytest.ini` or `pyproject.toml` configuration:

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"
markers = [
    "asyncio: async tests",
    "integration: integration tests",
    "slow: slow running tests",
]
```

---

## Common Workflows

### 1. Daily Signal Generation

```bash
# Generate signals with default settings
python -m binance_signal_generator --config config.yaml --output signals_$(date +%Y%m%d).json
```

### 2. Monitor Specific Assets

```bash
# Monitor BTC and ETH only
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT --pretty
```

### 3. Development/Testing Mode

```bash
# Dry run with verbose output
python -m binance_signal_generator --config config.yaml --dry-run -vv --pretty
```

### 4. Integration with External Systems

```bash
# Pipe output to external notification system
python -m binance_signal_generator | python notify.py

# Write to file for processing
python -m binance_signal_generator --output signals.json
python process_signals.py signals.json
```

### 5. Scheduled Execution (Cron)

```cron
# Run every 4 hours
0 */4 * * * cd /path/to/project && ./venv/bin/python -m binance_signal_generator --config config.yaml --output /var/log/signals/$(date +\%Y\%m\%d_\%H\%M\%S).json 2>> /var/log/signal_generator.log
```

### 6. Quick Signal Check

```bash
# Quick check with minimal output
python -m binance_signal_generator -q --top-n 3
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Config file not found` | Missing config.yaml | Create config from example |
| `Invalid API credentials` | Wrong API key/secret | Check environment variables |
| `Rate limit exceeded` | Too many API requests | Reduce request frequency |
| `No assets selected` | No assets met criteria | Lower `min_activity_score` |
| `Pipeline timeout` | Execution too slow | Increase timeout in config |

### Error Output

Errors are written to stderr, while signals go to stdout:

```bash
# Capture signals to file, errors to log
python -m binance_signal_generator > signals.json 2> errors.log
```

### Debugging

```bash
# Enable debug logging
python -m binance_signal_generator -vv --dry-run

# Shows:
# - API calls made
# - Asset selection process
# - Analysis details
# - Signal generation steps
```

---

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | Pipeline completed with signals generated |
| 1 | Error | Configuration error, API error, or no signals generated |
| 130 | Interrupted | User interrupted with Ctrl+C |

### Using Exit Codes in Scripts

```bash
#!/bin/bash
python -m binance_signal_generator --config config.yaml
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo "Signals generated successfully"
elif [ $exit_code -eq 130 ]; then
    echo "Interrupted by user"
else
    echo "Error occurred (exit code: $exit_code)"
fi
```

---

## Examples

### Example 1: Basic Signal Generation

```bash
# Generate signals for top 5 assets
python -m binance_signal_generator --config config.yaml

# Output:
# {"execution_id": "EXEC_20250516_120000_abc123", ...}
```

### Example 2: Analyze Specific Symbols

```bash
# Analyze BTC, ETH, and SOL
python -m binance_signal_generator --symbols BTCUSDT ETHUSDT SOLUSDT --pretty

# Output:
# {
#   "execution_id": "EXEC_20250516_120000_def456",
#   "signals": [
#     {
#       "signal_id": "SIG_20250516_120000_BTCUSDT",
#       "symbol": "BTCUSDT",
#       "direction": "LONG",
#       "confidence_score": 0.78,
#       ...
#     }
#   ]
# }
```

### Example 3: Development Mode

```bash
# Full debug output, no database writes
python -m binance_signal_generator --config config.yaml --dry-run -vv --pretty

# Shows detailed execution:
# [DEBUG] Initializing pipeline orchestrator
# [DEBUG] Fetching available underlyings
# [DEBUG] Found 25 underlyings
# [DEBUG] Scanning activity for BTCUSDT...
# ...
```

### Example 4: Filter by Confidence

```bash
# Only output signals with >= 70% confidence
python -m binance_signal_generator --min-confidence 0.70 --pretty
```

### Example 5: Adjust Asset Count

```bash
# Analyze top 10 assets instead of default 5
python -m binance_signal_generator --top-n 10
```

### Example 6: Integration Script

```bash
#!/bin/bash
# run_signals.sh - Daily signal generation script

CONFIG_FILE="/app/config.yaml"
OUTPUT_DIR="/app/output"
DATE=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/signals_${DATE}.json"
LOG_FILE="/app/logs/signals.log"

# Create directories
mkdir -p "${OUTPUT_DIR}" /app/logs

# Run signal generator
echo "$(date): Starting signal generation" >> "${LOG_FILE}"
python -m binance_signal_generator \
    --config "${CONFIG_FILE}" \
    --output "${OUTPUT_FILE}" \
    --top-n 5 \
    --min-confidence 0.60 \
    2>> "${LOG_FILE}"

exit_code=$?

if [ ${exit_code} -eq 0 ]; then
    echo "$(date): Successfully generated signals to ${OUTPUT_FILE}" >> "${LOG_FILE}"
    # Process signals with external system
    python /app/process_signals.py "${OUTPUT_FILE}"
else
    echo "$(date): Signal generation failed with exit code ${exit_code}" >> "${LOG_FILE}"
fi

exit ${exit_code}
```

### Example 7: Real-time Monitoring

```bash
# Watch mode - run every 15 minutes
watch -n 900 'python -m binance_signal_generator -q --top-n 3'
```

---

## Signal Output Schema

Each generated signal contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | string | Unique identifier (SIG_YYYYMMDD_HHMMSS_SYMBOL) |
| `timestamp` | string | ISO 8601 timestamp |
| `symbol` | string | Trading pair (e.g., BTCUSDT) |
| `direction` | enum | LONG, SHORT, or NEUTRAL |
| `confidence_score` | float | Signal confidence (0.0-1.0) |
| `signal_strength` | enum | WEAK, MODERATE, STRONG, VERY_STRONG |
| `entry_zone` | object | Entry price range (min, max, ideal) |
| `stop_loss` | object | Stop loss price and type |
| `take_profit_levels` | array | Up to 3 TP levels with ratios |
| `support_levels` | array | Support levels from put walls |
| `resistance_levels` | array | Resistance levels from call walls |
| `whale_metrics` | object | Whale activity analysis |
| `options_metrics` | object | Options market metrics |
| `futures_metrics` | object | Futures market data |
| `risk_reward_ratio` | float | Calculated R:R ratio |

---

## Pipeline Stages

The CLI executes a 6-stage pipeline:

| Stage | Name | Description |
|-------|------|-------------|
| 1 | Activity Scan | Scan all assets for activity scores |
| 2 | Asset Selection | Select top N assets by activity |
| 3 | Data Fetching | Fetch Options and Futures data |
| 4 | Analysis | Run IV, PCR, OI, Max Pain analysis |
| 5 | Whale/Wall Detection | Detect whale activity and OI walls |
| 6 | Signal Generation | Create and output trading signals |

---

## Troubleshooting

### Issue: No Signals Generated

**Symptoms:** Pipeline runs but outputs empty signals list

**Possible causes:**
1. No assets met minimum activity score
2. All signals below minimum confidence threshold
3. Missing or incomplete market data

**Solutions:**
```bash
# Lower activity threshold
# In config.yaml:
# ranking.min_activity_score: 0.20

# Lower confidence threshold
python -m binance_signal_generator --min-confidence 0.40

# Check with verbose output
python -m binance_signal_generator -vv
```

### Issue: API Rate Limits

**Symptoms:** Errors about rate limiting

**Solutions:**
```bash
# Reduce rate in config.yaml:
# binance.rate_limit.requests_per_second: 5

# Or wait and retry
python -m binance_signal_generator --config config.yaml
```

### Issue: Connection Timeout

**Symptoms:** Connection errors or timeouts

**Solutions:**
```bash
# Increase timeout in config.yaml:
# binance.timeout.connect_seconds: 30
# binance.timeout.read_seconds: 60
```

---

## Support

For issues and feature requests, please refer to:
- Project documentation in `docs/`
- Configuration guide: `docs/CONFIGURATION.md`
- Architecture overview: `docs/ARCHITECTURE.md`
- Development guide: `docs/DEVELOPMENT.md`

---

*Last Updated: 2025-05-16*
