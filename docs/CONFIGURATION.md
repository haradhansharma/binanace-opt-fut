# Configuration Guide

## Configuration Overview

The signal generator uses **YAML-based configuration** for full customization. Configuration is organized into sections for adaptive asset selection, whale detection, wall analysis, and intraday trading parameters.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   CONFIGURATION SECTIONS                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. binance         - API credentials and rate limiting            │
│  2. ranking         - Adaptive asset selection (TOP N)             │
│  3. pipeline        - Execution timeouts                           │
│  4. whale           - Whale detection parameters                   │
│  5. walls           - Options wall detection                       │
│  6. analysis        - Options analysis (IV, PCR, OI, Max Pain)     │
│  7. validation      - Futures validation filters                   │
│  8. output          - Signal generation and JSON output            │
│  9. logging         - Logging configuration                        │
│                                                                     │
│  NOTE: Scheduling (cronjob) and Notifications (Telegram) are       │
│        handled EXTERNALLY - not configured in this file            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Complete Configuration File

```yaml
# config.yaml - Complete Configuration
# ============================================================
# Binance Options-Driven Futures Signal Generator
# Optimized for Intraday Trading
# ============================================================

# ============================================================
# BINANCE API CONFIGURATION
# ============================================================
binance:
  # API credentials (use environment variables)
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
  
  # Rate limiting (respect Binance limits)
  rate_limit:
    requests_per_second: 10
    burst: 20
  
  # Timeouts
  timeout:
    connect_seconds: 10
    read_seconds: 30

# ============================================================
# ADAPTIVE ASSET RANKING (NEW)
# ============================================================
ranking:
  # Asset selection
  top_assets_count: 5            # Select top N assets by activity
  min_activity_score: 0.30       # Minimum score to be considered
  
  # Activity scoring weights
  scoring_weights:
    oi_change: 0.25              # OI momentum weight
    volume_spike: 0.20           # Volume spike weight
    iv_interest: 0.15            # IV percentile weight
    pcr_extreme: 0.15            # PCR extremeness weight
    whale_activity: 0.15         # Whale activity weight
    total_volume: 0.10           # Total volume weight
  
  # Thresholds for scoring
  thresholds:
    oi_change_max_pct: 20.0      # 20% OI change = max score
    volume_spike_max: 5.0        # 5x avg volume = max score
    total_volume_max: 100000000  # $100M volume = max score
  
  # Liquidity requirements for selection
  min_options_volume: 5000000    # Min $5M options volume
  min_active_strikes: 10         # Min strikes with OI
  
  # Exclusions
  excluded_symbols: []           # Symbols to never select

# ============================================================
# PIPELINE CONFIGURATION
# ============================================================
pipeline:
  # Timeouts (single execution)
  # Note: Scheduling is handled externally via cronjob
  timeout:
    total_seconds: 600           # Total pipeline timeout
    activity_scan_seconds: 30    # Stage 1: Activity scan
    asset_selection_seconds: 10  # Stage 2: Asset selection
    data_fetch_seconds: 120      # Stage 3: Data fetch
    analysis_seconds: 180        # Stage 4: Analysis
    whale_wall_seconds: 60       # Stage 5: Whale + Wall detection
    signal_output_seconds: 60    # Stage 6: Signal output

# ============================================================
# WHALE DETECTION (NEW)
# ============================================================
whale:
  # Thresholds
  min_premium: 100000            # $100k = whale trade threshold
  block_threshold: 500000        # $500k = block trade threshold
  lookback_hours: 24             # Hours to look back for whale activity
  
  # Confidence boost settings
  confidence_boost:
    enabled: true
    max_boost: 0.15              # Max 15% confidence boost
    net_volume_threshold: 20000000  # $20M net = max boost

# ============================================================
# WALL DETECTION (NEW)
# ============================================================
walls:
  # Detection parameters
  min_oi_percentage: 0.15        # 15% of total OI = wall
  major_threshold: 0.25          # 25% = major wall
  max_levels: 3                  # Max S/R levels to output
  
  # Wall strength calculation
  strength:
    distance_factor: 0.30        # Weight for distance from spot
    oi_factor: 0.70              # Weight for OI concentration
  
  # Gamma exposure (advanced)
  gamma_walls:
    enabled: false               # Not implemented yet

# ============================================================
# OPTIONS ANALYSIS
# ============================================================
analysis:
  # ────────────────────────────────────────────────────────────
  # IMPLIED VOLATILITY
  # ────────────────────────────────────────────────────────────
  iv:
    enabled: true
    weight: 0.20                 # Weight in final signal
    
    lookback_days: 30            # For IV rank calculation
    
    thresholds:
      high: 0.75                 # IV rank > 75% = high
      low: 0.25                  # IV rank < 25% = low
  
  # ────────────────────────────────────────────────────────────
  # PUT/CALL RATIO
  # ────────────────────────────────────────────────────────────
  pcr:
    enabled: true
    weight: 0.25                 # Weight in final signal
    
    thresholds:
      put_high: 1.2              # PCR > 1.2 = excessive puts
      call_high: 0.8             # PCR < 0.8 = excessive calls
    
    weighting:
      volume_weight: 0.6         # Volume PCR weight
      oi_weight: 0.4             # OI PCR weight
  
  # ────────────────────────────────────────────────────────────
  # OPEN INTEREST
  # ────────────────────────────────────────────────────────────
  oi:
    enabled: true
    weight: 0.20                 # Weight in final signal
    
    concentration_threshold: 0.15  # For wall detection
  
  # ────────────────────────────────────────────────────────────
  # MAX PAIN
  # ────────────────────────────────────────────────────────────
  max_pain:
    enabled: true
    weight: 0.15                 # Weight in final signal
    
    distance_threshold: 2.0      # % distance for signal strength

# ============================================================
# SIGNAL WEIGHTS (including whale)
# ============================================================
signal_weights:
  iv: 0.20
  pcr: 0.25
  oi: 0.20
  max_pain: 0.15
  whale: 0.20                    # Whale activity weight

# ============================================================
# FUTURES VALIDATION
# ============================================================
validation:
  # Liquidity
  liquidity:
    enabled: true
    min_24h_volume: 1000000      # Min $1M 24h volume
  
  # Trend
  trend:
    enabled: true
    ema_fast: 9
    ema_slow: 21
    require_alignment: true
  
  # Volatility
  volatility:
    enabled: true
    atr_period: 14
    extreme_multiplier: 3.0
  
  # Funding rate
  funding:
    enabled: true
    max_absolute_rate: 0.001     # 0.1%

# ============================================================
# SIGNAL OUTPUT (JSON + SQLite)
# ============================================================
output:
  # ────────────────────────────────────────────────────────────
  # JSON OUTPUT (Primary)
  # ────────────────────────────────────────────────────────────
  json:
    enabled: true                # Output JSON to stdout
    pretty_print: false          # Compact JSON (set true for debugging)
    include_metadata: true       # Include execution metadata
    include_selected_assets: true  # Include ranked assets list
  
  # ────────────────────────────────────────────────────────────
  # SIGNAL FILTERING
  # ────────────────────────────────────────────────────────────
  signals:
    min_confidence: 0.55         # Min confidence to output
    max_per_asset: 1             # Max 1 signal per asset per execution
    max_per_execution: 5         # Max total signals (top 5 assets)
    min_risk_reward: 1.5         # Min R:R for intraday
  
  # ────────────────────────────────────────────────────────────
  # SUPPORT/RESISTANCE LEVELS
  # ────────────────────────────────────────────────────────────
  sr_levels:
    max_levels: 3                # Max S/R levels each side
    include_max_pain: true       # Include max pain as S/R
    min_wall_strength: 0.50      # Min strength for S/R level
  
  # ────────────────────────────────────────────────────────────
  # STOP LOSS (WALL-BASED)
  # ────────────────────────────────────────────────────────────
  stop_loss:
    method: "wall"               # wall-based SL (intraday)
    
    wall_based:
      use_nearest_wall: true     # Use nearest wall for SL
      buffer_pct: 0.2            # Small buffer below/above wall
    
    min_distance_pct: 0.5        # Min 0.5% from entry
    max_distance_pct: 3.0        # Max 3% for intraday
  
  # ────────────────────────────────────────────────────────────
  # TAKE PROFIT (MULTI-LEVEL)
  # ────────────────────────────────────────────────────────────
  take_profit:
    levels: 3                    # 3 TP levels
    
    # Position split
    ratios:
      level_1: 0.5               # Close 50% at TP1
      level_2: 0.3               # Close 30% at TP2
      level_3: 0.2               # Close 20% at TP3
    
    # Based on walls
    wall_based:
      tp1: "nearest_wall"        # TP1 at nearest opposite wall
      tp2: "second_wall"         # TP2 at second wall
      tp3: "third_wall"          # TP3 at third wall
  
  # ────────────────────────────────────────────────────────────
  # DATABASE (Secondary - for historical analysis)
  # ────────────────────────────────────────────────────────────
  database:
    enabled: true                # Save signals to SQLite
    path: "./data/signals.db"
    rotation: "weekly"           # weekly or monthly
    retention_weeks: 4           # Keep 4 weeks of history

# ============================================================
# LOGGING
# ============================================================
logging:
  level: "INFO"
  format: "json"
  
  file:
    enabled: true
    path: "./logs/signal_generator.log"
    max_size_mb: 10
    backup_count: 5
  
  console:
    enabled: false               # Disable console logs (JSON to stdout)
    colorize: false
  
  mask_sensitive: true

# ============================================================
# NOTE: External Components
# ============================================================
# Scheduling: Handled externally via cronjob or task scheduler
# Example cronjob: */15 * * * * cd /path/to/project && python -m binance_signal_generator
#
# Notifications: Handled externally by reading JSON output
# You can pipe output to your notification system:
#   python -m binance_signal_generator | your_notification_script.sh
```

---

## Key Parameter Explanations

### Asset Ranking Parameters

```yaml
ranking:
  top_assets_count: 5            # Number of assets to analyze
  min_activity_score: 0.30       # Minimum activity to qualify
```

| Parameter | Purpose | Impact |
|-----------|---------|--------|
| `top_assets_count` | Number of assets for detailed analysis | More = more signals, more API calls |
| `min_activity_score` | Filter low-activity assets | Higher = fewer but better candidates |
| `scoring_weights` | Balance of activity factors | Adjust based on what matters most |

### Whale Detection Parameters

```yaml
whale:
  min_premium: 100000            # $100k threshold
  block_threshold: 500000        # $500k block trades
  lookback_hours: 24             # Analysis window
```

| Threshold | Trade Size | Classification |
|-----------|------------|----------------|
| `min_premium` | > $100,000 | Whale trade |
| `block_threshold` | > $500,000 | Block trade (major whale) |

### Wall Detection Parameters

```yaml
walls:
  min_oi_percentage: 0.15        # 15% = wall
  major_threshold: 0.25          # 25% = major wall
  max_levels: 3                  # 3 S/R levels
```

| Parameter | Effect |
|-----------|--------|
| `min_oi_percentage: 0.15` | Strike needs 15%+ OI to be a wall |
| `major_threshold: 0.25` | 25%+ OI = very strong wall |
| `max_levels: 3` | Output 3 support + 3 resistance levels |

### Intraday Signal Parameters

```yaml
output:
  signals:
    min_risk_reward: 1.5         # R:R for intraday
  stop_loss:
    max_distance_pct: 3.0        # Tight SL for intraday
```

| Setting | Intraday Value | Reason |
|---------|----------------|--------|
| `min_risk_reward` | 1.5 | Lower threshold for quick trades |
| `max_distance_pct` | 3.0 | Tighter stops for intraday |
| `take_profit.levels` | 3 | Multiple exits for partial profits |

---

## Configuration Profiles

### Aggressive Intraday Profile

```yaml
# config.intraday-aggressive.yaml

ranking:
  top_assets_count: 5
  min_activity_score: 0.25       # Lower = more candidates

output:
  signals:
    min_confidence: 0.50         # Lower threshold
    min_risk_reward: 1.2         # Accept lower R:R
  
  stop_loss:
    max_distance_pct: 2.5        # Tighter stops
  
  take_profit:
    levels: 2                    # Focus on quick exits
    ratios:
      level_1: 0.6               # Take more at TP1
      level_2: 0.4

whale:
  confidence_boost:
    max_boost: 0.20              # Higher whale influence
```

### Conservative Profile

```yaml
# config.conservative.yaml

ranking:
  top_assets_count: 3            # Fewer, higher quality
  min_activity_score: 0.45       # Higher threshold

output:
  signals:
    min_confidence: 0.70         # Higher bar
    min_risk_reward: 2.5         # Better R:R required
  
  stop_loss:
    max_distance_pct: 4.0        # Wider stops

whale:
  confidence_boost:
    max_boost: 0.10              # Lower whale influence

walls:
  min_oi_percentage: 0.20        # Only strong walls
```

### Whale-Focused Profile

```yaml
# config.whale-focused.yaml

ranking:
  scoring_weights:
    whale_activity: 0.35         # High whale weight
    oi_change: 0.20
    volume_spike: 0.15
    iv_interest: 0.10
    pcr_extreme: 0.10
    total_volume: 0.10

signal_weights:
  whale: 0.30                    # High whale signal weight

whale:
  min_premium: 50000             # Lower threshold
  confidence_boost:
    max_boost: 0.25              # Strong whale boost
```

---

## Environment Variables

```bash
# Required - Binance API credentials
export BINANCE_API_KEY="your-api-key"
export BINANCE_API_SECRET="your-api-secret"

# Optional - Use testnet for development
export BINANCE_USE_TESTNET="false"
```

> **Note**: Telegram tokens are NOT needed - notifications are handled externally.

## SDK Configuration

The project uses the **official Binance Connector Python SDK**. The SDK is configured through the config file and environment variables:

```yaml
binance:
  api_key: ${BINANCE_API_KEY}      # Loaded from environment
  api_secret: ${BINANCE_API_SECRET}
  testnet: false                    # Set to true for testnet
```

### SDK Modules Used

| Module | Purpose | API Endpoints |
|--------|---------|---------------|
| `binance.options` | Options data | `/eapi/v1/*` |
| `binance.um_futures` | USDT-M Futures | `/fapi/v1/*` |

### API Permissions Required

Ensure your API key has these permissions:
- ✅ **Enable Reading** - Required for all data fetching
- ✅ **Enable Futures** - Required for Futures data
- ✅ **Enable Options** - Required for Options data
- ❌ **Enable Withdrawals** - NOT needed (read-only)

---

## Validation Rules

The configuration is validated on startup:

```
Configuration Validation:
├── API credentials present
├── Ranking weights sum to 1.0
├── Signal weights sum to 1.0
├── min_confidence in [0, 1]
├── top_assets_count >= 1
├── min_premium > 0
├── wall thresholds in (0, 1)
├── database path writable
└── log path writable
```

### Common Errors

```
ConfigurationError: Signal weights must sum to 1.0 (got 1.10)
ConfigurationError: min_confidence must be between 0 and 1
ConfigurationError: top_assets_count must be at least 1
ConfigurationError: min_premium must be positive
```

---

## Best Practices

### 1. Intraday Optimization
```yaml
# For 15-minute intraday trading:
output:
  signals:
    min_risk_reward: 1.5-2.0    # Quick profits
  stop_loss:
    max_distance_pct: 2.0-3.0   # Tight stops
  take_profit:
    levels: 2-3                 # Scale out
```

### 2. Wall-Based S/R
```yaml
# Ensure walls are properly detected:
walls:
  min_oi_percentage: 0.15       # Not too aggressive
  max_levels: 3                 # Enough levels for TPs

output:
  stop_loss:
    method: "wall"              # Use walls for SL
    buffer_pct: 0.2             # Small buffer
```

### 3. Whale Activity
```yaml
# Balance whale influence:
signal_weights:
  whale: 0.15-0.25              # Significant but not dominant

whale:
  min_premium: 100000           # True whales only
  confidence_boost:
    max_boost: 0.15             # Reasonable boost
```

---

## Quick Reference

| Section | Key Parameter | Default |
|---------|---------------|---------|
| ranking | top_assets_count | 5 |
| whale | min_premium | $100,000 |
| walls | min_oi_percentage | 15% |
| output.signals | min_confidence | 0.55 |
| output.stop_loss | max_distance_pct | 3.0% |
| output.take_profit | levels | 3 |
