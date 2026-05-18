"""
HTML Telegram formatter for Binance Options-Driven Futures Signals.

Uses Telegram HTML parse_mode for rich formatting:
- Bold headers, code-formatted prices, italic timestamps
- Visual strength bars, emoji direction indicators
- Structured sections: Entry/SL/TP, Key Levels, Options, Whale, OI Flow, Futures

Compatible with the JSON output from binance_signal_generator.
"""

from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def direction_emoji(direction: str) -> str:
    return {
        "LONG": "\U0001f7e2",
        "SHORT": "\U0001f534",
        "NEUTRAL": "\U0001f7e1",
    }.get(direction, "\u26aa")


def direction_tag(direction: str) -> str:
    return {
        "LONG": "🟢",
        "SHORT": "🔴",
        "NEUTRAL": "🟡",
    }.get(direction, "⚪")


def strength_bar(score: float) -> str:
    filled = int(round(score * 10))
    empty = 10 - filled
    return "\u2588" * filled + "\u2591" * empty


def confidence_label(confidence: float) -> str:
    if confidence >= 0.9:
        return "ULTRA HIGH"
    elif confidence >= 0.75:
        return "VERY HIGH"
    elif confidence >= 0.6:
        return "HIGH"
    elif confidence >= 0.45:
        return "MODERATE"
    else:
        return "LOW"


def format_price(price: float, symbol: str = "") -> str:
    if price is None:
        return "N/A"
    if not isinstance(price, (int, float)):
        return str(price)
    # Use 2 decimals for major coins, 4 for alts
    major = ("BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC")
    if any(m in symbol.upper() for m in major):
        return f"${price:,.2f}"
    else:
        return f"${price:,.4f}"


def format_volume(vol: float) -> str:
    if vol is None:
        return "N/A"
    if abs(vol) >= 1_000_000_000:
        return f"${vol/1_000_000_000:.2f}B"
    elif abs(vol) >= 1_000_000:
        return f"${vol/1_000_000:.2f}M"
    elif abs(vol) >= 1_000:
        return f"${vol/1_000:.1f}K"
    else:
        return f"${vol:.2f}"


def format_pct(value: float) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def html_bold(text: str) -> str:
    return f"<b>{text}</b>"


def html_code(text: str) -> str:
    return f"<code>{text}</code>"


def html_italic(text: str) -> str:
    return f"<i>{text}</i>"


def separator(char: str = "\u2500") -> str:
    return char * 32


# ═══════════════════════════════════════════════════════════════
# Signal Formatter
# ═══════════════════════════════════════════════════════════════

def format_signal_message(signal: Dict[str, Any], rank: int, total: int) -> str:
    """
    Format a single trading signal into an informative Telegram HTML message.

    The message is designed to be visually scannable and information-dense,
    covering: direction & confidence, entry/SL/TP, key levels, options metrics,
    whale activity, and OI flow — everything a trader needs at a glance.
    """
    symbol = signal.get("symbol", "???")
    direction = signal.get("direction", "NEUTRAL")
    confidence = signal.get("confidence_score", 0.0)
    strength = signal.get("signal_strength", "WEAK")
    activity_score = signal.get("activity_score", 0.0)

    entry_zone = signal.get("entry_zone", {})
    stop_loss = signal.get("stop_loss", {})
    take_profit_levels = signal.get("take_profit_levels", [])
    support_levels = signal.get("support_levels", [])
    resistance_levels = signal.get("resistance_levels", [])

    whale = signal.get("whale_metrics", {})
    options = signal.get("options_metrics", {})
    futures = signal.get("futures_metrics", {})
    risk_reward = signal.get("risk_reward_ratio", 0.0)

    # Direction styling
    dir_emoji = direction_emoji(direction)
    dir_color_tag = direction_tag(direction)

    lines = []

    # ── Header ──
    lines.append(f"{dir_emoji} {html_bold(f'{dir_color_tag} {direction} {symbol}')} {dir_color_tag}")
    lines.append(
        f"{html_bold('Signal Strength:')} {strength} | "
        f"{html_bold('Confidence:')} {confidence:.1%} ({confidence_label(confidence)})"
    )
    lines.append(
        f"{html_bold('Activity Score:')} {activity_score:.3f} | "
        f"{html_bold('Asset Rank:')} #{rank} of {total}"
    )
    lines.append(separator())

    # ── Entry & Risk Management ──
    ideal_price = entry_zone.get("ideal", 0)
    lines.append(f"\U0001f3af {html_bold('ENTRY ZONE')}")
    lines.append(
        f"  Range: {html_code(format_price(entry_zone.get('min', 0), symbol))} \u2014 "
        f"{html_code(format_price(entry_zone.get('max', 0), symbol))}"
    )
    lines.append(f"  Ideal: {html_code(format_price(ideal_price, symbol))}")

    lines.append("")
    lines.append(f"\U0001f6d1 {html_bold('STOP LOSS')} \u2014 {html_code(format_price(stop_loss.get('price', 0), symbol))}")
    sl_type = stop_loss.get("type", "UNKNOWN")
    sl_dist = stop_loss.get("distance_pct", 0)
    sl_conf = stop_loss.get("confidence", 0)
    sl_source = stop_loss.get("source_strike")
    lines.append(f"  Type: {sl_type} | Dist: {format_pct(sl_dist)} | Conf: {sl_conf:.0%}")
    if sl_source:
        lines.append(f"  Source Strike: {format_price(sl_source, symbol)}")

    lines.append("")
    lines.append(f"\U0001f3af {html_bold('TAKE PROFIT LEVELS')}")
    for tp in take_profit_levels:
        tp_type = tp.get("type", "N/A")
        tp_emoji = (
            "\U0001f7e2" if tp.get("level", 0) == 1
            else "\U0001f7e1" if tp.get("level", 0) == 2
            else "\U0001f535"
        )
        lines.append(
            f"  {tp_emoji} TP{tp.get('level')}: {html_code(format_price(tp.get('price', 0), symbol))} "
            f"| R:R {tp.get('ratio', 0):.1f} | {format_pct(tp.get('distance_pct', 0))} | {tp_type}"
        )

    lines.append("")
    rr_color = "\U0001f7e2" if risk_reward >= 1.5 else "\U0001f7e1" if risk_reward >= 1.0 else "\U0001f534"
    lines.append(f"{rr_color} {html_bold('Risk/Reward:')} {risk_reward:.2f}:1")
    lines.append(separator())

    # ── Key Support & Resistance ──
    lines.append(f"\U0001f4ca {html_bold('KEY LEVELS')}")

    if resistance_levels:
        lines.append(f"  {html_bold('Resistance:')}")
        for rl in resistance_levels[:3]:
            r_type = rl.get("type", "N/A")
            r_price = rl.get("price", 0)
            r_dist = rl.get("distance_pct", 0)
            r_strength = rl.get("strength", 0)
            extra_parts = []
            if rl.get("pcr") is not None:
                extra_parts.append(f"PCR:{rl['pcr']:.2f}")
            if rl.get("oi") is not None:
                extra_parts.append(f"OI:{rl['oi']:,.0f}")
            if rl.get("gex") is not None:
                extra_parts.append(f"GEX:{rl['gex']:,.0f}")
            if rl.get("oi_concentration") is not None:
                extra_parts.append(f"OI%:{rl['oi_concentration']:.1f}%")
            extra_str = " | ".join(extra_parts)
            extra_prefix = f" | {extra_str}" if extra_str else ""
            lines.append(
                f"    R{rl.get('level')}: {html_code(format_price(r_price, symbol))} "
                f"| {format_pct(r_dist)} | {r_type} ({r_strength:.0%}){extra_prefix}"
            )

    if support_levels:
        lines.append(f"  {html_bold('Support:')}")
        for sl in support_levels[:3]:
            s_type = sl.get("type", "N/A")
            s_price = sl.get("price", 0)
            s_dist = sl.get("distance_pct", 0)
            s_strength = sl.get("strength", 0)
            extra_parts = []
            if sl.get("pcr") is not None:
                extra_parts.append(f"PCR:{sl['pcr']:.2f}")
            if sl.get("oi") is not None:
                extra_parts.append(f"OI:{sl['oi']:,.0f}")
            if sl.get("gex") is not None:
                extra_parts.append(f"GEX:{sl['gex']:,.0f}")
            if sl.get("oi_concentration") is not None:
                extra_parts.append(f"OI%:{sl['oi_concentration']:.1f}%")
            extra_str = " | ".join(extra_parts)
            extra_prefix = f" | {extra_str}" if extra_str else ""
            lines.append(
                f"    S{sl.get('level')}: {html_code(format_price(s_price, symbol))} "
                f"| {format_pct(s_dist)} | {s_type} ({s_strength:.0%}){extra_prefix}"
            )

    lines.append(separator())

    # ── Options Metrics ──
    lines.append(f"\u2699\ufe0f {html_bold('OPTIONS METRICS')}")

    pcr = options.get("pcr_combined", 0)
    pcr_emoji = "\U0001f7e2" if pcr > 1.2 else "\U0001f534" if pcr < 0.8 else "\U0001f7e1"
    iv_pct = options.get("iv_percentile", 0)
    iv_state = "HIGH" if iv_pct > 0.75 else "LOW" if iv_pct < 0.25 else "MID"
    gex_regime = options.get("gex_regime", "NEUTRAL")
    dealer_pressure = options.get("dealer_hedge_pressure", "MIXED")
    gamma_flip = options.get("gamma_flip", 0)
    dte = options.get("dte_days", 0)
    expiry_imminent = options.get("expiry_imminent", False)
    sentiment = options.get("combined_sentiment", "NEUTRAL")
    sentiment_score = options.get("sentiment_score", 0)
    contrarian = options.get("is_contrarian_signal", False)

    lines.append(f"  {pcr_emoji} PCR: {html_code(f'{pcr:.3f}')} | IV: {html_code(f'{iv_pct:.1%}')} ({iv_state})")
    lines.append(f"  GEX: {gex_regime} | Dealer: {dealer_pressure}")
    if gamma_flip:
        lines.append(f"  Gamma Flip: {html_code(format_price(gamma_flip, symbol))}")
    lines.append(f"  DTE: {dte:.1f}d {'⚠️ EXPIRY IMMINENT' if expiry_imminent else ''}")
    lines.append(
        f"  Sentiment: {sentiment} ({sentiment_score:+.2f})"
        + (" \U0001f504 CONTRARIAN" if contrarian else "")
    )

    # Wall metrics
    wall_intensity = options.get("wall_intensity", 0)
    wall_imbalance = options.get("wall_imbalance", 0)
    lines.append(f"  Wall Intensity: {wall_intensity:.3f} | Imbalance: {wall_imbalance:+.3f}")

    # Funding rate
    funding = options.get("current_funding_rate", 0)
    funding_extreme = options.get("funding_rate_extreme", False)
    funding_emoji = "\U0001f7e2" if funding < 0 else "\U0001f534" if funding > 0.0003 else "\U0001f7e1"
    lines.append(f"  {funding_emoji} Funding: {funding:.4%} {'⚠️ EXTREME' if funding_extreme else ''}")

    # L/S Ratios
    top_trader_pos = options.get("top_trader_position_ratio", 1.0)
    top_trader_acc = options.get("top_trader_account_ratio", 1.0)
    lines.append(f"  Top Traders \u2014 Pos: {top_trader_pos:.3f} | Acct: {top_trader_acc:.3f}")

    lines.append(separator())

    # ── OI Flow ──
    oi_flow = options.get("oi_flow", {})
    if oi_flow:
        flow_dir = oi_flow.get("flow_direction", "N/A")
        flow_type = oi_flow.get("flow_type", "N/A")
        oi_change = oi_flow.get("oi_change_estimated", 0)
        price_change = oi_flow.get("price_change_pct", 0)

        flow_emoji = {
            "LONG_BUILDUP": "\U0001f7e2",
            "SHORT_BUILDUP": "\U0001f534",
            "LONG_UNWINDING": "\U0001f7e1",
            "SHORT_UNWINDING": "\U0001f7e1",
        }.get(flow_type, "\u26aa")

        lines.append(f"{flow_emoji} {html_bold('OI FLOW:')} {flow_type.replace('_', ' ')}")
        lines.append(f"  OI Change: {format_pct(oi_change)} | Price: {format_pct(price_change)}")

    # ── Whale Activity ──
    if whale:
        lines.append(separator())
        whale_dir = whale.get("whale_direction", "NEUTRAL")
        whale_vol_sent = whale.get("whale_volume_sentiment", "NEUTRAL")
        whale_time = whale.get("whale_time_pattern", "N/A")
        whale_agg = whale.get("whale_aggressive_side", "N/A")
        whale_buy = whale.get("whale_buy_volume", 0)
        whale_sell = whale.get("whale_sell_volume", 0)
        whale_net = whale.get("whale_net_volume", 0)
        whale_score = whale.get("whale_activity_score", 0)
        whale_trades = whale.get("large_trades_count", 0)
        whale_cpr = whale.get("whale_call_put_ratio", 0)
        whale_top_strike = whale.get("whale_top_strike", 0)
        whale_concentration = whale.get("whale_top_strike_concentration", 0)

        whale_dir_emoji = (
            "\U0001f7e2" if whale_dir == "BULLISH"
            else "\U0001f534" if whale_dir == "BEARISH"
            else "\U0001f7e1"
        )

        lines.append(f"\U0001f40b {html_bold('WHALE ACTIVITY')} {whale_dir_emoji}")
        lines.append(f"  Direction: {whale_dir} | Vol Sentiment: {whale_vol_sent}")
        lines.append(f"  Pattern: {str(whale_time).replace('_', ' ')} | Aggressive: {whale_agg}")
        lines.append(
            f"  Buy: {format_volume(whale_buy)} | Sell: {format_volume(whale_sell)} | "
            f"Net: {format_volume(abs(whale_net))} {'(Selling)' if whale_net < 0 else '(Buying)'}"
        )
        lines.append(f"  Activity: {whale_score:.1%} | Large Trades: {whale_trades}")
        if whale_cpr:
            lines.append(
                f"  C/P Ratio: {whale_cpr:.2f} | "
                f"Top Strike: {format_price(whale_top_strike, symbol)} ({whale_concentration:.1%})"
            )

    lines.append(separator())

    # ── Futures Snapshot ──
    if futures:
        price = futures.get("price", 0)
        vol_24h = futures.get("volume_24h", 0)
        oi = futures.get("open_interest", 0)
        fr = futures.get("funding_rate", 0)
        lines.append(
            f"\U0001f4c8 {html_bold('FUTURES')}: {format_price(price, symbol)} | "
            f"Vol: {format_volume(vol_24h)} | OI: {format_volume(oi)} | FR: {fr:.4%}"
        )

    # ── Timestamp ──
    ts = signal.get("timestamp", "")
    sig_id = signal.get("signal_id", "N/A")
    lines.append(f"\n{html_italic(f'Signal: {sig_id}')}")
    lines.append(html_italic(f"Generated: {ts}"))

    return "\n".join(lines)


def format_summary_message(result: Dict[str, Any]) -> str:
    """
    Format a brief execution summary message (sent before individual signals).
    """
    lines = []

    exec_id = result.get("execution_id", "N/A")
    duration = result.get("execution_duration_seconds", 0)
    assets = result.get("assets_analyzed", 0)
    signals = result.get("signals_generated", 0)
    errors = result.get("metadata", {}).get("errors", [])
    api_calls = result.get("metadata", {}).get("api_calls_made", 0)

    lines.append(html_bold("\u26a1 SIGNAL GENERATOR EXECUTION REPORT"))
    lines.append(separator("="))
    lines.append(f"Execution: {html_code(exec_id)}")
    lines.append(f"Duration: {duration:.1f}s | API Calls: {api_calls}")
    lines.append(f"Assets Scanned: {assets} | Signals: {signals}")

    # Selected assets
    selected = result.get("selected_assets", [])
    if selected:
        lines.append("")
        lines.append(html_bold("Selected Assets:"))
        for asset in selected:
            sym = asset.get("symbol", "???")
            rank = asset.get("rank", 0)
            score = asset.get("activity_score", 0)
            driver = asset.get("primary_driver", "UNKNOWN")
            driver_emoji = {
                "WHALE_ACTIVITY": "\U0001f40b",
                "PCR_EXTREME": "\U0001f4c9",
                "OI_CHANGE": "\U0001f4ca",
                "VOLUME_SPIKE": "\U0001f4c8",
                "IV_INTEREST": "\U0001f4a1",
                "TOTAL_VOLUME": "\U0001f4b0",
            }.get(driver, "\u2728")
            lines.append(f"  #{rank} {sym} \u2014 Score: {score:.3f} | Driver: {driver_emoji} {driver}")

    if errors:
        lines.append(f"\n⚠️ Errors: {len(errors)}")

    lines.append(separator("="))
    lines.append("")

    return "\n".join(lines)


def format_all_signals(result: Dict[str, Any]) -> List[str]:
    """
    Format all signals from a result into a list of Telegram-ready HTML messages.
    Returns list of individual signal messages (each under 4096 chars).
    """
    signals = result.get("signals", [])
    total = len(signals)
    messages = []

    for i, signal in enumerate(signals):
        rank = signal.get("asset_rank", i + 1)
        msg = format_signal_message(signal, rank, total)
        # Telegram limit is 4096 chars per message
        if len(msg) > 4090:
            msg = msg[:4090] + "\n<i>…truncated</i>"
        messages.append(msg)

    return messages
