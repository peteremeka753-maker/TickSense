# ======================================
# POCKET OPTION OTC SIGNAL BOT
# RANKING + SAFE ENGINE + MARTINGALE
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
from collections import defaultdict, deque

# ================================
# CONFIG
# ================================
BOT_TOKEN = "8379555524:AAEPO3_ZQ0aHFpzOLr40hyHig89LxuJS7i4"
CHAT_ID = "6918721957"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

ENTRY_DELAY = 2
EXPIRY_MINUTES = 2
COOLDOWN_SECONDS = 60   # 🔥 reduced

# 🔥 MARTINGALE
MG_STEP = 2
MAX_MG = 3

MAX_PRICES = 700
WARMUP_TIME = 180

BLOCKED_PAIRS = [
    "frxUSDNOK","frxGBPNOK","frxUSDPLN",
    "frxGBPNZD","frxUSDSEK"
]

# ================================
# STATE
# ================================
prices = defaultdict(lambda: deque(maxlen=MAX_PRICES))
last_trade_time = 0
bot_start_time = datetime.now(TIMEZONE)

# 🔥 FOCUS SYSTEM
focused_pair = None
focus_start_time = 0

# ================================
# UTIL
# ================================
def warmup_done():
    return (datetime.now(TIMEZONE) - bot_start_time).seconds > WARMUP_TIME

def cooldown_ok():
    return (datetime.now().timestamp() - last_trade_time) > COOLDOWN_SECONDS

def valid_session():
    hour = datetime.now(TIMEZONE).hour
    return 8 <= hour <= 22

# ================================
# TICK INPUT
# ================================
def on_tick(pair, price):
    prices[pair].append(price)

# ================================
# SCORING
# ================================
def score_pair(data):
    if len(data) < 30:
        return 0

    arr = list(data)[-30:]
    trend = arr[-1] - arr[0]
    moves = [abs(arr[i] - arr[i - 1]) for i in range(1, len(arr))]
    volatility = np.mean(moves)

    if volatility == 0:
        return 0

    return trend / volatility

# ================================
# RANKING
# ================================
def rank_pairs():
    scored = []

    for pair, data in prices.items():
        if pair in BLOCKED_PAIRS:
            continue

        s = score_pair(data)
        scored.append((pair, s))

    scored.sort(key=lambda x: abs(x[1]), reverse=True)
    return scored

# ================================
# SIGNAL ENGINE (FOCUS + WAIT)
# ================================
def generate_signal():
    global focused_pair, focus_start_time

    ranked = rank_pairs()

    if not ranked:
        return None

    pair, score = ranked[0]

    # 🔥 relaxed threshold
    if abs(score) < 0.3:
        return None

    now = datetime.now().timestamp()

    # LOCK PAIR
    if focused_pair is None:
        focused_pair = pair
        focus_start_time = now
        return None

    # RESET if changed
    if pair != focused_pair:
        focused_pair = pair
        focus_start_time = now
        return None

    # WAIT before entry
    if now - focus_start_time < 15:
        return None

    direction = "BUY" if score > 0 else "SELL"

    focused_pair = None

    return {
        "pair": pair,
        "direction": direction
    }

# ================================
# SEND SIGNAL (WITH MARTINGALE)
# ================================
def send_signal(pair, direction):
    global last_trade_time

    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    mg_times = [
        entry_time + timedelta(minutes=MG_STEP * i)
        for i in range(1, MAX_MG + 1)
    ]

    msg = (
        f"🚨 OTC SIGNAL BOT\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY: {entry_time.strftime('%I:%M %p')}\n"
        f"EXPIRY: {EXPIRY_MINUTES} min\n\n"
        f"📊 MARTINGALE\n"
        f"🔹 L1 → {mg_times[0].strftime('%I:%M %p')}\n"
        f"🔹 L2 → {mg_times[1].strftime('%I:%M %p')}\n"
        f"🔹 L3 → {mg_times[2].strftime('%I:%M %p')}"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

    last_trade_time = datetime.now().timestamp()

# ================================
# LOAD SYMBOLS
# ================================
async def load_symbols():
    try:
        async with websockets.connect(DERIV_WS, ping_interval=20) as ws:
            await ws.send(json.dumps({"active_symbols": "brief"}))
            data = json.loads(await ws.recv())

            return [
                s["symbol"]
                for s in data.get("active_symbols", [])
                if s["symbol"].startswith("frx")
                and s["symbol"] not in BLOCKED_PAIRS
            ]
    except:
        return []

# ================================
# MAIN LOOP
# ================================
async def monitor():
    while True:
        try:

            if not valid_session():
                await asyncio.sleep(10)
                continue

            if not warmup_done():
                continue

            if not cooldown_ok():
                await asyncio.sleep(2)
                continue

            symbols = await load_symbols()

            if not symbols:
                await asyncio.sleep(5)
                continue

            async with websockets.connect(DERIV_WS, ping_interval=20) as ws:

                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for msg in ws:
                    data = json.loads(msg)

                    if "tick" not in data:
                        continue

                    pair = data["tick"]["symbol"]
                    price = float(data["tick"]["quote"])

                    on_tick(pair, price)

                    signal = generate_signal()

                    if signal:
                        send_signal(signal["pair"], signal["direction"])
                        break

        except Exception:
            await asyncio.sleep(3)

# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
