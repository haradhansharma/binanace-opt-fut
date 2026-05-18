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

## 📊 Summary Table

| # | Bug | Severity | File | Impact |
|---|---|---|---|---|
| 1 | Sentiment penalty applied unconditionally | 🚨 CRITICAL | `sentiment.py:513` | Confidence wrongly reduced on correct signals |
| 2 | OI flow always zero (missing model field) | 🚨 HIGH | `orchestrator.py:606` | 12% signal weight dead |
| 3 | IV decimal/percentage format ambiguity | 🔴 HIGH | `options_fetcher.py:818` | IV + gamma signals may be wrong |
| 4 | Volume PCR mixes notional and contract vol | 🟠 MEDIUM | `options_fetcher.py:863` | Volume PCR skewed |
| 5 | DTE always 7 days (expiry never populated) | 🟠 MEDIUM | `gamma_exposure.py:225` | DTE weighting non-functional |
| 6 | Block trade side integer vs string mismatch | 🟡 MEDIUM | `whale_detector.py:611 vs 211` | Potential systematic LONG bias |
| 7 | Wall threshold still too restrictive | 🟡 LOW-MED | `wall_detector.py:36` | Walls rarely detected |
| 8 | Dead IV term structure method | 🟡 LOW | `signal_scorer.py:669` | Dead code |
| 9 | Whale quoteQty currency ambiguity | 🟡 LOW-MED | `options_fetcher.py:1013` | Premium values may be wrong |

---

> **The most impactful fix would be Bug #1 (sentiment penalty) and Bug #2 (OI flow dead weight) — together these represent significant distortion in signal generation.**
