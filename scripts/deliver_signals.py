#!/usr/bin/env python3
"""
Binance Options Signal Generator + Telegram Delivery (HTML Formatter)
Runs the signal generator and sends rich HTML-formatted results to Telegram.

Uses html_formatter.py for Telegram HTML parse_mode messages.
Falls back to plain text if html_formatter is not available.
"""

import subprocess
import sys
import json
import urllib.request
import urllib.error
import os
from datetime import datetime

# Config
PROJECT_DIR = "/home/haradhan/workspace/binanace-opt-fut"
VENV_PYTHON = os.path.join(PROJECT_DIR, "venv", "bin", "python")
CONFIG = os.path.join(PROJECT_DIR, "config", "config.yaml")
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "signal_delivery.log")
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")

# Add scripts dir to path for html_formatter import
sys.path.insert(0, SCRIPTS_DIR)

# Telegram bots
TELEGRAM_BOTS = [
    {
        "name": "binance_signal",
        "token": "8974923019:AAEg0yQH4PBDmvpBZZwx7mK1OCsRVopYRsY",
        "chat_id": "5529887983",
    }
]

os.makedirs(os.path.join(PROJECT_DIR, "logs"), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line)


def run_signal_generator():
    log("Running signal generator...")
    result = subprocess.run(
        [VENV_PYTHON, "-m", "binance_signal_generator", "--config", CONFIG, "--quiet"],
        capture_output=True, text=True, timeout=120,
        cwd=PROJECT_DIR
    )
    if result.returncode != 0:
        log(f"Signal generator failed (exit {result.returncode}): {result.stderr[:200]}")
        return None
    return result.stdout.strip()


def format_message(json_str):
    """Format signal JSON into Telegram HTML messages using html_formatter."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e}")
        return None

    signals = data.get("signals", [])

    if not signals:
        return "📊 Binance Signal Scan\nNo trade signals met threshold.\n" + data.get("timestamp", "N/A")[:19]

    try:
        from html_formatter import format_all_signals
        messages = format_all_signals(data)
        if messages:
            return messages[0] if len(messages) == 1 else messages
    except ImportError:
        log("html_formatter not available, using plain text fallback")

    # Fallback: plain text (original formatter)
    return _format_plain_fallback(data)


def _format_plain_fallback(data):
    """Original plain text formatter as fallback."""
    signals = data.get("signals", [])
    timestamp = data.get("timestamp", "N/A")[:19]
    messages = []

    for sig in signals:
        symbol = sig["symbol"]
        rank = sig.get("asset_rank", "?")
        direction = sig["direction"]
        confidence = sig.get("confidence_score", 0) * 100
        strength = sig.get("signal_strength", "N/A")
        rr = sig.get("risk_reward_ratio", 0)
        entry = sig.get("entry_zone", {})
        sl = sig.get("stop_loss", {})
        tps = sig.get("take_profit_levels", [])
        supports = sig.get("support_levels", [])
        resistances = sig.get("resistance_levels", [])
        whale = sig.get("whale_metrics", {})
        opts = sig.get("options_metrics", {})
        futures = sig.get("futures_metrics", {})

        dir_emoji = "🟢" if direction == "LONG" else "🔴" if direction == "SHORT" else "⚪"
        rr_warn = " ⚠️ LOW R:R" if rr < 1.0 else ""

        lines = []
        lines.append("🔔 Binance Options Signal")
        lines.append("")
        lines.append(f"{dir_emoji} #{rank} {symbol} | {direction}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("📈 Entry Zone")
        lines.append(f"  Min: {entry.get('min', 0):,.1f} | Max: {entry.get('max', 0):,.1f}")
        lines.append(f"  Ideal: {entry.get('ideal', 0):,.1f}")
        lines.append("")
        lines.append("🛑 Stop Loss")
        lines.append(f"  Price: {sl.get('price', 0):,.1f} ({sl.get('distance_pct', 0):.1f}%)")
        sl_detail = f"[{sl.get('type', '')}]"
        if sl.get("source_strike"):
            sl_detail += f" Strike:{sl['source_strike']:,.1f}"
        if sl.get("confidence"):
            sl_detail += f" Conf:{sl['confidence']:.0%}"
        lines.append(f"  {sl_detail}")
        lines.append("")
        lines.append("🎯 Take Profit Levels")
        for tp in tps:
            lines.append(
                f"  TP{tp['level']}: {tp.get('price', 0):,.1f} "
                f"(+{tp.get('distance_pct', 0):.1f}%) "
                f"R:{tp.get('ratio', 0):.1f} [{tp.get('type', '')}]"
            )
        lines.append(f"  Confidence: {confidence:.0f}% ({strength})")
        lines.append(f"  R:R: {rr:.2f}{rr_warn}")

        if supports:
            lines.append("")
            lines.append("🛡️ Support Levels")
            for s in supports:
                pcr_str = f" PCR:{s['pcr']:.2f}" if s.get("pcr") is not None else ""
                oi_str = f" OI:{s['oi']:,.0f}" if s.get("oi") is not None else ""
                lines.append(
                    f"  S {s.get('price', 0):,.1f} "
                    f"({s.get('distance_pct', 0):+.1f}%)"
                    f"{pcr_str}{oi_str} [{s.get('type', '')}]"
                )

        if resistances:
            lines.append("")
            lines.append("🔺 Resistance Levels")
            for r in resistances:
                pcr_str = f" PCR:{r['pcr']:.2f}" if r.get("pcr") is not None else ""
                oi_str = f" OI:{r['oi']:,.0f}" if r.get("oi") is not None else ""
                lines.append(
                    f"  R {r.get('price', 0):,.1f} "
                    f"({r.get('distance_pct', 0):+.1f}%)"
                    f"{pcr_str}{oi_str} [{r.get('type', '')}]"
                )

        lines.append("")
        lines.append("🐋 Whale Activity")
        lines.append(f"  Dir: {whale.get('whale_direction', 'N/A')}")
        lines.append(f"  Buy: {whale.get('whale_buy_volume', 0):,.0f} | Sell: {whale.get('whale_sell_volume', 0):,.0f}")
        lines.append(f"  Net: {whale.get('whale_net_volume', 0):+,.0f} | Score: {whale.get('whale_activity_score', 0):.2f}")
        lines.append(f"  Large Trades: {whale.get('large_trades_count', 0)}")

        lines.append("")
        lines.append("📊 Options Data")
        lines.append(f"  PCR: {opts.get('pcr_combined', 0):.2f} | IV: {opts.get('iv_percentile', 0) * 100:.0f}%")
        lines.append(f"  Sentiment: {opts.get('combined_sentiment', 'N/A')} | GEX: {opts.get('gex_regime', 'N/A')}")
        lines.append(f"  Dealer: {opts.get('dealer_hedge_pressure', 'N/A')}")
        lines.append(f"  Max Pain Dist: {opts.get('max_pain_distance', 0):+.1f}%")
        lines.append(f"  Gamma Flip: {(opts.get('gamma_flip') or 0):,.0f} | Risk: {(opts.get('gamma_risk_score') or 0):.2f}")
        lines.append(f"  DTE: {opts.get('dte_days', 0):.0f}d | Wall Int: {opts.get('wall_intensity', 0):.3f}")
        lines.append(f"  Wall Imb: {opts.get('wall_imbalance', 0):.3f}")
        lines.append(f"  Top Trader Pos: {opts.get('top_trader_position_ratio', 0):.2f} | Acc: {opts.get('top_trader_account_ratio', 0):.2f}")
        lines.append(f"  Funding: {opts.get('current_funding_rate', 0):.4f}")

        lines.append("")
        lines.append("💹 Futures")
        lines.append(f"  Price: {futures.get('price', 0):,.1f}")
        lines.append(f"  Vol 24h: {futures.get('volume_24h', 0):,.0f} | OI: {futures.get('open_interest', 0):,.0f}")
        lines.append(f"  Funding: {futures.get('funding_rate', 0):.4f}")

        lines.append("")
        lines.append(f"⏱ {timestamp}")

        messages.append("\n".join(lines))

    combined = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(messages)
    if len(combined) <= 4090:
        return combined
    else:
        return messages[0] + f"\n\n⚠️ {len(messages)} signals generated. Showing first only."


def send_telegram(token, chat_id, message):
    """Send a message to Telegram using HTML parse mode."""
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        if result.get("ok"):
            return True, "OK"
        else:
            return False, str(result)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    json_output = run_signal_generator()
    if json_output is None:
        for bot in TELEGRAM_BOTS:
            send_telegram(bot["token"], bot["chat_id"],
                         "⚠️ Signal generator failed. Check logs.")
        sys.exit(1)

    message = format_message(json_output)
    if message is None:
        log("Failed to format message.")
        sys.exit(1)

    if not message:
        log("No message content.")
        sys.exit(0)

    # Handle both single string and list of messages
    if isinstance(message, list):
        messages = message
    else:
        messages = [message]

    log(f"Formatted {len(messages)} message(s). Sending...")

    for bot in TELEGRAM_BOTS:
        for i, msg in enumerate(messages):
            ok, detail = send_telegram(bot["token"], bot["chat_id"], msg)
            if ok:
                log(f"✅ Sent message {i+1}/{len(messages)} to {bot['name']}")
            else:
                log(f"❌ Failed message {i+1} to {bot['name']}: {detail}")
                # Try sending without HTML parse_mode as fallback
                log("Retrying without HTML parse_mode...")
                payload = json.dumps({
                    "chat_id": bot["chat_id"],
                    "text": msg,
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{bot['token']}/sendMessage",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                try:
                    resp = urllib.request.urlopen(req, timeout=15)
                    result = json.loads(resp.read())
                    if result.get("ok"):
                        log(f"✅ Sent message {i+1} (plain text fallback)")
                    else:
                        log(f"❌ Plain text fallback also failed: {result}")
                except Exception as e:
                    log(f"❌ Plain text fallback error: {e}")

    log("Delivery complete.")


if __name__ == "__main__":
    main()
