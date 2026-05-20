# Configurable Keys from Project

This document extracts all configurable keys from the `binance_signal_generator` module, organized by file name.

---

## 1. analysis/iv_analyzer.py

### IVConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `iv_high_threshold` | float | 0.75 | 75th percentile threshold for high IV |
| `iv_low_threshold` | float | 0.25 | 25th percentile threshold for low IV |
| `iv_high_value` | float | 0.80 | 80% annualized - high IV value threshold |
| `iv_low_value` | float | 0.30 | 30% annualized - low IV value threshold |
| `atm_range_pct` | float | 5.0 | 5% from spot for ATM range |
| `min_strikes` | int | 3 | Minimum strikes for valid analysis |

### Internal Variables

| Key | Default Value | Description |
|-----|---------------|-------------|
| `_iv_history_max` | 30 | Max IV observations to keep for rolling percentile |

---

## 2. analysis/pcr_analyzer.py

### PCRConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `pcr_high_threshold` | float | 1.2 | Put-heavy threshold |
| `pcr_low_threshold` | float | 0.8 | Call-heavy threshold |
| `pcr_extreme_high` | float | 1.5 | Very put-heavy threshold |
| `pcr_extreme_low` | float | 0.5 | Very call-heavy threshold |
| `volume_weight` | float | 0.4 | 40% weight for notional PCR |
| `min_total_oi` | int | 100 | Minimum OI for valid analysis |

---

## 3. analysis/oi_analyzer.py

### OIConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `high_oi_concentration` | float | 0.04 | 4% of total OI at one strike (crypto-optimized) |
| `significant_oi_change` | float | 0.20 | 20% change is significant |
| `max_strikes_to_analyze` | int | 50 | Maximum strikes to analyze |
| `min_total_oi` | int | 100 | Minimum total OI |

### Signal Generation Constants

| Key | Value | Description |
|-----|-------|-------------|
| `trend_threshold` | 0.15 | Conservative threshold for crypto trend detection |

---

## 4. analysis/max_pain.py

### MaxPainConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `distance_threshold` | float | 3.0 | 3% from max pain for signal |
| `expiry_weight_factor` | float | 1.0 | Weight by days to expiry |
| `min_strikes` | int | 3 | Minimum strikes for calculation |

---

## 5. analysis/wall_detector.py

### WallDetectorConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `min_oi_concentration` | float | 0.002 | 0.2% of total OI (lowered from 0.5%) |
| `major_wall_concentration` | float | 0.01 | 1% of total OI (lowered from 2%) |
| `max_wall_distance` | float | 15.0 | 15% from spot |
| `min_absolute_oi` | int | 10 | Minimum absolute OI for wall detection |

---

## 6. analysis/gamma_exposure.py

### GammaExposureConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `significant_level_threshold` | float | 0.05 | 5% of total absolute GEX |
| `min_oi_threshold` | int | 10 | Minimum OI to consider |
| `flip_search_range` | float | 0.30 | ±30% from spot for flip detection |
| `use_simplified_delta` | bool | True | Use simplified delta approximation |
| `dte_reference_days` | float | 7.0 | Reference DTE for normalization |
| `max_dte_weight` | float | 3.0 | Maximum DTE weight |
| `min_dte_weight` | float | 0.3 | Minimum DTE weight |
| `enable_dte_weighting` | bool | True | Enable DTE weighting |

### DELTA_APPROX Dictionary

| Key | Value | Description |
|-----|-------|-------------|
| `deep_otm` | 0.05 | < 0.7 delta moneyness |
| `otm` | 0.15 | 0.7-0.85 delta moneyness |
| `near_atm` | 0.50 | 0.85-1.15 delta moneyness |
| `itm` | 0.70 | 1.15-1.30 delta moneyness |
| `deep_itm` | 0.90 | > 1.30 delta moneyness |

---

## 7. analysis/sentiment.py

### SentimentConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `ls_ratio_extreme_high` | float | 2.0 | > 2.0 = extreme bullish (contrarian short) |
| `ls_ratio_extreme_low` | float | 0.5 | < 0.5 = extreme bearish (contrarian long) |
| `ls_ratio_bullish` | float | 1.2 | > 1.2 = bullish |
| `ls_ratio_bearish` | float | 0.8 | < 0.8 = bearish |
| `funding_extreme_high` | float | 0.0005 | > 0.05% = extremely long |
| `funding_extreme_low` | float | -0.0005 | < -0.05% = extremely short |
| `funding_bullish` | float | 0.0001 | > 0.01% = long bias |
| `funding_bearish` | float | -0.0001 | < -0.01% = short bias |
| `ls_ratio_lookback_periods` | int | 5 | Periods to analyze trend |
| `funding_rate_lookback_hours` | int | 168 | 7 days for average |
| `top_trader_position_weight` | float | 0.35 | Weight for top trader position ratio |
| `top_trader_account_weight` | float | 0.25 | Weight for top trader account ratio |
| `funding_rate_weight` | float | 0.40 | Weight for funding rate |
| `use_contrarian_signals` | bool | True | Enable contrarian mode |
| `contrarian_extreme_threshold` | float | 3.0 | L/S ratio > 3.0 = strong contrarian |

---

## 8. analysis/signal_scorer.py

### SignalScorerConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `iv_weight` | float | 0.15 | IV analysis weight |
| `pcr_weight` | float | 0.18 | PCR analysis weight |
| `oi_weight` | float | 0.15 | OI analysis weight |
| `max_pain_weight` | float | 0.10 | Max Pain magnet weight |
| `sentiment_weight` | float | 0.16 | Sentiment (L/S + funding) weight |
| `gamma_weight` | float | 0.10 | Gamma exposure weight |
| `oi_flow_weight` | float | 0.12 | OI flow direction - PRIMARY signal |
| `wall_concentration_weight` | float | 0.04 | Wall concentration weight |
| `pcr_strike_alignment_weight` | float | 0.08 | PCR strike alignment weight |
| `whale_flow_weight` | float | 0.05 | Whale money flow weight |
| `min_confidence` | float | 0.4 | Minimum confidence for valid signal |
| `agreement_threshold` | float | 0.6 | % of signals agreeing |
| `iv_high_value` | float | 0.80 | 80% annualized = HIGH |
| `iv_low_value` | float | 0.40 | 40% annualized = LOW |

---

## 9. config/loader.py

### BinanceConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `api_key` | str | "" | Binance API key |
| `api_secret` | str | "" | Binance API secret |
| `testnet` | bool | False | Use testnet environment |
| `rate_limit_requests_per_second` | int | 10 | Rate limit requests per second |
| `rate_limit_burst` | int | 20 | Rate limit burst |
| `timeout_connect_seconds` | int | 10 | Connection timeout |
| `timeout_read_seconds` | int | 30 | Read timeout |

### RankingConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `top_assets_count` | int | 5 | Number of top assets |
| `min_activity_score` | float | 0.30 | Minimum activity score |
| `weight_oi_change` | float | 0.25 | OI change weight |
| `weight_volume_spike` | float | 0.20 | Volume spike weight |
| `weight_iv_interest` | float | 0.15 | IV interest weight |
| `weight_pcr_extreme` | float | 0.15 | PCR extreme weight |
| `weight_whale_activity` | float | 0.15 | Whale activity weight |
| `weight_total_volume` | float | 0.10 | Total volume weight |
| `oi_change_max_pct` | float | 20.0 | Max OI change % for normalization |
| `volume_spike_max` | float | 5.0 | Max volume spike multiplier |
| `total_volume_max` | float | 100_000_000 | Max total volume in USD |
| `min_options_volume` | float | 100_000 | $100K minimum options volume |
| `min_active_strikes` | int | 5 | Minimum active strikes |
| `excluded_symbols` | list | [] | List of excluded symbols |

### PipelineConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `timeout_total_seconds` | int | 600 | Total pipeline timeout |
| `timeout_activity_scan_seconds` | int | 30 | Activity scan timeout |
| `timeout_asset_selection_seconds` | int | 10 | Asset selection timeout |
| `timeout_data_fetch_seconds` | int | 120 | Data fetch timeout |
| `timeout_analysis_seconds` | int | 180 | Analysis timeout |
| `timeout_whale_wall_seconds` | int | 60 | Whale/wall detection timeout |
| `timeout_signal_output_seconds` | int | 60 | Signal output timeout |

### IntradayConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `enabled` | bool | True | Enable intraday mode |
| `oi_period` | str | "15m" | OI period for intraday |
| `oi_limit` | int | 96 | 24 hours of 15-min data |
| `volume_interval` | str | "15m" | Volume spike detection interval |
| `volume_limit` | int | 48 | 12 hours for avg comparison |
| `kline_interval` | str | "15m" | Kline interval |
| `kline_limit` | int | 48 | 12 hours of candles |
| `scoring_mode` | str | "intraday" | Scoring mode |
| `execution_interval_minutes` | int | 15 | Execution interval |

### WhaleConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `min_premium` | float | 100_000 | Default whale premium threshold |
| `block_threshold` | float | 500_000 | Default block trade threshold |
| `lookback_hours` | int | 24 | Lookback period for whale analysis |
| `confidence_boost_enabled` | bool | True | Enable confidence boost |
| `confidence_boost_max` | float | 0.15 | Maximum confidence boost |
| `confidence_boost_net_volume_threshold` | float | 20_000_000 | Net volume threshold for boost |
| `asset_thresholds` | Dict | {} | Asset-specific thresholds |

### WallsConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `min_oi_percentage` | float | 0.15 | Minimum OI percentage |
| `major_threshold` | float | 0.25 | Major wall threshold |
| `max_levels` | int | 3 | Maximum levels |
| `strength_distance_factor` | float | 0.30 | Distance factor for strength |
| `strength_oi_factor` | float | 0.70 | OI factor for strength |

### AnalysisConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `iv_enabled` | bool | True | Enable IV analysis |
| `iv_weight` | float | 0.20 | IV analysis weight |
| `iv_lookback_days` | int | 30 | IV lookback period |
| `iv_threshold_high` | float | 0.75 | High IV threshold |
| `iv_threshold_low` | float | 0.25 | Low IV threshold |
| `pcr_enabled` | bool | True | Enable PCR analysis |
| `pcr_weight` | float | 0.25 | PCR analysis weight |
| `pcr_threshold_put_high` | float | 1.2 | Put high threshold |
| `pcr_threshold_call_high` | float | 0.8 | Call high threshold |
| `pcr_volume_weight` | float | 0.6 | Volume weight for PCR |
| `pcr_oi_weight` | float | 0.4 | OI weight for PCR |
| `oi_enabled` | bool | True | Enable OI analysis |
| `oi_weight` | float | 0.20 | OI analysis weight |
| `oi_concentration_threshold` | float | 0.15 | OI concentration threshold |
| `max_pain_enabled` | bool | True | Enable Max Pain |
| `max_pain_weight` | float | 0.15 | Max Pain weight |
| `max_pain_distance_threshold` | float | 2.0 | Distance threshold |

### ValidationConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `liquidity_enabled` | bool | True | Enable liquidity check |
| `liquidity_min_24h_volume` | float | 1_000_000 | Minimum 24h volume |
| `trend_enabled` | bool | True | Enable trend check |
| `trend_ema_fast` | int | 9 | Fast EMA period |
| `trend_ema_slow` | int | 21 | Slow EMA period |
| `trend_require_alignment` | bool | True | Require trend alignment |
| `volatility_enabled` | bool | True | Enable volatility check |
| `volatility_atr_period` | int | 14 | ATR period |
| `volatility_extreme_multiplier` | float | 3.0 | Extreme volatility multiplier |
| `funding_enabled` | bool | True | Enable funding check |
| `funding_max_absolute_rate` | float | 0.001 | Max absolute funding rate |

### OutputConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `json_enabled` | bool | True | Enable JSON output |
| `json_pretty_print` | bool | False | Pretty print JSON |
| `json_include_metadata` | bool | True | Include metadata |
| `json_include_selected_assets` | bool | True | Include selected assets |
| `min_confidence` | float | 0.55 | Minimum signal confidence |
| `max_per_asset` | int | 1 | Max signals per asset |
| `max_per_execution` | int | 5 | Max signals per execution |
| `min_risk_reward` | float | 1.5 | Minimum risk/reward ratio |
| `sr_max_levels` | int | 3 | Max S/R levels |
| `sr_include_max_pain` | bool | True | Include max pain in S/R |
| `sr_min_wall_strength` | float | 0.50 | Min wall strength for S/R |
| `stop_loss_method` | str | "wall" | Stop loss method |
| `stop_loss_buffer_pct` | float | 0.2 | Stop loss buffer |
| `stop_loss_min_distance_pct` | float | 0.5 | Min SL distance |
| `stop_loss_max_distance_pct` | float | 3.0 | Max SL distance |
| `take_profit_levels` | int | 3 | Number of TP levels |
| `take_profit_ratio_1` | float | 0.5 | TP level 1 ratio |
| `take_profit_ratio_2` | float | 0.3 | TP level 2 ratio |
| `take_profit_ratio_3` | float | 0.2 | TP level 3 ratio |
| `database_enabled` | bool | True | Enable database |
| `database_path` | str | "./data/signals.db" | Database path |
| `database_rotation` | str | "weekly" | Database rotation |
| `database_retention_weeks` | int | 4 | Database retention |

### LoggingConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `level` | str | "INFO" | Log level |
| `format` | str | "json" | Log format |
| `file_enabled` | bool | True | Enable file logging |
| `file_path` | str | "./logs/signal_generator.log" | Log file path |
| `file_max_size_mb` | int | 10 | Max file size |
| `file_backup_count` | int | 5 | Backup count |
| `console_enabled` | bool | False | Enable console logging |
| `console_colorize` | bool | False | Colorize console output |
| `mask_sensitive` | bool | True | Mask sensitive data |

---

## 10. pipeline/orchestrator.py

### PipelineConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `timeout_seconds` | int | 600 | Total timeout |
| `activity_scan_timeout` | int | 60 | Activity scan timeout |
| `data_fetch_timeout` | int | 180 | Data fetch timeout |
| `analysis_timeout` | int | 180 | Analysis timeout |
| `top_n_assets` | int | 5 | Number of top assets |
| `min_activity_score` | float | 0.30 | Minimum activity score |
| `min_signal_confidence` | float | 0.50 | Minimum signal confidence |
| `max_signals_per_run` | int | 5 | Max signals per run |
| `output_to_stdout` | bool | True | Output to stdout |
| `save_to_database` | bool | False | Save to database |

### OI Flow Thresholds

| Key | Value | Description |
|-----|-------|-------------|
| `oi_threshold` | 2.0 | ±2% for daily OI flow detection |
| `oi_threshold` (intraday) | 1.0 | ±1% for intraday OI flow detection |

---

## 11. ranking/activity_scorer.py

### ActivityScorer DEFAULT_WEIGHTS

| ActivityDriver | Weight | Description |
|----------------|--------|-------------|
| OI_CHANGE | 0.25 | Open Interest change weight |
| VOLUME_SPIKE | 0.20 | Volume spike weight |
| IV_INTEREST | 0.15 | IV interest weight |
| PCR_EXTREME | 0.15 | PCR extreme weight |
| WHALE_ACTIVITY | 0.15 | Whale activity weight |
| TOTAL_VOLUME | 0.10 | Total volume weight |

### ActivityScorer Parameters

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `oi_change_max` | float | 20.0 | Max OI change % for normalization |
| `volume_spike_max` | float | 5.0 | Max volume spike multiplier |
| `total_volume_max` | float | 10_000_000 | $10M max total volume |

---

## 12. ranking/asset_selector.py

### SelectionConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `top_n` | int | 5 | Number of assets to select |
| `min_activity_score` | float | 0.15 | Minimum activity score (lowered from 0.30) |
| `min_options_volume` | float | 100_000 | $100K minimum options volume |
| `min_active_strikes` | int | 5 | Minimum active strikes |
| `excluded_symbols` | Set[str] | None | Set of excluded symbols |

---

## 13. whale/whale_detector.py

### AssetWhaleThreshold

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `min_premium` | float | 100_000 | Minimum premium for whale |
| `block_threshold` | float | 500_000 | Block trade threshold |

### WhaleDetectorConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `min_premium` | float | 100_000 | $100k for regular whale |
| `block_threshold` | float | 500_000 | $500k for block trade |
| `lookback_hours` | int | 24 | Lookback period |
| `min_trades_for_analysis` | int | 3 | Minimum trades for analysis |
| `bullish_threshold` | float | 0.3 | 30% net bullish = bullish |
| `bearish_threshold` | float | -0.3 | 30% net bearish = bearish |
| `asset_thresholds` | Dict | {} | Asset-specific thresholds |

---

## 14. whale/volume_analyzer.py

### VolumeAnalyzerConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `time_buckets` | int | 4 | Divide lookback into 4 buckets |
| `high_concentration_threshold` | float | 0.3 | 30% at one strike |

---

## 15. output/sr_levels.py

### SRLevelConfig

| Key | Type | Default Value | Description |
|-----|------|---------------|-------------|
| `max_support_levels` | int | 3 | Max support levels |
| `max_resistance_levels` | int | 3 | Max resistance levels |
| `min_level_distance_pct` | float | 1.0 | Minimum distance between levels (%) |
| `wall_weight` | float | 0.50 | Wall weight factor |
| `max_pain_weight` | float | 0.30 | Max pain weight factor |
| `volume_weight` | float | 0.20 | Volume weight factor |
| `default_sl_distance_pct` | float | 2.0 | Default SL distance |
| `default_tp_ratios` | List[float] | [1.5, 3.0, 5.0] | Default TP RR ratios |

---

## 16. data/options_fetcher.py

### Rate Limiter Defaults

| Key | Value | Description |
|-----|-------|-------------|
| `requests_per_second` | 10.0 | Default rate limit |
| `burst` | 20 | Default burst |

### Cache Expiry Times

| Key | Value | Description |
|-----|-------|-------------|
| Exchange info cache | 3600s | 1 hour |
| Tickers cache | 30s | 30 seconds |
| Mark prices cache | 30s | 30 seconds |
| Block trades cache | 30s | 30 seconds |

---

## 17. data/futures_fetcher.py

### Rate Limiter Defaults

| Key | Value | Description |
|-----|-------|-------------|
| `requests_per_second` | 20.0 | Higher rate limit for Futures API |
| `burst` | 40 | Higher burst for Futures API |

---

## Summary of Total Configurable Keys

| Module | Config Class | Key Count |
|--------|--------------|-----------|
| analysis/iv_analyzer.py | IVConfig | 6 |
| analysis/pcr_analyzer.py | PCRConfig | 6 |
| analysis/oi_analyzer.py | OIConfig | 4 |
| analysis/max_pain.py | MaxPainConfig | 3 |
| analysis/wall_detector.py | WallDetectorConfig | 4 |
| analysis/gamma_exposure.py | GammaExposureConfig | 7 |
| analysis/sentiment.py | SentimentConfig | 15 |
| analysis/signal_scorer.py | SignalScorerConfig | 13 |
| config/loader.py | BinanceConfig | 7 |
| config/loader.py | RankingConfig | 13 |
| config/loader.py | PipelineConfig | 7 |
| config/loader.py | IntradayConfig | 8 |
| config/loader.py | WhaleConfig | 7 |
| config/loader.py | WallsConfig | 5 |
| config/loader.py | AnalysisConfig | 17 |
| config/loader.py | ValidationConfig | 11 |
| config/loader.py | OutputConfig | 23 |
| config/loader.py | LoggingConfig | 9 |
| pipeline/orchestrator.py | PipelineConfig | 9 |
| ranking/activity_scorer.py | (weights + params) | 9 |
| ranking/asset_selector.py | SelectionConfig | 5 |
| whale/whale_detector.py | WhaleDetectorConfig | 7 |
| whale/volume_analyzer.py | VolumeAnalyzerConfig | 2 |
| output/sr_levels.py | SRLevelConfig | 8 |

**Total: ~190+ configurable keys across the project**
