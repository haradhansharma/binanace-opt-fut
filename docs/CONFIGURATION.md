# Configuration Guide

## Configuration Overview

The signal generator uses **YAML-based configuration** for full customization. Configuration is organized into sections for adaptive asset selection, whale detection, wall analysis, sentiment analysis, gamma exposure, and intraday trading parameters.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   CONFIGURATION SECTIONS                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. binance         - API credentials and rate limiting            │
│  2. ranking         - Adaptive asset selection (TOP N)             │
│  3. pipeline        - Execution timeouts                           │
│  4. intraday        - Multi-timeframe support (NEW)                │
│  5. whale           - Whale detection with asset thresholds (NEW)  │
│  6. walls           - Options wall detection                       │
│  7. sentiment       - L/S ratios + funding analysis (NEW)          │
│  8. gamma_exposure  - GEX calculator settings (NEW)                │
│  9. analysis        - Options analysis (IV, PCR, OI, Max Pain)     │
│  10. validation     - Futures validation filters                   │
│  11. output         - Signal generation and JSON output            │
│  12. logging        - Logging configuration                        │
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
# Optimized for Intraday Trading with Sentiment & Gamma Analysis
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
# ADAPTIVE ASSET RANKING
# ============================================================
ranking:
  # Asset selection
  top_assets_count: 5            # Select top N assets by activity
  min_activity_score: 0.15       # Minimum score to be considered
  
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
  timeout:
    total_seconds: 600           # Total pipeline timeout
    activity_scan_seconds: 30    # Stage 1: Activity scan
    asset_selection_seconds: 10  # Stage 2: Asset selection
    data_fetch_seconds: 120      # Stage 3: Data fetch
    analysis_seconds: 180        # Stage 4: Analysis
    whale_wall_seconds: 60       # Stage 5: Whale + Wall detection
    signal_output_seconds: 60    # Stage 6: Signal output

# ============================================================
# INTRADAY MULTI-TIMEFRAME SUPPORT (NEW)
# ============================================================
intraday:
  enabled: true                  # Enable intraday mode
  
  # Timeframe settings
  oi_period: "15m"               # OI analysis period: 5m, 15m, 1h, 4h
  volume_interval: "15m"         # Volume analysis interval: 5m, 15m, 1h, 4h
  
  # Auto mode - selects timeframe based on volatility
  auto_mode: true                # Auto-select based on market conditions
  auto_thresholds:
    high_volatility: 3.0         # ATR% > 3% uses 5m
    medium_volatility: 1.5       # ATR% 1.5-3% uses 15m
    low_volatility: 1.5          # ATR% < 1.5% uses 1h

# ============================================================
# WHALE DETECTION WITH ASSET-SPECIFIC THRESHOLDS (NEW)
# ============================================================
whale:
  # Default thresholds (fallback for unspecified assets)
  min_premium: 100000            # $100k = whale trade threshold
  block_threshold: 500000        # $500k = block trade threshold
  lookback_hours: 24             # Hours to look back for whale activity
  
  # Asset-specific thresholds (NEW)
  asset_thresholds:
    BTCUSDT:
      min_premium: 500000        # $500k for BTC
      block_threshold: 2000000   # $2M block for BTC
    ETHUSDT:
      min_premium: 200000        # $200k for ETH
      block_threshold: 1000000   # $1M block for ETH
    SOLUSDT:
      min_premium: 100000
      block_threshold: 500000
    # Add more assets as needed
  
  # Confidence boost settings
  confidence_boost:
    enabled: true
    max_boost: 0.15              # Max 15% confidence boost
    net_volume_threshold: 20000000  # $20M net = max boost

# ============================================================
# WALL DETECTION
# ============================================================
walls:
  # Detection parameters
  min_oi_percentage: 0.005       # 0.5% of total OI = wall
  major_threshold: 0.02          # 2% = major wall
  max_levels: 3                  # Max S/R levels to output
  
  # Wall strength calculation
  strength:
    distance_factor: 0.30        # Weight for distance from spot
    oi_factor: 0.70              # Weight for OI concentration

# ============================================================
# SENTIMENT ANALYSIS (NEW)
# ============================================================
sentiment:
  enabled: true                  # Enable sentiment analysis
  
  # L/S Ratio thresholds
  ls_extreme_high: 2.0           # Ratio > 2.0 = extreme bullish
  ls_extreme_low: 0.5            # Ratio < 0.5 = extreme bearish
  
  # Contrarian signals
  use_contrarian: true           # Generate contrarian signals at extremes
  contrarian_threshold: 3.0      # Ratio > 3.0 = contrarian SHORT signal
  
  # Funding rate settings
  funding_extreme_threshold: 0.001  # 0.1% = extreme funding
  funding_lookback_days: 7       # Days of funding history
  
  # Sentiment scoring weights
  weights:
    position_ratio: 0.40         # Top trader position ratio weight
    account_ratio: 0.30          # Top trader account ratio weight
    funding_rate: 0.30           # Funding rate weight

# ============================================================
# GAMMA EXPOSURE (GEX) (NEW)
# ============================================================
gamma_exposure:
  enabled: true                  # Enable GEX calculation
  
  # Detection thresholds
  significant_threshold: 0.05    # Min gamma significance
  
  # S/R level integration
  include_in_sr: true            # Add gamma levels to S/R
  max_gamma_levels: 3            # Max gamma-based S/R levels
  
  # Risk scoring
  gamma_risk_levels:
    low: 10000000000             # GEX < $10B = low risk
    medium: 50000000000          # GEX < $50B = medium risk
    high: 100000000000           # GEX > $100B = high risk

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
# SIGNAL WEIGHTS (including sentiment)
# ============================================================
signal_weights:
  iv: 0.20
  pcr: 0.25
  oi: 0.20
  max_pain: 0.15
  sentiment: 0.20                # Sentiment weight (NEW)

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
    min_confidence: 0.30         # Min confidence to output
    max_per_asset: 1             # Max 1 signal per asset per execution
    max_per_execution: 5         # Max total signals (top 5 assets)
    min_risk_reward: 1.5         # Min R:R for intraday
  
  # ────────────────────────────────────────────────────────────
  # SUPPORT/RESISTANCE LEVELS
  # ────────────────────────────────────────────────────────────
  sr_levels:
    max_levels: 3                # Max S/R levels each side
    include_max_pain: true       # Include max pain as S/R
    include_gamma: true          # Include gamma levels (NEW)
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
```

---

## Key Parameter Explanations

### Intraday Multi-Timeframe Parameters

```yaml
intraday:
  oi_period: "15m"               # OI analysis timeframe
  volume_interval: "15m"         # Volume analysis timeframe
  auto_mode: true                # Auto-select based on volatility
```

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `oi_period` | 5m, 15m, 1h, 4h | Timeframe for OI change calculation |
| `volume_interval` | 5m, 15m, 1h, 4h | Timeframe for volume spike detection |
| `auto_mode` | true/false | Auto-select based on market conditions |

**Auto Mode Logic:**
- **High volatility** (ATR% > 3%): Uses 5m timeframe
- **Medium volatility** (ATR% 1.5-3%): Uses 15m timeframe
- **Low volatility** (ATR% < 1.5%): Uses 1h timeframe

### Asset-Specific Whale Thresholds

```yaml
whale:
  asset_thresholds:
    BTCUSDT:
      min_premium: 500000
      block_threshold: 2000000
    ETHUSDT:
      min_premium: 200000
      block_threshold: 1000000
```

| Asset | Min Premium | Block Threshold | Reason |
|-------|-------------|-----------------|--------|
| BTC | $500,000 | $2,000,000 | Higher notional values |
| ETH | $200,000 | $1,000,000 | Medium notional values |
| Others | $100,000 | $500,000 | Default threshold |

### Sentiment Analysis Parameters

```yaml
sentiment:
  ls_extreme_high: 2.0           # Ratio threshold
  use_contrarian: true           # Contrarian signals
  weights:
    position_ratio: 0.40
    account_ratio: 0.30
    funding_rate: 0.30
```

| Parameter | Purpose | Impact |
|-----------|---------|--------|
| `ls_extreme_high` | L/S ratio > 2.0 = extreme | Triggers contrarian signals |
| `ls_extreme_low` | L/S ratio < 0.5 = extreme | Triggers contrarian signals |
| `use_contrarian` | Generate contrarian signals | Fade extreme positioning |

**Sentiment Score Calculation:**
```
sentiment_score = (position_ratio_weight × normalized_position_ratio) +
                  (account_ratio_weight × normalized_account_ratio) +
                  (funding_rate_weight × normalized_funding_rate)
```

### Gamma Exposure Parameters

```yaml
gamma_exposure:
  enabled: true
  significant_threshold: 0.05
  include_in_sr: true
```

| Parameter | Purpose |
|-----------|---------|
| `significant_threshold` | Minimum gamma significance for S/R levels |
| `include_in_sr` | Add gamma flip levels to support/resistance |
| `gamma_risk_levels` | GEX thresholds for risk scoring |

---

## Configuration Profiles

### Aggressive Intraday Profile

```yaml
# config.intraday-aggressive.yaml

intraday:
  oi_period: "5m"
  volume_interval: "5m"
  auto_mode: false

ranking:
  top_assets_count: 5
  min_activity_score: 0.15

output:
  signals:
    min_confidence: 0.30
    min_risk_reward: 1.2

sentiment:
  use_contrarian: true
  contrarian_threshold: 2.5

stop_loss:
  max_distance_pct: 2.0
```

### Conservative Profile

```yaml
# config.conservative.yaml

intraday:
  oi_period: "1h"
  volume_interval: "1h"
  auto_mode: false

ranking:
  top_assets_count: 3
  min_activity_score: 0.35

output:
  signals:
    min_confidence: 0.60
    min_risk_reward: 2.5

sentiment:
  use_contrarian: false

stop_loss:
  max_distance_pct: 4.0
```

### Sentiment-Focused Profile

```yaml
# config.sentiment-focused.yaml

signal_weights:
  iv: 0.15
  pcr: 0.20
  oi: 0.15
  max_pain: 0.10
  sentiment: 0.40            # High sentiment weight

sentiment:
  ls_extreme_high: 1.5       # Lower threshold
  ls_extreme_low: 0.67       # Lower threshold
  use_contrarian: true
  contrarian_threshold: 2.0
  
  weights:
    position_ratio: 0.50
    account_ratio: 0.35
    funding_rate: 0.15
```

---

## Environment Variables

```bash
# Required - Binance API credentials
export BINANCE_API_KEY="your-api-key"
export BINANCE_API_SECRET="your-api-secret"

# Optional - Use testnet for development
export BINANCE_USE_TESTNET="false"

# Optional - Override config settings
export SIGNAL_GENERATOR_LOG_LEVEL="DEBUG"
```

> **Note**: Telegram tokens are NOT needed - notifications are handled externally.

## API Permissions Required

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
├── Sentiment weights sum to 1.0
├── min_confidence in [0, 1]
├── top_assets_count >= 1
├── min_premium > 0 for all assets
├── wall thresholds in (0, 1)
├── intraday timeframes valid
├── database path writable
└── log path writable
```

### Common Errors

```
ConfigurationError: Signal weights must sum to 1.0 (got 1.10)
ConfigurationError: Sentiment weights must sum to 1.0 (got 0.95)
ConfigurationError: Invalid oi_period '10m' (must be: 5m, 15m, 1h, 4h)
ConfigurationError: min_confidence must be between 0 and 1
```

---

## Best Practices

### 1. Intraday Optimization
```yaml
# For high-frequency intraday trading:
intraday:
  oi_period: "5m"
  volume_interval: "5m"
  auto_mode: true

output:
  signals:
    min_risk_reward: 1.5-2.0
  stop_loss:
    max_distance_pct: 2.0-3.0
```

### 2. Sentiment Integration
```yaml
# Balance sentiment with other signals:
signal_weights:
  sentiment: 0.20-0.30

sentiment:
  use_contrarian: true
  ls_extreme_high: 2.0-3.0
```

### 3. Asset-Specific Thresholds
```yaml
# Customize for your traded assets:
whale:
  asset_thresholds:
    BTCUSDT:
      min_premium: 500000   # Higher for BTC
    ETHUSDT:
      min_premium: 200000   # Medium for ETH
    SOLUSDT:
      min_premium: 100000   # Default
```

---

## Quick Reference

| Section | Key Parameter | Default |
|---------|---------------|---------|
| intraday | oi_period | 15m |
| intraday | volume_interval | 15m |
| sentiment | ls_extreme_high | 2.0 |
| sentiment | use_contrarian | true |
| gamma_exposure | include_in_sr | true |
| whale (BTC) | min_premium | $500,000 |
| whale (ETH) | min_premium | $200,000 |
| output.signals | min_confidence | 0.30 |
| output.stop_loss | max_distance_pct | 3.0% |
| output.take_profit | levels | 3 |
