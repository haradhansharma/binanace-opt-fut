# Configuration Refactor Plan - Single Source of Truth

## Overview

This document outlines the plan to refactor the configuration system to use `config.yaml` as the single source of truth. All configuration dataclasses will be defined in `config/loader.py` and loaded via `load_config()`.

### Goals

1. **Single Source of Truth**: All configuration comes from `config.yaml`
2. **No Value Changes**: Preserve all existing default values
3. **No Logic Breaks**: Maintain backward compatibility
4. **File-wise Naming**: Use prefixed keys when same key has different values across files

---

## Current State Analysis

### Already Consolidated (in loader.py)

| Config Class | Status | Notes |
|--------------|--------|-------|
| `BinanceConfig` | ✅ Done | API configuration |
| `RankingConfig` | ✅ Done | Asset ranking |
| `PipelineConfig` (loader.py) | ✅ Done | Pipeline timeouts |
| `IntradayConfig` | ✅ Done | Intraday settings |
| `WhaleConfig` | ✅ Done | Whale detection |
| `AssetWhaleThreshold` | ✅ Done | Asset-specific thresholds |
| `WallsConfig` | ✅ Done | Wall detection |
| `SentimentConfig` | ✅ Done | Sentiment analysis |
| `IVConfig` | ✅ Done | IV analysis (just refactored) |
| `AnalysisConfig` | ✅ Done | Analysis settings |
| `ValidationConfig` | ✅ Done | Futures validation |
| `OutputConfig` | ✅ Done | Signal output |
| `StopLossWallBasedConfig` | ✅ Done | Stop loss |
| `TakeProfitWallBasedConfig` | ✅ Done | Take profit |
| `LoggingConfig` | ✅ Done | Logging settings |

### Needs Refactoring (duplicated in individual files)

| File | Config Class | Current Location | Target Location |
|------|--------------|------------------|-----------------|
| `analysis/pcr_analyzer.py` | `PCRConfig` | Local dataclass | `config/loader.py` |
| `analysis/oi_analyzer.py` | `OIConfig` | Local dataclass | `config/loader.py` |
| `analysis/max_pain.py` | `MaxPainConfig` | Local dataclass | `config/loader.py` |
| `analysis/wall_detector.py` | `WallDetectorConfig` | Local dataclass | `config/loader.py` |
| `analysis/gamma_exposure.py` | `GammaExposureConfig` | Local dataclass | `config/loader.py` |
| `analysis/signal_scorer.py` | `SignalScorerConfig` | Local dataclass | `config/loader.py` |
| `pipeline/orchestrator.py` | `PipelineConfig` | Local dataclass | `config/loader.py` (different from loader's!) |
| `ranking/activity_scorer.py` | Weights & params | Hardcoded | `config/loader.py` |
| `ranking/asset_selector.py` | `SelectionConfig` | Local dataclass | `config/loader.py` |
| `whale/whale_detector.py` | `WhaleDetectorConfig` | Local dataclass | `config/loader.py` |
| `whale/volume_analyzer.py` | `VolumeAnalyzerConfig` | Local dataclass | `config/loader.py` |
| `output/sr_levels.py` | `SRLevelConfig` | Local dataclass | `config/loader.py` |

---

## Potential Conflicts (Same Key, Different Values)

### Issue: PipelineConfig exists in TWO places with DIFFERENT fields!

**loader.py PipelineConfig:**
```python
timeout_total_seconds: int = 600
timeout_activity_scan_seconds: int = 30
timeout_asset_selection_seconds: int = 10
timeout_data_fetch_seconds: int = 120
timeout_analysis_seconds: int = 180
timeout_whale_wall_seconds: int = 60
timeout_signal_output_seconds: int = 60
```

**orchestrator.py PipelineConfig:**
```python
timeout_seconds: int = 600
activity_scan_timeout: int = 60
data_fetch_timeout: int = 180
analysis_timeout: int = 180
top_n_assets: int = 5
min_activity_score: float = 0.30
min_signal_confidence: float = 0.50
max_signals_per_run: int = 5
output_to_stdout: bool = True
save_to_database: bool = False
```

**Solution**: Use prefixed naming in config.yaml:
```yaml
pipeline:
  # loader.py fields (timeouts)
  timeout_total_seconds: 600
  timeout_activity_scan_seconds: 30
  # ...
  
  # orchestrator.py fields (selection/signal)
  orchestrator_top_n_assets: 5
  orchestrator_min_activity_score: 0.30
  orchestrator_min_signal_confidence: 0.50
```

### Issue: WallsConfig vs WallDetectorConfig

**loader.py WallsConfig:**
```python
min_oi_percentage: float = 0.15
major_threshold: float = 0.25
max_levels: int = 3
strength_distance_factor: float = 0.30
strength_oi_factor: float = 0.70
```

**wall_detector.py WallDetectorConfig:**
```python
min_oi_concentration: float = 0.002  # Different value!
major_wall_concentration: float = 0.01  # Different value!
max_wall_distance: float = 15.0
min_absolute_oi: int = 10
```

**Solution**: Keep separate, use different YAML sections:
```yaml
walls:  # For loader.py WallsConfig (used in signal scoring)
  min_oi_percentage: 0.15
  
wall_detector:  # For wall_detector.py WallDetectorConfig
  min_oi_concentration: 0.002
  major_wall_concentration: 0.01
```

### Issue: WhaleConfig vs WhaleDetectorConfig

**loader.py WhaleConfig:**
```python
min_premium: float = 100_000
block_threshold: float = 500_000
lookback_hours: int = 24
confidence_boost_enabled: bool = True
confidence_boost_max: float = 0.15
confidence_boost_net_volume_threshold: float = 20_000_000
asset_thresholds: Dict
```

**whale_detector.py WhaleDetectorConfig:**
```python
min_premium: float = 100_000
block_threshold: float = 500_000
lookback_hours: int = 24
min_trades_for_analysis: int = 3  # Additional!
bullish_threshold: float = 0.3    # Additional!
bearish_threshold: float = -0.3   # Additional!
asset_thresholds: Dict
```

**Solution**: Merge into one, add missing fields to loader.py

---

## Refactoring Tasks

### Task 1: PCRConfig (analysis/pcr_analyzer.py) ✅ Ready

**Current Values:**
```python
pcr_high_threshold: float = 1.2
pcr_low_threshold: float = 0.8
pcr_extreme_high: float = 1.5
pcr_extreme_low: float = 0.5
volume_weight: float = 0.4
min_total_oi: int = 100
```

**Steps:**
1. [ ] Add `PCRAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add PCR config section to `config.yaml`
3. [ ] Update `pcr_analyzer.py` to load config from `load_config()`
4. [ ] Remove local `PCRConfig` from `pcr_analyzer.py`
5. [ ] Update `analysis/__init__.py` to import from config
6. [ ] Update all usages in `signal_scorer.py`, `orchestrator.py`

**config.yaml addition:**
```yaml
analysis:
  pcr:
    enabled: true
    weight: 0.25
    # From PCRConfig (pcr_analyzer.py)
    analyzer:
      pcr_high_threshold: 1.2
      pcr_low_threshold: 0.8
      pcr_extreme_high: 1.5
      pcr_extreme_low: 0.5
      volume_weight: 0.4
      min_total_oi: 100
```

---

### Task 2: OIConfig (analysis/oi_analyzer.py) ✅ Ready

**Current Values:**
```python
high_oi_concentration: float = 0.04
significant_oi_change: float = 0.20
max_strikes_to_analyze: int = 50
min_total_oi: int = 100
```

**Steps:**
1. [ ] Add `OIAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add OI config section to `config.yaml`
3. [ ] Update `oi_analyzer.py` to load config from `load_config()`
4. [ ] Remove local `OIConfig` from `oi_analyzer.py`
5. [ ] Update `analysis/__init__.py` to import from config
6. [ ] Update all usages

**config.yaml addition:**
```yaml
analysis:
  oi:
    enabled: true
    weight: 0.20
    # From OIConfig (oi_analyzer.py)
    analyzer:
      high_oi_concentration: 0.04
      significant_oi_change: 0.20
      max_strikes_to_analyze: 50
      min_total_oi: 100
```

---

### Task 3: MaxPainConfig (analysis/max_pain.py) ✅ Ready

**Current Values:**
```python
distance_threshold: float = 3.0
expiry_weight_factor: float = 1.0
min_strikes: int = 3
```

**Steps:**
1. [ ] Add `MaxPainAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add max_pain config section to `config.yaml`
3. [ ] Update `max_pain.py` to load config from `load_config()`
4. [ ] Remove local `MaxPainConfig` from `max_pain.py`
5. [ ] Update `analysis/__init__.py` to import from config
6. [ ] Update all usages

**config.yaml addition:**
```yaml
analysis:
  max_pain:
    enabled: true
    weight: 0.15
    # From MaxPainConfig (max_pain.py)
    analyzer:
      distance_threshold: 3.0
      expiry_weight_factor: 1.0
      min_strikes: 3
```

---

### Task 4: WallDetectorConfig (analysis/wall_detector.py) ⚠️ Conflict

**Current Values:**
```python
min_oi_concentration: float = 0.002
major_wall_concentration: float = 0.01
max_wall_distance: float = 15.0
min_absolute_oi: int = 10
```

**Note:** Different from `WallsConfig` in loader.py. Keep separate.

**Steps:**
1. [ ] Add `WallDetectorAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add `wall_detector` config section to `config.yaml` (separate from `walls`)
3. [ ] Update `wall_detector.py` to load config from `load_config()`
4. [ ] Remove local `WallDetectorConfig` from `wall_detector.py`
5. [ ] Update `analysis/__init__.py` to import from config
6. [ ] Update all usages in `orchestrator.py`

**config.yaml addition:**
```yaml
wall_detector:  # Separate from 'walls' section
  min_oi_concentration: 0.002
  major_wall_concentration: 0.01
  max_wall_distance: 15.0
  min_absolute_oi: 10
```

---

### Task 5: GammaExposureConfig (analysis/gamma_exposure.py) ✅ Ready

**Current Values:**
```python
significant_level_threshold: float = 0.05
min_oi_threshold: int = 10
flip_search_range: float = 0.30
use_simplified_delta: bool = True
dte_reference_days: float = 7.0
max_dte_weight: float = 3.0
min_dte_weight: float = 0.3
enable_dte_weighting: bool = True
```

**Steps:**
1. [ ] Add `GammaExposureAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add gamma config section to `config.yaml`
3. [ ] Update `gamma_exposure.py` to load config from `load_config()`
4. [ ] Remove local `GammaExposureConfig` from `gamma_exposure.py`
5. [ ] Update `analysis/__init__.py` to import from config
6. [ ] Update all usages

**config.yaml addition:**
```yaml
gamma_exposure:
  significant_level_threshold: 0.05
  min_oi_threshold: 10
  flip_search_range: 0.30
  use_simplified_delta: true
  dte_reference_days: 7.0
  max_dte_weight: 3.0
  min_dte_weight: 0.3
  enable_dte_weighting: true
```

---

### Task 6: SignalScorerConfig (analysis/signal_scorer.py) ✅ Ready

**Current Values:**
```python
iv_weight: float = 0.15
pcr_weight: float = 0.18
oi_weight: float = 0.15
max_pain_weight: float = 0.10
sentiment_weight: float = 0.16
gamma_weight: float = 0.10
oi_flow_weight: float = 0.12
wall_concentration_weight: float = 0.04
pcr_strike_alignment_weight: float = 0.08
whale_flow_weight: float = 0.05
min_confidence: float = 0.4
agreement_threshold: float = 0.6
iv_high_value: float = 0.80
iv_low_value: float = 0.40
```

**Steps:**
1. [ ] Add `SignalScorerAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add signal_scorer config section to `config.yaml`
3. [ ] Update `signal_scorer.py` to load config from `load_config()`
4. [ ] Remove local `SignalScorerConfig` from `signal_scorer.py`
5. [ ] Update `analysis/__init__.py` to import from config

**config.yaml addition:**
```yaml
signal_scorer:
  # Signal weights
  iv_weight: 0.15
  pcr_weight: 0.18
  oi_weight: 0.15
  max_pain_weight: 0.10
  sentiment_weight: 0.16
  gamma_weight: 0.10
  oi_flow_weight: 0.12
  wall_concentration_weight: 0.04
  pcr_strike_alignment_weight: 0.08
  whale_flow_weight: 0.05
  # Thresholds
  min_confidence: 0.4
  agreement_threshold: 0.6
  iv_high_value: 0.80
  iv_low_value: 0.40
```

---

### Task 7: PipelineConfig Conflict Resolution ⚠️ Critical

**Problem:** Two `PipelineConfig` classes with different fields.

**Solution:** Rename orchestrator's PipelineConfig to `OrchestratorConfig`

**Steps:**
1. [ ] Create `OrchestratorConfig` dataclass in `loader.py`
2. [ ] Add `orchestrator` section to `config.yaml`
3. [ ] Update `orchestrator.py` to use `OrchestratorConfig` from loader
4. [ ] Remove local `PipelineConfig` from `orchestrator.py`
5. [ ] Update imports in all files that use orchestrator's PipelineConfig

**config.yaml addition:**
```yaml
orchestrator:
  timeout_seconds: 600
  activity_scan_timeout: 60
  data_fetch_timeout: 180
  analysis_timeout: 180
  top_n_assets: 5
  min_activity_score: 0.30
  min_signal_confidence: 0.50
  max_signals_per_run: 5
  output_to_stdout: true
  save_to_database: false
```

---

### Task 8: SelectionConfig (ranking/asset_selector.py) ✅ Ready

**Current Values:**
```python
top_n: int = 5
min_activity_score: float = 0.15
min_options_volume: float = 100_000
min_active_strikes: int = 5
excluded_symbols: Set[str] = None
```

**Steps:**
1. [ ] Add `SelectionConfig` dataclass to `loader.py` (if not present)
2. [ ] Add `asset_selector` config section to `config.yaml`
3. [ ] Update `asset_selector.py` to load config from `load_config()`
4. [ ] Remove local `SelectionConfig` from `asset_selector.py`
5. [ ] Update all usages

**config.yaml addition:**
```yaml
asset_selector:
  top_n: 5
  min_activity_score: 0.15
  min_options_volume: 100000
  min_active_strikes: 5
  excluded_symbols: []
```

---

### Task 9: WhaleDetectorConfig (whale/whale_detector.py) ⚠️ Partial Overlap

**Current Values:**
```python
min_premium: float = 100_000
block_threshold: float = 500_000
lookback_hours: int = 24
min_trades_for_analysis: int = 3
bullish_threshold: float = 0.3
bearish_threshold: float = -0.3
asset_thresholds: Dict
```

**Note:** Overlaps with `WhaleConfig` but has additional fields.

**Steps:**
1. [ ] Add missing fields to `WhaleConfig` in `loader.py`
2. [ ] Update `whale_detector.py` to load config from `load_config()`
3. [ ] Remove local `WhaleDetectorConfig` from `whale_detector.py`
4. [ ] Update all usages

**config.yaml update:**
```yaml
whale:
  # Existing fields
  min_premium: 500
  block_threshold: 5000
  lookback_hours: 24
  # New fields (from whale_detector.py)
  min_trades_for_analysis: 3
  bullish_threshold: 0.3
  bearish_threshold: -0.3
  # ... rest unchanged
```

---

### Task 10: VolumeAnalyzerConfig (whale/volume_analyzer.py) ✅ Ready

**Current Values:**
```python
time_buckets: int = 4
high_concentration_threshold: float = 0.3
```

**Steps:**
1. [ ] Add `VolumeAnalyzerConfig` dataclass to `loader.py`
2. [ ] Add `volume_analyzer` config section to `config.yaml`
3. [ ] Update `volume_analyzer.py` to load config from `load_config()`
4. [ ] Remove local config from `volume_analyzer.py`
5. [ ] Update all usages

**config.yaml addition:**
```yaml
volume_analyzer:
  time_buckets: 4
  high_concentration_threshold: 0.3
```

---

### Task 11: SRLevelConfig (output/sr_levels.py) ✅ Ready

**Current Values:**
```python
max_support_levels: int = 3
max_resistance_levels: int = 3
min_level_distance_pct: float = 1.0
wall_weight: float = 0.50
max_pain_weight: float = 0.30
volume_weight: float = 0.20
default_sl_distance_pct: float = 2.0
default_tp_ratios: List[float] = [1.5, 3.0, 5.0]
```

**Steps:**
1. [ ] Add `SRLevelCalculatorConfig` dataclass to `loader.py`
2. [ ] Add `sr_levels` config section to `config.yaml`
3. [ ] Update `sr_levels.py` to load config from `load_config()`
4. [ ] Remove local `SRLevelConfig` from `sr_levels.py`
5. [ ] Update all usages

**config.yaml addition:**
```yaml
sr_levels:
  max_support_levels: 3
  max_resistance_levels: 3
  min_level_distance_pct: 1.0
  wall_weight: 0.50
  max_pain_weight: 0.30
  volume_weight: 0.20
  default_sl_distance_pct: 2.0
  default_tp_ratios: [1.5, 3.0, 5.0]
```

---

### Task 12: ActivityScorer Constants (ranking/activity_scorer.py) ✅ Ready

**Current Values:**
```python
# DEFAULT_WEIGHTS
OI_CHANGE: 0.25
VOLUME_SPIKE: 0.20
IV_INTEREST: 0.15
PCR_EXTREME: 0.15
WHALE_ACTIVITY: 0.15
TOTAL_VOLUME: 0.10

# Parameters
oi_change_max: float = 20.0
volume_spike_max: float = 5.0
total_volume_max: float = 10_000_000
```

**Steps:**
1. [ ] Add `ActivityScorerConfig` dataclass to `loader.py`
2. [ ] Add `activity_scorer` config section to `config.yaml`
3. [ ] Update `activity_scorer.py` to load config from `load_config()`
4. [ ] Replace hardcoded values with config references

**config.yaml addition:**
```yaml
activity_scorer:
  weights:
    oi_change: 0.25
    volume_spike: 0.20
    iv_interest: 0.15
    pcr_extreme: 0.15
    whale_activity: 0.15
    total_volume: 0.10
  thresholds:
    oi_change_max: 20.0
    volume_spike_max: 5.0
    total_volume_max: 10000000
```

---

## Implementation Pattern

For each task, follow this exact pattern:

### Step-by-Step Instructions

1. **Add dataclass to `config/loader.py`**
   ```python
   @dataclass
   class XxxConfig:
       """Configuration for XXX."""
       key1: type = default_value
       key2: type = default_value
   ```

2. **Add to main `Config` class**
   ```python
   @dataclass
   class Config:
       # ... existing fields
       xxx: XxxConfig = field(default_factory=XxxConfig)
   ```

3. **Add parsing method (if needed)**
   ```python
   @staticmethod
   def _parse_xxx(data: Dict) -> XxxConfig:
       return XxxConfig(
           key1=data.get("key1", default),
           key2=data.get("key2", default),
       )
   ```

4. **Update `_build_config()` to parse the section**
   ```python
   if "xxx" in data:
       config.xxx = cls._parse_xxx(data["xxx"])
   ```

5. **Add to `config/__init__.py` exports**
   ```python
   from binance_signal_generator.config.loader import XxxConfig
   __all__ = [..., "XxxConfig"]
   ```

6. **Update the analyzer file**
   ```python
   # BEFORE
   @dataclass
   class XxxConfig:
       key: type = value
   
   class XxxAnalyzer:
       def __init__(self, config: Optional[XxxConfig] = None):
           self.config = config or XxxConfig()
   
   # AFTER
   from binance_signal_generator.config import load_config
   
   class XxxAnalyzer:
       def __init__(self, config_path: Optional[str] = None):
           loaded_config = load_config(config_path)
           self.config = loaded_config.xxx  # or loaded_config.xxx_analyzer
   ```

7. **Update all usages**
   - Remove `XxxConfig()` instantiation
   - Remove `config` parameter passing
   - Update imports

8. **Add to `config.yaml`**
   ```yaml
   xxx:
     key1: value1
     key2: value2
   ```

---

## Progress Tracking

| Task | Config Class | Status | Files Changed |
|------|--------------|--------|---------------|
| 0 | IVConfig | ✅ DONE | iv_analyzer.py, signal_scorer.py, orchestrator.py, analysis/__init__.py |
| 1 | PCRAnalyzerConfig | ✅ DONE | pcr_analyzer.py, signal_scorer.py, orchestrator.py |
| 2 | OIAnalyzerConfig | ✅ DONE | oi_analyzer.py, signal_scorer.py, orchestrator.py |
| 3 | MaxPainAnalyzerConfig | ✅ DONE | max_pain.py, signal_scorer.py, orchestrator.py |
| 4 | WallDetectorAnalyzerConfig | ✅ DONE | wall_detector.py, orchestrator.py |
| 5 | GammaExposureAnalyzerConfig | ✅ DONE | gamma_exposure.py, orchestrator.py |
| 6 | SignalScorerAnalyzerConfig | ✅ DONE | signal_scorer.py |
| 7 | OrchestratorConfig | ✅ DONE | orchestrator.py |
| 8 | AssetSelectorConfig | ✅ DONE | asset_selector.py, orchestrator.py |
| 9 | WhaleDetectorAnalyzerConfig | ✅ DONE | whale_detector.py, orchestrator.py |
| 10 | VolumeAnalyzerConfig | ✅ DONE | volume_analyzer.py, orchestrator.py |
| 11 | SRLevelCalculatorConfig | ✅ DONE | sr_levels.py, orchestrator.py |
| 12 | ActivityScorerConfig | ✅ DONE | activity_scorer.py |

---

## Testing Checklist

After each task, verify:

- [ ] `python -c "from binance_signal_generator.config import XxxConfig"` works
- [ ] `python -c "from binance_signal_generator.analysis import XxxAnalyzer"` works
- [ ] Analyzer loads config from YAML correctly
- [ ] Default values are preserved (no behavior change)
- [ ] No import errors in dependent files
- [ ] Orchestrator still initializes correctly

---

## Final config.yaml Structure

```yaml
# After all refactoring, config.yaml will have:

binance:           # API config
ranking:           # Asset ranking
pipeline:          # Pipeline timeouts (loader.py)
orchestrator:      # Orchestrator-specific settings
intraday:          # Intraday settings
whale:             # Whale detection (merged)
volume_analyzer:   # Volume analysis
walls:             # Wall scoring config
wall_detector:     # Wall detection config
gamma_exposure:    # Gamma exposure
activity_scorer:   # Activity scoring
asset_selector:    # Asset selection
analysis:          # Analysis settings
  iv:              # IV config
  pcr:             # PCR config
  oi:              # OI config
  max_pain:        # Max pain config
  sentiment:       # Sentiment config
signal_scorer:     # Signal scoring
sr_levels:         # S/R levels
validation:        # Futures validation
output:            # Signal output
logging:           # Logging config
```

---

## Notes

1. **Preserve All Values**: Never change default values during refactoring
2. **One Task at a Time**: Complete each task fully before moving to next
3. **Test After Each**: Run tests after each task
4. **Commit Frequently**: Commit after each successful task
5. **Document Changes**: Update this file as tasks are completed
