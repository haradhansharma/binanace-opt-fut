# Configuration Adjustment Needed — Single Source of Truth Analysis

## 1. Executive Summary

The codebase currently has **configuration scattered across 7+ different sources** with significant duplication, conflicting defaults, and a disconnect between the central config system (`config/config.yaml` + `config/loader.py`) and the per-module dataclass configs. The orchestrator in `pipeline/orchestrator.py` creates most module configs with **bare default constructors** (e.g., `SentimentConfig()`, `IVConfig()`) instead of feeding values from the loaded YAML config. This means most values in `config.yaml` are **silently ignored** at runtime.

---

## 2. Current Configuration Sources

| # | Source | Location | Format | Status |
|---|--------|----------|--------|--------|
| 1 | `config/config.example.yaml` | `/config/config.example.yaml` | YAML | **Primary intended source** — but many values never reach modules |
| 2 | `Config` dataclasses | `config/loader.py` (lines 117-346) | Python dataclasses | Central parsed config — **10 sub-configs** |
| 3 | Per-module configs | Each module file | Python dataclasses | **7 separate module-level configs** with their own defaults |
| 4 | `PipelineConfig` | `pipeline/orchestrator.py` (lines 58-78) | Python dataclass | Separate pipeline config — **duplicates** config.loader values |
| 5 | CLI default arguments | `cli.py` (lines 143-164) | argparse defaults | Hardcoded defaults that **override** config values |
| 6 | `pyproject.toml` | `/pyproject.toml` | TOML | Build/tool config only |
| 7 | Environment variables | `config/loader.py` (lines 67-113) | `${VAR}` in YAML | API keys only |

---

## 3. Detailed Conflict & Gap Analysis

### 3.1 SentimentConfig — NOT Connected to Central Config

**YAML section** (`config/config.example.yaml` lines 179-208):
```yaml
analysis:
  sentiment:
    enabled: true
    weight: 0.20
    ls_ratio_extreme_high: 2.0
    ls_ratio_extreme_low: 0.5
    ...
```

**Central config loader** (`config/loader.py`): The `AnalysisConfig` dataclass does **NOT** have any sentiment fields. The `_parse_analysis()` method (lines 532-557) never reads the `sentiment` subsection from YAML.

**Per-module config** (`analysis/sentiment.py` lines 51-76): `SentimentConfig` dataclass with all the same fields, completely independent.

**Orchestrator** (`pipeline/orchestrator.py` line 177):
```python
self.sentiment_analyzer = SentimentAnalyzer(SentimentConfig())  # BARE DEFAULTS!
```

**Result**: All sentiment config values in YAML are **silently ignored**. The module always uses its hardcoded defaults.

---

### 3.2 IVConfig — NOT Connected to Central Config

**YAML section** (`config/config.example.yaml` lines 147-155):
```yaml
analysis:
  iv:
    enabled: true
    weight: 0.20
    lookback_days: 30
    thresholds:
      high: 0.75
      low: 0.25
```

**Central `AnalysisConfig`** has fields like `iv_enabled`, `iv_weight`, `iv_threshold_high`, `iv_threshold_low` — these ARE parsed from YAML.

**Per-module `IVConfig`** (`analysis/iv_analyzer.py` lines 32-47) has DIFFERENT fields:
- `iv_high_threshold: float = 0.75` — matches YAML
- `iv_low_threshold: float = 0.25` — matches YAML
- `iv_high_value: float = 0.80` — **NOT in YAML or AnalysisConfig**
- `iv_low_value: float = 0.30` — **NOT in YAML or AnalysisConfig**
- `atm_range_pct: float = 5.0` — **NOT in YAML or AnalysisConfig**
- `min_strikes: int = 3` — **NOT in YAML or AnalysisConfig**

**Orchestrator** (line 180):
```python
self.iv_analyzer = IVAnalyzer(IVConfig())  # BARE DEFAULTS!
```

**Result**: YAML `analysis.iv` values are parsed into `AnalysisConfig` but **never passed** to `IVAnalyzer`. The `IVConfig` has additional fields with no YAML representation at all.

---

### 3.3 PCRConfig — NOT Connected to Central Config

**YAML section** (`config/config.example.yaml` lines 157-166):
```yaml
analysis:
  pcr:
    enabled: true
    weight: 0.25
    thresholds:
      put_high: 1.2
      call_high: 0.8
    weighting:
      volume_weight: 0.6
      oi_weight: 0.4
```

**Per-module `PCRConfig`** (`analysis/pcr_analyzer.py` lines 37-54):
- `pcr_high_threshold: float = 1.2` — matches YAML
- `pcr_low_threshold: float = 0.8` — matches YAML
- `pcr_extreme_high: float = 1.5` — **NOT in YAML or AnalysisConfig**
- `pcr_extreme_low: float = 0.5` — **NOT in YAML or AnalysisConfig**
- `volume_weight: float = 0.4` — **CONFLICT**: YAML says 0.6 for `volume_weight`, but PCRConfig uses 0.4 (which is the OI weight)
- `min_total_oi: int = 100` — **NOT in YAML**

**Orchestrator** (line 181):
```python
self.pcr_analyzer = PCRAnalyzer(PCRConfig())  # BARE DEFAULTS!
```

**Result**: YAML PCR values parsed but never used. Additional thresholds missing from YAML entirely.

---

### 3.4 OIConfig — NOT Connected to Central Config

**YAML section** (`config/config.example.yaml` lines 168-171):
```yaml
analysis:
  oi:
    enabled: true
    weight: 0.20
    concentration_threshold: 0.15
```

**Per-module `OIConfig`** (`analysis/oi_analyzer.py` lines 36-49):
- `high_oi_concentration: float = 0.04` — **MAJOR CONFLICT**: YAML says 0.15 (15%), module uses 0.04 (4%)
- `significant_oi_change: float = 0.20` — **NOT in YAML**
- `max_strikes_to_analyze: int = 50` — **NOT in YAML**
- `min_total_oi: int = 100` — **NOT in YAML**

**Orchestrator** (line 182):
```python
self.oi_analyzer = OIAnalyzer(OIConfig())  # BARE DEFAULTS!
```

**Result**: The 0.15 vs 0.04 discrepancy is critical — the module was already patched (see Bug #7 comment) but the YAML still says 0.15.

---

### 3.5 MaxPainConfig — NOT Connected to Central Config

**YAML section** (`config/config.example.yaml` lines 173-177):
```yaml
analysis:
  max_pain:
    enabled: true
    weight: 0.15
    distance_threshold: 2.0
```

**Per-module `MaxPainConfig`** (`analysis/max_pain.py` lines 32-41):
- `distance_threshold: float = 3.0` — **CONFLICT**: YAML says 2.0, module defaults to 3.0
- `expiry_weight_factor: float = 1.0` — **NOT in YAML**
- `min_strikes: int = 3` — **NOT in YAML**

**Orchestrator** (line 183):
```python
self.max_pain_calculator = MaxPainCalculator(MaxPainConfig())  # BARE DEFAULTS!
```

**Result**: YAML value of 2.0 is parsed but never used; module always uses 3.0.

---

### 3.6 WallDetectorConfig — NOT Connected to Central Config

**YAML section** (`config/config.example.yaml` lines 132-142):
```yaml
walls:
  min_oi_percentage: 0.05
  major_threshold: 0.15
  max_levels: 3
  strength:
    distance_factor: 0.30
    oi_factor: 0.70
```

**Central `WallsConfig`** (`config/loader.py` lines 218-224):
- `min_oi_percentage: float = 0.15` — **CONFLICT with YAML's 0.05**
- `major_threshold: float = 0.25` — **CONFLICT with YAML's 0.15**

**Per-module `WallDetectorConfig`** (`analysis/wall_detector.py` lines 29-52) — completely DIFFERENT config:
- `min_oi_concentration: float = 0.002` — different field name and value (0.2%)
- `major_wall_concentration: float = 0.01` — different field (1%)
- `max_wall_distance: float = 15.0` — **NOT in WallsConfig or YAML**
- `min_absolute_oi: int = 10` — **NOT in WallsConfig or YAML**

**Orchestrator** (line 170):
```python
self.wall_detector = WallDetector(WallDetectorConfig())  # BARE DEFAULTS!
```

**Result**: THREE different wall configurations with different field names and values. The YAML WallsConfig is parsed but never reaches WallDetector. The WallDetectorConfig has entirely different fields.

---

### 3.7 GammaExposureConfig — NOT Connected to Central Config

**YAML**: No `gamma` section exists in config.yaml at all.

**Central config**: No gamma fields in any dataclass.

**Per-module `GammaExposureConfig`** (`analysis/gamma_exposure.py` lines 39-65) — 10 fields, none configurable from YAML:
- `significant_level_threshold: float = 0.05`
- `min_oi_threshold: int = 10`
- `flip_search_range: float = 0.30`
- `use_simplified_delta: bool = True`
- `dte_reference_days: float = 7.0`
- `max_dte_weight: float = 3.0`
- `min_dte_weight: float = 0.3`
- `enable_dte_weighting: bool = True`

**Orchestrator** (line 174):
```python
self.gamma_calculator = GammaExposureCalculator(GammaExposureConfig())  # BARE DEFAULTS!
```

**Result**: Zero YAML configurability for gamma exposure.

---

### 3.8 SignalScorerConfig — NOT Connected to Central Config

**YAML**: No `signal_scorer` section exists.

**Central config**: No signal scoring fields in any dataclass.

**Per-module `SignalScorerConfig`** (`analysis/signal_scorer.py` lines 38-66) — 12 weight fields + thresholds, none configurable from YAML:
- `iv_weight: float = 0.15`
- `pcr_weight: float = 0.18`
- `oi_weight: float = 0.15`
- `max_pain_weight: float = 0.10`
- `sentiment_weight: float = 0.16`
- `gamma_weight: float = 0.10`
- `oi_flow_weight: float = 0.12`
- `wall_concentration_weight: float = 0.04`
- `pcr_strike_alignment_weight: float = 0.08`
- `whale_flow_weight: float = 0.05`
- `min_confidence: float = 0.4`
- `agreement_threshold: float = 0.6`

**Orchestrator** (line 155):
```python
self.signal_scorer = SignalScorer()  # BARE DEFAULTS!
```

**Result**: Zero YAML configurability for signal scoring weights — the heart of the signal generation logic.

---

### 3.9 WhaleDetectorConfig — Partially Connected

**YAML** (`config/config.example.yaml` lines 94-128):
```yaml
whale:
  min_premium: 500
  block_threshold: 5000
  ...
  asset_thresholds: { BTCUSDT: ... }
  confidence_boost: { ... }
```

**Central `WhaleConfig`** (`config/loader.py` lines 204-214):
- `min_premium: float = 100_000` — **MAJOR CONFLICT**: YAML says 500, dataclass defaults to $100,000
- `block_threshold: float = 500_000` — **CONFLICT**: YAML says 5,000, dataclass defaults to $500,000
- `confidence_boost_net_volume_threshold: float = 20_000_000` — **CONFLICT**: YAML says 50,000

**Per-module `WhaleDetectorConfig`** (`whale/whale_detector.py` lines 38-54) — yet another separate config:
- `min_premium: float = 100_000` — same as WhaleConfig default (CONFLICT with YAML 500)
- `block_threshold: float = 500_000` — same as WhaleConfig default (CONFLICT with YAML 5,000)
- `lookback_hours: int = 24` — matches
- `min_trades_for_analysis: int = 3` — **NOT in YAML or WhaleConfig**
- `bullish_threshold: float = 0.3` — **NOT in YAML or WhaleConfig**
- `bearish_threshold: float = -0.3` — **NOT in YAML or WhaleConfig**
- `asset_thresholds` — partially connected through orchestrator

**Orchestrator** (lines 158-164):
```python
whale_config = WhaleDetectorConfig(
    min_premium=config.whale.min_premium,          # Connected!
    block_threshold=config.whale.block_threshold,   # Connected!
    lookback_hours=config.whale.lookback_hours,     # Connected!
    asset_thresholds=config.whale.asset_thresholds, # Connected!
)
```

**Result**: Whale config is the **only module that partially connects** to the central config. However, the central config's defaults are wildly different from YAML values, and several WhaleDetectorConfig fields are not in YAML.

---

### 3.10 VolumeAnalyzerConfig — NOT Connected

**Per-module config** (`whale/volume_analyzer.py` lines 20-22):
- `time_buckets: int = 4`
- `high_concentration_threshold: float = 0.3`

**Orchestrator** (line 167):
```python
self.whale_volume_analyzer = WhaleVolumeAnalyzer(VolumeAnalyzerConfig())  # BARE DEFAULTS!
```

**Result**: No YAML representation.

---

### 3.11 ActivityScorer — NOT Connected

**Per-module defaults** (`ranking/activity_scorer.py` lines 60-67, 70-75):
- DEFAULT_WEIGHTS dict — same values as `RankingConfig.scoring_weights` in YAML but **not connected**
- `oi_change_max: float = 20.0` — matches YAML
- `volume_spike_max: float = 5.0` — matches YAML
- `total_volume_max: float = 10_000_000` — **CONFLICT**: YAML says 100,000,000 ($100M)

**Orchestrator** (line 138):
```python
self.activity_scorer = ActivityScorer()  # BARE DEFAULTS!
```

**Result**: Activity scorer weights and thresholds are not fed from YAML config.

---

### 3.12 PipelineConfig vs Central Config — Duplication

**`PipelineConfig`** (`pipeline/orchestrator.py` lines 58-78) duplicates values from `PipelineConfig` in `config/loader.py` (lines 161-169):

| Field | `config/loader.py` PipelineConfig | `orchestrator.py` PipelineConfig |
|-------|----------------------------------|--------------------------------|
| timeout_total_seconds | 600 | timeout_seconds: 600 |
| timeout_activity_scan_seconds | 30 | activity_scan_timeout: 60 **CONFLICT** |
| timeout_data_fetch_seconds | 120 | data_fetch_timeout: 180 **CONFLICT** |
| timeout_analysis_seconds | 180 | analysis_timeout: 180 |
| top_assets_count → top_n_assets | 5 | top_n_assets: 5 |
| min_activity_score | 0.30 | min_activity_score: 0.30 |
| — | — | min_signal_confidence: 0.50 |
| — | — | max_signals_per_run: 5 |

**Result**: Two different PipelineConfig classes with conflicting timeout defaults. The orchestrator's version is what actually runs; the central config's timeouts are never used.

---

### 3.13 CLI Defaults Override Config

**`cli.py`** (lines 143-164) has hardcoded defaults:
- `--top-n`: default=5 — **duplicates** `ranking.top_assets_count`
- `--min-confidence`: default=0.30 — **CONFLICT**: `OutputConfig.min_confidence` defaults to 0.55
- `--min-activity`: default=0.15 — **CONFLICT**: `RankingConfig.min_activity_score` defaults to 0.30

**`cli.py` `run_pipeline()`** (lines 189-217) also has its own defaults:
- `top_n: int = 5`
- `min_confidence: float = 0.50` — **third different value!**
- `min_activity: float = 0.30`

**Result**: Three different sources for the same parameters, with three different default values.

---

### 3.14 RateLimiter — NOT Connected

**`orchestrator.py`** (lines 117-120):
```python
self.rate_limiter = RateLimiter(
    requests_per_second=15.0,  # YAML says 10
    burst=30,                   # YAML says 20
)
```

**YAML**:
```yaml
binance:
  rate_limit:
    requests_per_second: 10
    burst: 20
```

**Result**: Rate limiter hardcoded with different values than YAML.

---

### 3.15 SRLevelConfig — NOT Connected

**Per-module config** (`output/sr_levels.py`) — not examined in detail but initialized in orchestrator:
```python
self.sr_calculator = SRLevelCalculator(SRLevelConfig())  # BARE DEFAULTS!
```

**Result**: No YAML configurability.

---

### 3.16 Missing SentimentConfig in Central Config

The `config/config.example.yaml` has an `analysis.sentiment` section with 18+ fields, but:
- `AnalysisConfig` dataclass in `config/loader.py` has **NO sentiment fields**
- `_parse_analysis()` in `config/loader.py` **never reads** the `sentiment` subsection
- `config/__init__.py` does not export any `SentimentConfig`

This is the largest missing piece in the central config system.

---

## 4. Summary of Default Value Conflicts

| Parameter | YAML Value | Central Config Default | Module Config Default | Actual Runtime |
|-----------|-----------|----------------------|---------------------|---------------|
| whale.min_premium | 500 | 100,000 | 100,000 | 100,000 (via orchestrator bridge) |
| whale.block_threshold | 5,000 | 500,000 | 500,000 | 500,000 (via orchestrator bridge) |
| whale.confidence_boost.net_volume_threshold | 50,000 | 20,000,000 | — | 20,000,000 |
| walls.min_oi_percentage | 0.05 | 0.15 | 0.002 | 0.002 |
| walls.major_threshold | 0.15 | 0.25 | 0.01 | 0.01 |
| max_pain.distance_threshold | 2.0 | 2.0 | 3.0 | 3.0 |
| oi.concentration_threshold | 0.15 | 0.15 | 0.04 | 0.04 |
| pcr.volume_weight (naming confusion) | 0.6 | 0.6 | 0.4 | 0.4 |
| ranking.min_activity_score | 0.15 | 0.30 | 0.30 | 0.30 |
| output.signals.min_confidence | 0.30 | 0.55 | — | 0.50 (from CLI) |
| rate_limit.requests_per_second | 10 | 10 | — | 15 (hardcoded) |
| rate_limit.burst | 20 | 20 | — | 30 (hardcoded) |
| pipeline.activity_scan_seconds | 30 | 30 | — | 60 (PipelineConfig) |
| pipeline.data_fetch_seconds | 120 | 120 | — | 180 (PipelineConfig) |
| activity_scorer.total_volume_max | 100,000,000 | 100,000,000 | 10,000,000 | 10,000,000 |

---

## 5. Modules Initialized with Bare Defaults in Orchestrator

The following modules in `pipeline/orchestrator.py` are initialized with **no connection** to the central `Config` object:

| Line | Module | Config Used | Central Config Connected? |
|------|--------|------------|--------------------------|
| 117-120 | RateLimiter | Hardcoded (15/30) | No (YAML says 10/20) |
| 138 | ActivityScorer | `ActivityScorer()` | No |
| 155 | SignalScorer | `SignalScorer()` | No |
| 167 | WhaleVolumeAnalyzer | `VolumeAnalyzerConfig()` | No |
| 170 | WallDetector | `WallDetectorConfig()` | No |
| 171 | SRLevelCalculator | `SRLevelConfig()` | No |
| 174 | GammaExposureCalculator | `GammaExposureConfig()` | No |
| 177 | SentimentAnalyzer | `SentimentConfig()` | No |
| 180 | IVAnalyzer | `IVConfig()` | No |
| 181 | PCRAnalyzer | `PCRConfig()` | No |
| 182 | OIAnalyzer | `OIConfig()` | No |
| 183 | MaxPainCalculator | `MaxPainConfig()` | No |

**Only WhaleDetector** (lines 158-164) is partially connected.

---

## 6. Recommendations for Single Source of Truth

### 6.1 Eliminate Per-Module Config Dataclasses

Move all per-module config dataclasses (`IVConfig`, `PCRConfig`, `OIConfig`, `MaxPainConfig`, `WallDetectorConfig`, `GammaExposureConfig`, `SentimentConfig`, `SignalScorerConfig`, `VolumeAnalyzerConfig`, `WhaleDetectorConfig`) into `config/loader.py` as part of the central `Config` hierarchy. Each module should accept its section of the central config, not its own separate class.

### 6.2 Add Missing YAML Sections

Add to `config.yaml`:
- `signal_scorer:` section with all 10+ weight fields
- `gamma_exposure:` section
- `wall_detector:` section (with correct field names matching what the module actually uses)
- `volume_analyzer:` section
- `activity_scorer:` section

### 6.3 Add SentimentConfig to AnalysisConfig

The `AnalysisConfig` dataclass needs sentiment fields:
- `sentiment_enabled`, `sentiment_weight`
- All L/S ratio thresholds, funding rate thresholds
- Contrarian mode settings
- Weights for combined sentiment

The `_parse_analysis()` method needs a `sentiment` subsection parser.

### 6.4 Bridge Orchestrator to Central Config

Every module initialization in `orchestrator.py` should extract its config from `self.config`:
```python
# Instead of:
self.sentiment_analyzer = SentimentAnalyzer(SentimentConfig())

# Should be:
self.sentiment_analyzer = SentimentAnalyzer(
    SentimentConfig(
        ls_ratio_extreme_high=config.analysis.sentiment_ls_ratio_extreme_high,
        ...
    )
)
```

### 6.5 Eliminate Duplicate PipelineConfig

Remove `PipelineConfig` from `orchestrator.py`. Use `config.pipeline` and `config.output` from the central config instead.

### 6.6 Fix CLI Default Conflicts

CLI defaults should read from the loaded config, not hardcode their own:
```python
parser.add_argument("--min-confidence", default=config.output.min_confidence)
```

### 6.7 Fix Default Value Conflicts

Align all defaults across YAML, central dataclasses, and module configs to a single agreed value. Priority: YAML > central dataclass > module default.

### 6.8 Add Config Validation for Coverage

Add a validation step in `ensure_valid_config()` that checks all parsed YAML sections have corresponding dataclass fields, and warns if YAML keys have no mapping.

---

## 7. Files Requiring Changes

| File | Change Type |
|------|-------------|
| `config/config.example.yaml` | Add missing sections (gamma, signal_scorer, wall_detector, volume_analyzer, activity_scorer); fix conflicting values |
| `config/loader.py` | Add SentimentConfig, GammaExposureConfig, SignalScorerConfig, WallDetectorConfig, VolumeAnalyzerConfig, ActivityScorerConfig, proper SRLevelConfig to central Config; add parsers for all new sections |
| `config/validators.py` | Add validation for all new config sections |
| `config/__init__.py` | Export new config classes |
| `pipeline/orchestrator.py` | Replace all bare default constructors with config-driven initialization; remove duplicate PipelineConfig; use RateLimiter from config |
| `cli.py` | Read defaults from config instead of hardcoding; remove conflicting default values |
| `analysis/sentiment.py` | Accept central config fields instead of independent SentimentConfig |
| `analysis/iv_analyzer.py` | Accept central config fields; add missing YAML fields (iv_high_value, iv_low_value, atm_range_pct, min_strikes) |
| `analysis/pcr_analyzer.py` | Accept central config fields; add missing YAML fields (pcr_extreme_high, pcr_extreme_low) |
| `analysis/oi_analyzer.py` | Accept central config fields; fix YAML vs code discrepancy (0.15 vs 0.04) |
| `analysis/max_pain.py` | Accept central config fields; fix distance_threshold conflict (2.0 vs 3.0) |
| `analysis/wall_detector.py` | Accept central config fields; unify field names with YAML |
| `analysis/gamma_exposure.py` | Accept central config fields; add YAML section |
| `analysis/signal_scorer.py` | Accept central config fields; add YAML section for weights |
| `whale/whale_detector.py` | Already partially connected; add missing fields to YAML and central config |
| `whale/volume_analyzer.py` | Accept central config fields; add YAML section |
| `ranking/activity_scorer.py` | Accept central config weights from central config; fix total_volume_max conflict |
| `ranking/asset_selector.py` | Accept central config fields |
| `output/sr_levels.py` | Accept central config fields |
| `utils/rate_limiter.py` | Remove hardcoded BINANCE_*_RATE_LIMIT instances; use config values |
