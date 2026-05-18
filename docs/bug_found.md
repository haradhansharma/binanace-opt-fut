# ROOT CAUSE ANALYSIS: Why Only LONG Signals When Market Is Bearish

I found multiple systemic bugs that collectively bias the signal heavily toward LONG. Here they are, ranked by impact:

---

## BUG #1 (CRITICAL): `_derive_oi_flow_signal` — Always defaults to LONG when OI is building ✅ FIXED

**File:** `signal_scorer.py`, lines 316-363

```python
if flow_direction == "BUILDING":
    # OI increasing suggests conviction in current direction
    # For now, assume price is rising (would need price data for full logic)
    signal = SignalDirection.LONG  # ← HARDCODED LONG!!!
    confidence = min(abs(oi_change) / 20.0, 0.8)
```

The code explicitly assumes OI building = LONG with a comment saying "For now, assume price is rising." But when the market is going DOWN with OI building, that's actually a SHORT buildup (new short positions being created). The `oi_flow_weight` is 0.12 (12%) — the highest single advanced metric weight — so this hardcoded LONG bias has massive impact.

**Fix applied (2 files changed):**

1. **`orchestrator.py`** — Now passes `price_change_pct` from `futures_data` into the `oi_flow` dict and computes a `flow_type` field that correctly classifies:
   - OI UP + Price UP = `LONG_BUILDUP`
   - OI UP + Price DOWN = `SHORT_BUILDUP`
   - OI DOWN + Price UP = `SHORT_COVERING`
   - OI DOWN + Price DOWN = `LONG_UNWINDING`

2. **`signal_scorer.py`** — `_derive_oi_flow_signal()` now uses `flow_type` to determine direction:
   - `LONG_BUILDUP` → LONG signal
   - `SHORT_BUILDUP` → SHORT signal
   - `SHORT_COVERING` → LONG signal
   - `LONG_UNWINDING` → SHORT signal
   - Also includes a fallback path using `price_change_pct` when `flow_type` is not available

---

## BUG #2 (CRITICAL): PCR Analyzer uses CONTRARIAN logic — inverts bearish signals ✅ FIXED

**File:** `pcr_analyzer.py`, lines 171-214

```python
# Very high PCR (extreme bearishness) - Strong bullish contrarian
if pcr >= self.config.pcr_extreme_high:
    return SignalDirection.LONG, 0.8  # ← HIGH PCR = BEARISH market → but returns LONG!

# Very low PCR (extreme bullishness) - Strong bearish contrarian
elif pcr <= self.config.pcr_extreme_low:
    return SignalDirection.SHORT, 0.8  # ← LOW PCR = BULLISH market → but returns SHORT!
```

PCR > 1.2 means more puts are being bought (bearish sentiment), but the code returns LONG as a "contrarian" signal. In a bearish market, PCR stays high for a reason — the crowd is correctly bearish. The contrarian approach systematically flips bearish confirmation into a LONG signal, which is wrong when the market is trending down.

**Fix applied (2 files changed):**

1. **`pcr_analyzer.py`** — `_generate_signal()` now accepts optional `price_change_pct` and uses trend-aware logic:

   | PCR Signal | Price Trend | Action |
   |------------|-------------|--------|
   | High (bearish) | Price DOWN | Trend confirms → SHORT (follow trend, boosted confidence) |
   | High (bearish) | Price UP | Trend opposes → LONG (contrarian, 40% reduced confidence) |
   | Low (bullish) | Price UP | Trend confirms → LONG (follow trend, boosted confidence) |
   | Low (bullish) | Price DOWN | Trend opposes → SHORT (contrarian, 40% reduced confidence) |
   | Any | No trend data | Legacy contrarian logic (unchanged behavior) |

   - `analyze()` method now accepts `price_change_pct` parameter
   - When trend confirms PCR: confidence is boosted by trend strength
   - When trend opposes PCR: contrarian still fires but with 60% of original confidence
   - Module/class docstrings updated to reflect trend-aware logic

2. **`signal_scorer.py`** — Extracts `price_change_pct` from `advanced_metrics["oi_flow"]` and passes it to `pcr_analyzer.analyze()`

---

## BUG #3 (HIGH): OI Analyzer also uses CONTRARIAN logic ✅ FIXED

**File:** `oi_analyzer.py`, lines 170-231

```python
if imbalance > 0.15:
    # Significant put bias - contrarian bullish
    return SignalDirection.LONG, confidence  # ← More puts = bearish → returns LONG!

elif imbalance < -0.15:
    # Significant call bias - contrarian bearish
    return SignalDirection.SHORT, confidence  # ← More calls = bullish → returns SHORT!
```

Same contrarian problem as PCR. When put OI dominates (people buying puts = bearish sentiment), the code flips it to LONG. In a downtrend, put dominance is confirming the trend, not signaling a reversal.

**Fix applied (2 files changed):**

1. **`oi_analyzer.py`** — `_generate_signal()` now accepts optional `price_change_pct` and uses trend-aware logic:

   | OI Imbalance | Price Trend | Action |
   |--------------|-------------|--------|
   | Put-heavy (bearish) | Price DOWN | Trend confirms → SHORT (follow trend, boosted confidence) |
   | Put-heavy (bearish) | Price UP | Trend opposes → LONG (contrarian, 40% reduced confidence) |
   | Call-heavy (bullish) | Price UP | Trend confirms → LONG (follow trend, boosted confidence) |
   | Call-heavy (bullish) | Price DOWN | Trend opposes → SHORT (contrarian, 40% reduced confidence) |
   | Any | No trend data | Legacy contrarian logic (unchanged behavior) |

   - `analyze()` method now accepts `price_change_pct` parameter
   - Module/class docstrings updated to reflect trend-aware logic

2. **`signal_scorer.py`** — Now passes `price_change_pct` to `oi_analyzer.analyze()` from `advanced_metrics`

---

## BUG #4 (MEDIUM): Gamma signal always defaults to LONG in positive GEX regime ✅ FIXED

**File:** `signal_scorer.py`, lines 219-314

```python
if gex_regime == "POSITIVE":
    # Dealers provide support (buy dips)
    if gamma_flip and spot_price:
        if spot_price < gamma_flip:
            signal = SignalDirection.LONG  # ← Makes sense
        else:
            signal = SignalDirection.LONG  # ← ALSO LONG above flip!
    else:
        signal = SignalDirection.LONG  # ← ALWAYS LONG in positive GEX!
```

In a POSITIVE GEX regime, the code always returns LONG regardless of price position relative to gamma flip. Even if price is above the flip and trending down, it still returns LONG. Positive GEX should still allow SHORT signals when the price is dropping below support levels.

**Fix applied (1 file changed):**

1. **`signal_scorer.py`** — `_derive_gamma_signal()` now accepts `price_change_pct` and uses trend-aware logic:

   **Positive GEX (dealers provide support):**
   | Price Position | Price Trend | Action |
   |----------------|-------------|--------|
   | Below flip | Dropping | SHORT (support failing, momentum bearish) |
   | Below flip | Stable/Rising | LONG (support bounce expected) |
   | Above flip | Dropping | SHORT (bearish momentum overrides, reduced confidence) |
   | Above flip | Stable/Rising | LONG (support working) |
   | No flip | Dropping | SHORT (momentum overrides) |
   | No flip | Not dropping | LONG (positive regime) |

   **Negative GEX (dealers provide resistance):**
   | Price Position | Price Trend | Action |
   |----------------|-------------|--------|
   | Above flip | Rising | LONG (resistance failing, momentum bullish) |
   | Above flip | Stable/Falling | SHORT (resistance pushing down) |
   | Below flip | Rising | LONG (bullish momentum overrides, reduced confidence) |
   | Below flip | Stable/Falling | SHORT (resistance working) |
   | No flip | Rising | LONG (momentum overrides) |
   | No flip | Not rising | SHORT (negative regime) |

   - Counter-regime signals get 30% confidence reduction (SHORT in +GEX, LONG in -GEX)
   - `signal_scorer.analyze()` now passes `price_change_pct` to `_derive_gamma_signal()`

---

## BUG #5 (MEDIUM): Sentiment contrarian flips bullish confirmation to SHORT, but rarely activates for bearish ✅ FIXED

**File:** `sentiment.py`, lines 385-452

The contrarian logic activates on extreme L/S ratios (> 3.0) or extreme funding rates. However:

- In a downtrend, L/S ratios tend to be moderate (0.8-1.2), NOT extreme
- So the contrarian flip rarely triggers for bearish signals
- The "following mode" at the bottom returns LONG when `combined_score > 0.15`, which happens easily

**Fix applied (2 files changed):**

1. **`sentiment.py`** — `_determine_signal()` now accepts optional `price_change_pct` and uses trend-aware logic:

   | Sentiment Direction | Price Trend | Action |
   |--------------------|-------------|--------|
   | Bullish (score > 0.15) | Price dropping | SHORT (trend override, reduced confidence) |
   | Bullish (score > 0.15) | Price rising | LONG (confirmed, boosted confidence) |
   | Bearish (score < -0.15) | Price rising | LONG (trend override, reduced confidence) |
   | Bearish (score < -0.15) | Price dropping | SHORT (confirmed, boosted confidence) |
   | Neutral zone | Price dropping | SHORT (follow trend) |
   | Neutral zone | Price rising | LONG (follow trend) |
   | Extreme contrarian | Trend confirms | Boost confidence |
   | Extreme contrarian | Trend opposes | Reduce confidence by 40% |
   | Any | No trend data | Legacy behavior unchanged |

   - `analyze()` method now accepts `price_change_pct` parameter
   - Contrarian extremes now get trend-aware adjustments (boost if aligned, reduce if opposed)
   - Following mode now flips signal direction when price trend opposes sentiment
   - Neutral zone now generates directional signal when price has a clear trend

2. **`orchestrator.py`** — Now passes `futures_data.price_change_pct` to `sentiment_analyzer.analyze()`

---

## BUG #6 (SIGNIFICANT): Signal combination `raw_score` threshold is asymmetric ✅ FIXED

**File:** `signal_scorer.py`, lines 712-718

```python
if raw_score > 0.15:
    direction = SignalDirection.LONG
elif raw_score < -0.15:
    direction = SignalDirection.SHORT
```

Because of all the LONG biases above, the `raw_score` rarely goes negative enough to hit -0.15, while it easily exceeds +0.15. The combined effect of bugs 1-5 pushes the `raw_score` positive.

**Fix applied (1 file changed):**

1. **`signal_scorer.py`** — `_combine_signals()` now accepts optional `price_change_pct` and applies a trend validation filter after direction determination:

   | Signal Direction | Price Trend | Confidence Adjustment |
   |-----------------|-------------|---------------------|
   | LONG | Strong drop (>0.3%) | 50% penalty |
   | LONG | Moderate drop (>0.1%) | 30% penalty |
   | LONG | Rising (>0.1%) | 10% boost |
   | SHORT | Strong rise (>0.3%) | 50% penalty |
   | SHORT | Moderate rise (>0.1%) | 30% penalty |
   | SHORT | Dropping (>0.1%) | 10% boost |
   | Any | No trend data | No adjustment |

   - This acts as a safety net against any residual LONG bias from the weighted components
   - When the market clearly disagrees with the signal direction, confidence is significantly reduced
   - `analyze()` passes `price_change_pct` to `_combine_signals()`

---

## BUG #7 (AGGRAVATING): Whale `confidence_boost` always adds, never subtracts ✅ FIXED

**File:** `orchestrator.py`, line 721-722

```python
if whale_analysis and whale_analysis.confidence_boost > 0:
    confidence = min(confidence + whale_analysis.confidence_boost, 1.0)
```

This only increases confidence, never decreases it. Even if whales are selling (bearish), the confidence is only boosted when `confidence_boost > 0`. The confidence boost calculation in `whale_detector.py` always returns a positive value (0-0.2), so it always reinforces the existing signal direction — which is usually LONG due to the other bugs.

**Fix applied (1 file changed):**

1. **`orchestrator.py`** — `_create_trading_signal()` now checks whale direction alignment with signal direction:

   | Whale Direction | Signal Direction | Action |
   |----------------|-----------------|--------|
   | BULLISH | LONG | Boost confidence (aligned) |
   | BEARISH | SHORT | Boost confidence (aligned) |
   | BULLISH | SHORT | Reduce confidence by 60% of boost (opposed) |
   | BEARISH | LONG | Reduce confidence by 60% of boost (opposed) |
   | NEUTRAL | Any | No adjustment |

   - Uses `whale_analysis.whale_net_direction` (BULLISH/BEARISH/NEUTRAL) to determine alignment
   - When whale direction opposes signal, confidence is REDUCED instead of boosted
   - The penalty is 60% of the boost value (proportional to whale activity significance)

---

## Impact Summary

| Bug | File | Weight Impact | Bias |
|-----|------|--------------|------|
| #1 OI Flow hardcoded LONG | `signal_scorer.py:353` | 12% weight | ~~STRONG LONG~~ ✅ FIXED |
| #2 PCR contrarian flip | `pcr_analyzer.py:188` | 18% weight | ~~STRONG LONG~~ ✅ FIXED |
| #3 OI contrarian flip | `oi_analyzer.py:213` | 15% weight | ~~MODERATE LONG~~ ✅ FIXED |
| #4 Gamma always LONG in +GEX | `signal_scorer.py:276` | 10% weight | ~~MODERATE LONG~~ ✅ FIXED |
| #5 Sentiment contrarian rarely triggers bearish | `sentiment.py:412` | 15% weight | ~~MILD LONG~~ ✅ FIXED |
| #6 Raw score threshold asymmetry | `signal_scorer.py:713` | Combined effect | ~~MILD LONG~~ ✅ FIXED |
| #7 Whale boost only positive | `orchestrator.py:721` | Variable | ~~MILD LONG~~ ✅ FIXED |

**Combined: ~70% of the weighted signal components HAD a systematic LONG bias — ALL 7 BUGS NOW FIXED ✅**

---

## Recommended Fixes (Priority Order)

1. **~~Fix `_derive_oi_flow_signal`~~** ✅ DONE — Passed `futures_data.price_change_pct` into `advanced_metrics`, added `flow_type` classification in orchestrator, and updated signal scorer to use `flow_type` for correct OI flow direction

2. **~~Add trend context to PCR analyzer~~** ✅ DONE — Added `price_change_pct` parameter to `PCRAnalyzer.analyze()` and `_generate_signal()`. When price trend confirms PCR direction, follows the trend. When trend opposes, uses contrarian with 40% reduced confidence. Signal scorer now passes `price_change_pct` from `advanced_metrics` to PCR analyzer.

3. **~~Fix OI Analyzer contrarian logic~~** ✅ DONE — Added `price_change_pct` to `OIAnalyzer.analyze()` and `_generate_signal()`. Same trend-aware approach as PCR: when price confirms OI imbalance, follow trend; when opposes, contrarian with 40% reduced confidence. Signal scorer now passes `price_change_pct` to OI analyzer.

4. **~~Fix Gamma signal~~** ✅ DONE — Added `price_change_pct` to `_derive_gamma_signal()`. In positive GEX, price dropping now returns SHORT (support failing / momentum bearish) instead of always LONG. In negative GEX, price rising now returns LONG (resistance failing). Counter-regime signals get 30% confidence reduction.

5. **~~Make whale `confidence_boost` directional~~** ✅ DONE — Whale confidence boost is now directional: aligned → boost, opposed → reduce confidence by 60% of boost value. Uses `whale_net_direction` (BULLISH/BEARISH) to check alignment with signal direction.

6. **~~Add price trend filter~~** ✅ DONE — Added trend validation filter in `_combine_signals()`. When the combined signal direction opposes the clear price trend (>0.1% or >0.3%), confidence is penalized (30-50%). When trend confirms, confidence is boosted by 10%. Also, sentiment analyzer now uses trend-aware logic (Bug #5 fix) which adds trend context at the component level as well.
