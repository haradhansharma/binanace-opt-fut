#!/bin/bash
# Binance Options Signal Generator + Telegram Delivery
# Runs the signal generator and sends results to Telegram

set -euo pipefail

PROJECT_DIR="/home/haradhan/workspace/binanace-opt-fut"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
CONFIG="$PROJECT_DIR/config/config.yaml"
LOG_FILE="$PROJECT_DIR/logs/signal_delivery.log"

# Telegram Bot Config
BINANCE_BOT_TOKEN="8974923019:AAEg0yQH4PBDmvpBZZwx7mK1OCsRVopYRsY"
BINANCE_CHAT_ID="5529887983"

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/scripts"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Step 1: Run signal generator
log "Running signal generator..."
SIGNAL_JSON=$(cd "$PROJECT_DIR" && $VENV_PYTHON -m binance_signal_generator --config "$CONFIG" --quiet 2>/dev/null) || {
    log "ERROR: Signal generator failed"
    # Send failure notification
    curl -s -X POST "https://api.telegram.org/bot${BINANCE_BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\":\"${BINANCE_CHAT_ID}\",\"text\":\"⚠️ Signal generator failed. Check logs.\",\"parse_mode\":\"Markdown\"}" > /dev/null 2>&1 || true
    exit 1
}

log "Signal received. Formatting..."

# Step 2: Parse and format with Python
FORMATTED_MSG=$(echo "$SIGNAL_JSON" | $VENV_PYTHON -c "
import sys, json

data = json.load(sys.stdin)
signals = data.get('signals', [])
timestamp = data.get('timestamp', 'N/A')[:19]

if not signals:
    print(f'📊 Binance Signal Scan\nNo trade signals met threshold.\n⏱ {timestamp}')
    sys.exit(0)

messages = []
for sig in signals:
    symbol = sig['symbol']
    rank = sig.get('asset_rank', '?')
    direction = sig['direction']
    confidence = sig.get('confidence_score', 0) * 100
    strength = sig.get('signal_strength', 'N/A')
    rr = sig.get('risk_reward_ratio', 0)

    entry = sig.get('entry_zone', {})
    sl = sig.get('stop_loss', {})
    tps = sig.get('take_profit_levels', [])

    whale = sig.get('whale_metrics', {})
    opts = sig.get('options_metrics', {})

    dir_emoji = '🟢' if direction == 'LONG' else '🔴' if direction == 'SHORT' else '⚪'
    rr_warn = ' ⚠️ LOW R:R' if rr < 1.0 else ''

    tp_lines = ''
    for tp in tps:
        tp_lines += f\"🎯 TP{tp['level']}: {tp['price']:,.1f} (+{tp['distance_pct']:.1f}%)\n\"

    whale_dir = whale.get('whale_direction', 'N/A')
    whale_net = whale.get('whale_net_volume', 0)
    whale_emoji = '🟢' if whale_dir == 'BULLISH' else '🔴' if whale_dir == 'BEARISH' else '⚪'

    pcr = opts.get('pcr_combined', 0)
    iv = opts.get('iv_percentile', 0) * 100
    sentiment = opts.get('combined_sentiment', 'N/A')
    gex = opts.get('gex_regime', 'N/A')
    dealer = opts.get('dealer_hedge_pressure', 'N/A')

    msg = f\"\"\"🔔 Binance Options Signal

{dir_emoji} #{rank} {symbol} | {direction}
━━━━━━━━━━━━━━━━━━━━
📈 Entry: {entry.get('ideal', 0):,.1f}
🛑 SL: {sl.get('price', 0):,.1f} ({sl.get('distance_pct', 0):.1f}%)
{tp_lines}📊 Confidence: {confidence:.0f}% ({strength})
⚖️ R:R: {rr:.2f}{rr_warn}

🐋 Whale: {whale_emoji} {whale_dir} | Net: {whale_net:+,.0f}
📊 PCR: {pcr:.2f} | IV: {iv:.0f}%
🎭 Sentiment: {sentiment} | GEX: {gex}
🏦 Dealer: {dealer}

⏱ {timestamp}\"\"\"
    messages.append(msg)

combined = '\n━━━━━━━━━━━━━━━━━━━━\n'.join(messages)
if len(combined) <= 4090:
    print(combined)
else:
    # Send first signal if too long
    print(messages[0])
" 2>&1)

if [ -z "$FORMATTED_MSG" ]; then
    log "No message content."
    exit 0
}

log "Sending to Telegram (binance bot)..."

# Step 3: Send to Telegram via Python (proper JSON escaping)
echo "$FORMATTED_MSG" | $VENV_PYTHON -c "
import sys, json, urllib.request, urllib.error

message = sys.stdin.read().strip()
payload = json.dumps({
    'chat_id': '${BINANCE_CHAT_ID}',
    'text': message,
    'parse_mode': 'Markdown'
}).encode('utf-8')

req = urllib.request.Request(
    'https://api.telegram.org/bot${BINANCE_BOT_TOKEN}/sendMessage',
    data=payload,
    headers={'Content-Type': 'application/json'}
)

try:
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    if result.get('ok'):
        print('SENT_OK')
    else:
        print(f'SEND_FAILED: {result}')
except urllib.error.URLError as e:
    print(f'NETWORK_ERROR: {e}')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1 | while read line; do log "$line"; done

log "Done."
