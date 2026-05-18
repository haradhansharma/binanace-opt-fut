# 🔍 Signal Generation Bug Analysis & API Audit

## 📡 APIs Being Called

### Options API (`/eapi/*` — Binance Options SDK)

| API Endpoint | Method | File | Purpose |
|---|---|---|---|
| GET `/eapi/v1/exchangeInfo` | `exchange_information()` | `options_fetcher.py:131` | Get all option symbols & underlyings |
| GET `/eapi/v1/openInterest` | `open_interest()` | `options_fetcher.py:298` | OI per symbol (requires expiration) |
| GET `/eapi/v1/mark` | `option_mark_price()` | `options_fetcher.py:417-420` | Mark prices, IV, Greeks |
| GET `/eapi/v1/blockTrades` | `recent_block_trades_list()` | `options_fetcher.py:493-501` | Block trades for whale detection |
| GET `/eapi/v1/index` | `index_price()` | `options_fetcher.py:559` | Spot/index price for underlying |
| GET `/eapi/v1/ticker/24hr` | `ticker24hr_price_change_statistics()` | `options_fetcher.py:597-599` | 24hr volume/price data |
| GET `/eapi/v1/trades` | `recent_trades_list()` | `options_fetcher.py:666` | Recent trades (currently unused in pipeline) |

### Futures API (`/fapi/*` — Binance USDS-M Futures SDK)

| API Endpoint | Method | File | Purpose |
|---|---|---|---|
| GET `/fapi/v1/ticker/24hr` | `ticker24hr_price_change_statistics()` | `futures_fetcher.py:138` | Price & 24hr stats |
| GET `/fapi/v1/openInterest` | `open_interest()` | `futures_fetcher.py:251` | Futures open interest |
| GET `/fapi/v1/fundingRate` | `get_funding_rate_history()` | `futures_fetcher.py:286` | Funding rate history |
| GET `/fapi/v1/premiumIndex` | `mark_price()` | `futures_fetcher.py:341` | Mark & index price |
| GET `/fapi/v1/klines` | `kline_candlestick_data()` | `futures_fetcher.py:387` | Candlestick data |
| GET `/fapi/v1/depth` | `order_book()` | `futures_fetcher.py:540` | Order book depth |
| GET `/fapi/v1/exchangeInfo` | `exchange_information()` | `futures_fetcher.py:574` | Exchange info & symbols |
| GET `/futures/data/openInterestHist` | `open_interest_statistics()` | `futures_fetcher.py:675` | Historical OI (weight: 0) |
| GET `/futures/data/topLongShortPositionRatio` | `top_trader_long_short_ratio_positions()` | `futures_fetcher.py:882` | Top trader L/S positions (weight: 0) |
| GET `/futures/data/topLongShortAccountRatio` | `top_trader_long_short_ratio_accounts()` | `futures_fetcher.py:998` | Top trader L/S accounts (weight: 0) |

---

## 🐛 Signal Generation Bugs Found

### BUG #1: 🚨 CRITICAL — Sentiment Contrarian Penalty Always Applied (Even When Trend Confirms)

**File:** `sentiment.py`, lines 504-518  
**Severity:** CRITICAL — Systematically reduces confidence on correct contrarian signals

The extreme long positioning contrarian SHORT signal (lines 499-521) applies a trend penalty unconditionally. Even when `price_dropping=True` and the code boosts confidence (`*1.2`), the penalty block at lines 513-518 still executes right after because it's NOT in an `else` branch:

```python
if has_trend and price_dropping and signal == SignalDirection.SHORT:
    confidence = min(confidence * 1.2, 0.85)  # Boost applied
    logger.debug(...)
# BUG: This runs ALWAYS, even after the boost above!
penalty = max(0.3, 1.0 - abs(price_change_pct) * 0.5)
confidence *= penalty  # Then immediately reduces it!
logger.debug(...)
```

The same bug exists for extreme short positioning contrarian LONG (lines 523-546).

**Impact:** When price confirms the contrarian signal (e.g., extreme longs + price dropping → SHORT), confidence gets boosted then immediately penalized, effectively nullifying the trend confirmation.

---

### BUG #2: 🚨 HIGH — OI Flow `oi_change_pct` Always Zero

**File:** `orchestrator.py`, line 606  
**Severity:** HIGH — OI flow signal always uses 0% OI change

```python
oi_change_pct = futures_data.open_interest_change_pct if hasattr(futures_data, 'open_interest_change_pct') else 0.0
```

The `FuturesData` model (`models.py`) does NOT have an `open_interest_change_pct` field. It only has `open_interest`. The `hasattr` check always returns `False`, so `oi_change_pct` is always `0.0`. This means the OI flow type is always NEUTRAL — the entire `oi_flow_weight` (12% of signal scoring) is dead weight.

**Impact:** The OI flow signal (12% weight — the PRIMARY signal per config) never generates a non-neutral signal, removing a major signal source from the combined score.

---

### BUG #3: 🔴 HIGH — IV Treated as Decimal When API Returns Percentage

**File:** `options_fetcher.py`, lines 818-823  
**Severity:** HIGH — IV values are likely wrong, cascading into IV analysis and gamma exposure

```python
iv_str = mark.get("mark_iv") or mark.get("markIV") or "0"
try:
    iv = float(iv_str) if iv_str else 0.0
```

The comment on line 812 says "API returns markIV as decimal (e.g., '1.45' = 145%)" but there's NO conversion from decimal to percentage. The `IVAnalyzer` treats values > 0.80 as "high IV" (`iv_high_value=0.80`). If the API returns `1.45` (meaning 145%), the code uses `1.45` directly — which happens to work. But if the API returns `0.45` (meaning 45%), the code treats it as 45% which is correct. The inconsistency is that the code doesn't know which format the API actually returns, and the comment suggests both formats are possible.

This cascades into:

- **IV analyzer:** wrong percentile/state detection
- **Gamma exposure:** wrong IV scaling in `_estimate_gamma()` (uses `iv_scaling = 0.6 / iv`)
- **Signal scorer:** wrong IV signal direction

---

### BUG #4: 🟠 MEDIUM — Volume PCR Uses `amount` (USDT Notional) Not Contract Volume

**File:** `options_fetcher.py`, lines 863-872  
**Severity:** MEDIUM — Volume PCR is skewed because it mixes notional with contract counts

```python
volume_value = amount if amount > 0 else volume * last_price
...
total_call_volume += volume_value  # This is in USDT notional
total_put_volume += volume_value   # This is in USDT notional
```

The `OptionData.volume` field stores `int(volume)` which is contract volume. But `total_call_volume` / `total_put_volume` use `volume_value` (USDT notional). Then `get_volume_pcr()` computes `total_put_volume / total_call_volume`. The issue: `volume` (integer contract count) is stored as `OptionData.volume = int(volume)` but the PCR uses notional value — this creates an asymmetry where high-priced calls (deep ITM) dominate the volume PCR even if fewer contracts traded.

---

### BUG #5: 🟠 MEDIUM — DTE Always Defaults to 7 Days (No Real Expiry Data in Chain)

**File:** `gamma_exposure.py`, lines 225-227  
**Severity:** MEDIUM — Gamma exposure weighting is always the same

```python
if expiry is None:
    return 7.0  # If no expiry provided, assume standard 7-day expiry
```

The `OptionsChain.expiry` field is never populated in `options_fetcher.py`'s `get_option_chain()` — the returned `OptionsChain` always has `expiry=None`. This means `_calculate_dte()` always returns `7.0`, `dte_weight` is always `1.0`, and `expiry_imminent` is always `False`. The entire DTE-weighting system is non-functional.

---

### BUG #6: 🟡 MEDIUM — Block Trade `side` Field Interpreted as Integer, Not String

**File:** `whale_detector.py`, line 611  
**Severity:** MEDIUM — Could cause wrong sentiment classification

```python
side = trade.get("side", 0)  # -1 = sell, 1 = buy
```

But in the `_parse_trade()` method (line 211):

```python
direction = trade.get("side", trade.get("direction", "UNKNOWN"))
```

This expects a string like `"BUY"`/`"SELL"`. The `analyze_block_trades()` method uses integer comparison (`side == -1`), while `_parse_trade()` uses string comparison. The block trades API response format is inconsistent between the two code paths. If the API returns `side` as a string (like `"BUY"`), the integer comparison `side == -1` will always be `False`, making all trades appear as "buy" (bullish), creating a systematic LONG bias in whale analysis.

---

### BUG #7: 🟡 LOW-MEDIUM — Wall Detection Threshold Still Too High for Real-World OI

**File:** `wall_detector.py`, line 36  
**Severity:** LOW-MEDIUM — Walls may rarely be detected

```python
min_oi_concentration: float = 0.005   # 0.5% of total OI
```

The comment at line 33 acknowledges that max single-strike OI is ~0.67% of total. With a 0.5% threshold, only the very top strikes pass — and the `min_absolute_oi: int = 25` filter also applies. For assets with very distributed OI (which is common in Binance crypto options), walls are rarely detected, meaning the `wall_concentration` signal (4% weight) and wall-based SL/TP levels are often empty.

---

### BUG #8: 🟡 LOW — `_derive_iv_term_structure_signal` Dead Code

**File:** `signal_scorer.py`, lines 669-738  
**Severity:** LOW — Dead method, never called

The `_derive_iv_term_structure_signal()` method still exists in the code even though its weight was removed from `SignalScorerConfig`. The method is never called in the `analyze()` method — it's dead code. While not harmful, it could confuse maintainers.

---

### BUG #9: 🟡 LOW — Whale `quoteQty` Currency Ambiguity

**File:** `options_fetcher.py`, lines 1013-1028 and `whale_detector.py`, lines 567-580  
**Severity:** LOW-MEDIUM — Possible systematic under/over-counting

Both files have comments acknowledging uncertainty about whether `quoteQty` is in base currency (BTC) or USDT. The code assumes USDT (because USDT-margined), but if the API actually returns base currency, all whale premium calculations are off by the spot price factor (e.g., 80x for BTC). There's no validation or logging to confirm the actual API response format.

---

## 📊 Summary Table (Original Bugs #1-#9)

| # | Bug | Severity | File | Impact | Status |
|---|---|---|---|---|---|
| 1 | Sentiment penalty applied unconditionally | 🚨 CRITICAL | `sentiment.py:513` | Confidence wrongly reduced on correct signals | ✅ Fixed |
| 2 | OI flow always zero (missing model field) | 🚨 HIGH | `orchestrator.py:606` | 12% signal weight dead | ✅ Fixed |
| 3 | IV decimal/percentage format ambiguity | 🔴 HIGH | `options_fetcher.py:818` | IV + gamma signals may be wrong | ✅ Fixed |
| 4 | Volume PCR mixes notional and contract vol | 🟠 MEDIUM | `options_fetcher.py:863` | Volume PCR skewed | ✅ Fixed |
| 5 | DTE always 7 days (expiry never populated) | 🟠 MEDIUM | `gamma_exposure.py:225` | DTE weighting non-functional | ✅ Fixed |
| 6 | Block trade side integer vs string mismatch | 🟡 MEDIUM | `whale_detector.py:611 vs 211` | Potential systematic LONG bias | ✅ Fixed |
| 7 | Wall threshold still too restrictive | 🟡 LOW-MED | `wall_detector.py:36` | Walls rarely detected | ✅ Fixed |
| 8 | Dead IV term structure method | 🟡 LOW | `signal_scorer.py:669` | Dead code | ✅ Fixed |
| 9 | Whale quoteQty currency ambiguity | 🟡 LOW-MED | `options_fetcher.py:1013` | Premium values may be wrong | ✅ Fixed |

---

### BUG #10: 🚨 HIGH — Systematic LONG Bias in `_combine_signals()`

**File:** `signal_scorer.py`, lines 805-810 (`_combine_signals`)
**Severity:** HIGH — Systematically favors LONG signals over SHORT

The raw_score threshold is symmetric (+/-0.15), but several signals systematically contribute positive (LONG) weighted scores more often than negative:

1. **max_pain**: Tends to be above current price → LONG signal dominates
2. **PCR contrarian**: Legacy logic flips high PCR (bearish crowd) → LONG, and PCR > 1.0 is the default in crypto
3. **wall_imbalance**: Put walls (protection) are structurally more common → typically > 0 → LONG
4. **pcr_strike alignment**: `put_heavy_count` dominates in crypto (protection puts) → LONG

The raw_score exceeds +0.15 far more often than -0.15, producing a systematic LONG bias.

**Fix applied (multi-layered):**
- **Wall concentration signal** (`_derive_wall_concentration_signal`): Added price trend dampening — when put walls suggest LONG but price is actively dropping, confidence is reduced (support is failing)
- **PCR strike signal** (`_derive_pcr_strike_signal`): Added proximity-weighted counts instead of raw counts, plus price trend dampening — reduces the structural LONG bias from distant OTM put-heavy strikes
- **PCR trend-aware logic** (`pcr_analyzer.py`): Lowered trend threshold from 0.15% to 0.05% so that trend-aware logic activates for almost all non-flat periods, reducing contrarian LONG fallback
- **Structural bias correction** (`_combine_signals`): When max_pain, wall_conc, and pcr_strike all point LONG but balanced signals (oi_flow, sentiment) don't confirm, raw_score is reduced by 25%
- **Trend validation** (`_combine_signals`): If combined signal opposes the clear price trend, confidence is penalized (50% for strong opposition, 30% for moderate)

---

### BUG #11: 🟠 MEDIUM — OI Flow ±5% Threshold Too High

**File:** `orchestrator.py`, lines 616-617
**Severity:** MEDIUM — OI flow (12% weight) frequently returns NEUTRAL, wasting its weight

```python
oi_building = oi_change_pct > 5
oi_unwinding = oi_change_pct < -5
```

The ±5% threshold is too high for daily BTC/ETH OI changes. For example, BTC OI going from 20,000 to 20,800 contracts is a +4% change — meaningful but classified as NEUTRAL. This means the OI flow signal (12% weight) frequently returns NEUTRAL, effectively wasting its weight allocation.

**Fix applied:** Lowered threshold from ±5% to ±2% for daily mode and ±1% for intraday mode:
```python
oi_threshold = 2.0  # Default: ±2% for daily
if intraday_config and intraday_config.enabled:
    oi_threshold = 1.0  # ±1% for intraday
oi_building = oi_change_pct > oi_threshold
oi_unwinding = oi_change_pct < -oi_threshold
```

---

### BUG #12: 🟠 MEDIUM — Volume PCR Now Redundant with OI PCR

**Files:** `models.py`, `options_fetcher.py`, `pcr_analyzer.py`
**Severity:** MEDIUM — Volume PCR lost its distinct information after Bug #4 fix

After Bug #4 fix changed `total_call_volume`/`total_put_volume` from USDT notional to contract count, the volume PCR (`put_contracts / call_contracts`) became essentially the same as OI PCR (`put_OI / call_OI`) — both measure the put/call ratio by contract count. This means the `volume_weight` (40%) in PCR combined calculation was contributing redundant information.

**Fix applied:**
1. **`models.py`**: Added `total_call_notional` and `total_put_notional` fields to `OptionsChain`, plus `get_notional_pcr()` method
2. **`options_fetcher.py`**: Track both contract count AND USDT notional separately — `total_call_volume`/`total_put_volume` use contract count, `total_call_notional`/`total_put_notional` use USDT value
3. **`pcr_analyzer.py`**: Changed volume PCR to use `chain.get_notional_pcr()` instead of `chain.get_volume_pcr()`. Notional PCR captures capital flow direction (where big money is trading), which is distinct from OI PCR (structural positioning). Deep ITM options have much higher notional per contract, so notional PCR reveals different information.

---

## 📊 Updated Summary Table

| # | Bug | Severity | File | Status |
|---|---|---|---|---|
| 1 | Sentiment penalty applied unconditionally | 🚨 CRITICAL | `sentiment.py:513` | ✅ Fixed |
| 2 | OI flow always zero (missing model field) | 🚨 HIGH | `orchestrator.py:606` | ✅ Fixed |
| 3 | IV decimal/percentage format ambiguity | 🔴 HIGH | `options_fetcher.py:818` | ✅ Fixed |
| 4 | Volume PCR mixes notional and contract vol | 🟠 MEDIUM | `options_fetcher.py:863` | ✅ Fixed |
| 5 | DTE always 7 days (expiry never populated) | 🟠 MEDIUM | `gamma_exposure.py:225` | ✅ Fixed |
| 6 | Block trade side integer vs string mismatch | 🟡 MEDIUM | `whale_detector.py:611` | ✅ Fixed |
| 7 | Wall threshold still too restrictive | 🟡 LOW-MED | `wall_detector.py:36` | ✅ Fixed |
| 8 | Dead IV term structure method | 🟡 LOW | `signal_scorer.py:669` | ✅ Fixed |
| 9 | Whale quoteQty currency ambiguity | 🟡 LOW-MED | `options_fetcher.py:1013` | ✅ Fixed |
| 10 | Systematic LONG bias in signal combination | 🚨 HIGH | `signal_scorer.py:805` | ✅ Fixed |
| 11 | OI flow ±5% threshold too high | 🟠 MEDIUM | `orchestrator.py:616` | ✅ Fixed |
| 12 | Volume PCR redundant with OI PCR | 🟠 MEDIUM | `models.py` + `options_fetcher.py` + `pcr_analyzer.py` | ✅ Fixed |
| 13 | SelectionConfig ignores min_options_volume/min_active_strikes from config | 🚨 HIGH | `orchestrator.py:139` | ✅ Fixed |
| 14 | total_options_volume is contract count but compared against USDT threshold | 🚨 HIGH | `options_fetcher.py:985` + `activity_scorer.py:194` | ✅ Fixed |
| 15 | RankingConfig defaults too high ($5M/10) vs config.yaml ($100K/5) | 🟠 MEDIUM | `config/loader.py:148` | ✅ Fixed |

---

### BUG #13: 🚨 HIGH — SelectionConfig Ignores `min_options_volume` and `min_active_strikes` from Config

**File:** `orchestrator.py`, lines 139-144
**Severity:** HIGH — Most assets fail liquidity check silently

```python
self.asset_selector = AssetSelector(
    SelectionConfig(
        top_n=self.pipeline_config.top_n_assets,
        min_activity_score=self.pipeline_config.min_activity_score,
    )
)
```

Only `top_n` and `min_activity_score` are passed. `min_options_volume` and `min_active_strikes` are NOT passed, so they fall back to `SelectionConfig` defaults ($100K / 5). The `config.ranking.min_options_volume` and `config.ranking.min_active_strikes` loaded from YAML are **completely ignored**.

**Fix applied:** Pass all ranking config fields to `SelectionConfig`:
```python
self.asset_selector = AssetSelector(
    SelectionConfig(
        top_n=self.pipeline_config.top_n_assets,
        min_activity_score=self.pipeline_config.min_activity_score,
        min_options_volume=config.ranking.min_options_volume,
        min_active_strikes=config.ranking.min_active_strikes,
        excluded_symbols=set(config.ranking.excluded_symbols),
    )
)
```

---

### BUG #14: 🚨 HIGH — `total_options_volume` is Contract Count But Compared Against USDT Dollar Threshold

**Files:** `options_fetcher.py:985`, `activity_scorer.py:194`
**Severity:** HIGH — Virtually all assets fail the liquidity check

After Bug #4 fix changed `total_call_volume`/`total_put_volume` from USDT notional to contract count, the `total_options_volume` field (used for liquidity checks and scoring) became a contract count instead of a USDT amount.

The liquidity check in `asset_selector.py`:
```python
metrics.total_options_volume >= self.config.min_options_volume  # e.g., 5000 >= 100000? NO!
```

A typical ETHUSDT options chain might have 5000 contracts traded, but the `min_options_volume` threshold is $100,000 USDT. 5000 contracts ≠ $100K, so the asset fails the liquidity check.

This affects BOTH:
1. `options_fetcher.py:get_activity_summary()` — sets `total_options_volume = chain.total_call_volume + chain.total_put_volume` (contract count)
2. `activity_scorer.py:score_from_chain()` — same issue

**Fix applied:** Use `chain.total_call_notional + chain.total_put_notional` (USDT notional) for `total_options_volume` instead of contract count. This ensures the liquidity check compares like-for-like (USDT vs USDT).

---

### BUG #15: 🟠 MEDIUM — `RankingConfig` Defaults Too High ($5M/10) vs config.yaml ($100K/5)

**File:** `config/loader.py`, lines 148-149
**Severity:** MEDIUM — If config.yaml doesn't specify values, defaults reject most assets

```python
min_options_volume: float = 5_000_000  # $5M default
min_active_strikes: int = 10           # 10 strikes default
```

The config.yaml specifies `$100K / 5` which works for most Binance Options assets. But if the YAML is missing these keys, the loader falls back to $5M/10, which rejects virtually all crypto options assets. The defaults should match the recommended config.yaml values.

**Fix applied:** Lowered defaults to $100K / 5 to match config.yaml.

---

> **All 15 bugs have been fixed. Bugs #13-#15 specifically address why only 1 asset was being selected — the liquidity check was comparing contract count against a USDT dollar threshold, and the config was not being properly passed to the asset selector.**
