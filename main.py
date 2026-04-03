# ======================================
# POCKET OPTION OTC SIGNAL BOT
# RANKING + SAFE ENGINE + MARTINGALE
# + PULLBACK + TREND STABILITY FILTER
# + PROTECTION SYSTEM (ANTI-LOSS)
# + MANUAL FEEDBACK + RECONNECT
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

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

ENTRY_DELAY = 2
EXPIRY_MINUTES = 2

MG_STEP = 2
MAX_MG = 3

MAX_PRICES = 700
WARMUP_TIME = 180

BLOCKED_PAIRS = [
    "frxUSDNOK","frxGBPNOK","frxUSDPLN",
    "frxGBPNZD","frxUSDSEK"
]

# ================================
# PROTECTION SETTINGS
# ================================
MAX_LOSS_STREAK = 2
PAUSE_AFTER_LOSS = 600

# ================================
# STATE
# ================================
prices = defaultdict(lambda: deque(maxlen=MAX_PRICES))
bot_start_time = datetime.now(TIMEZONE)

focused_pair = None
focus_start_time = 0
next_trade_allowed_time = 0

trade_history = deque(maxlen=20)
loss_streak = 0
pause_until = 0

# 🔥 NEW: WAIT FOR USER FEEDBACK
waiting_feedback = False

# ================================
# UTIL
# ================================
def warmup_done():
    return (datetime.now(TIMEZONE) - bot_start_time).seconds > WARMUP_TIME

def cooldown_ok():
    return datetime.now().timestamp() > next_trade_allowed_time

def protection_ok():
    return datetime.now().timestamp() > pause_until

def valid_session():
    hour = datetime.now(TIMEZONE).hour
    return 8 <= hour <= 22

# ================================
# RESULT TRACKING
# ================================
def record_trade_result(result):
    global loss_streak, pause_until, waiting_feedback

    trade_history.append(result)

    if result == "LOSS":
        loss_streak += 1
    else:
        loss_streak = 0

    if loss_streak >= MAX_LOSS_STREAK:
        pause_until = datetime.now().timestamp() + PAUSE_AFTER_LOSS
        loss_streak = 0

    waiting_feedback = False  # 🔥 unlock bot

# ================================
# TELEGRAM BUTTON HANDLER
# ================================
async def listen_for_buttons():
    last_update_id = None

    while True:
        try:
            url = f"{TELEGRAM_API}/getUpdates"
            if last_update_id:
                url += f"?offset={last_update_id + 1}"

            res = requests.get(url, timeout=10).json()

            for update in res.get("result", []):
                last_update_id = update["update_id"]

                if "callback_query" in update:
                    data = update["callback_query"]["data"]

                    if data == "WIN":
                        record_trade_result("WIN")

                    elif data == "LOSS":
                        record_trade_result("LOSS")

            await asyncio.sleep(1)

        except:
            await asyncio.sleep(3)

# ================================
# TICK INPUT
# ================================
def on_tick(pair, price):
    prices[pair].append(price)

# ================================
# PULLBACK DETECTION
# ================================
def detect_pullback(arr):
    if len(arr) < 30:
        return 0

    recent = arr[-30:]
    start = recent[0]
    mid = recent[15]
    end = recent[-1]

    trend = end - start
    moves = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
    volatility = np.mean(moves)

    if volatility == 0:
        return 0

    price_range = max(recent) - min(recent)

    if price_range < volatility * 6:
        return 0

    pullback = mid - start

    if trend > 0 and pullback < 0:
        return 1

    if trend < 0 and pullback > 0:
        return -1

    return 0

# ================================
# SCORING
# ================================
def score_pair(data):
    if len(data) < 50:
        return 0

    arr = list(data)[-50:]
    trend = arr[-1] - arr[0]

    moves = [abs(arr[i] - arr[i - 1]) for i in range(1, len(arr))]
    volatility = np.mean(moves)

    if volatility == 0:
        return 0

    price_range = max(arr) - min(arr)

    if price_range < volatility * 6:
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
# SIGNAL ENGINE
# ================================
def generate_signal():
    global focused_pair, focus_start_time

    ranked = rank_pairs()

    if not ranked:
        return None

    pair, score = ranked[0]

    if abs(score) < 0.3:
        return None

    now = datetime.now().timestamp()

    if focused_pair is None:
        focused_pair = pair
        focus_start_time = now
        return None

    if pair != focused_pair:
        focused_pair = pair
        focus_start_time = now
        return None

    if now - focus_start_time < 15:
        return None

    arr = list(prices[pair])
    pull = detect_pullback(arr)

    if pull == 0:
        return None

    direction = "BUY" if pull == 1 else "SELL"

    focused_pair = None

    return {"pair": pair, "direction": direction}

# ================================
# SEND SIGNAL (WITH BUTTONS)
# ================================
def send_signal(pair, direction):
    global next_trade_allowed_time, waiting_feedback

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

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ WIN", "callback_data": "WIN"},
            {"text": "❌ LOSS", "callback_data": "LOSS"}
        ]]
    }

    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": msg,
                "reply_markup": keyboard
            },
            timeout=10
        )
    except:
        pass

    total_wait = (ENTRY_DELAY + EXPIRY_MINUTES) * 60
    next_trade_allowed_time = datetime.now().timestamp() + total_wait

    waiting_feedback = True  # 🔥 lock bot

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
# MAIN LOOP (RECONNECT SAFE)
# ================================
async def monitor():
    global waiting_feedback

    while True:
        try:
            if waiting_feedback:
                await asyncio.sleep(1)
                continue

            if not valid_session():
                await asyncio.sleep(10)
                continue

            if not warmup_done():
                continue

            if not cooldown_ok():
                await asyncio.sleep(2)
                continue

            if not protection_ok():
                await asyncio.sleep(5)
                continue

            symbols = await load_symbols()

            if not symbols:
                await asyncio.sleep(5)
                continue

            while True:  # 🔥 reconnect loop
                try:
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

                except:
                    await asyncio.sleep(2)  # reconnect

        except:
            await asyncio.sleep(3)

# ================================
# START
# ================================
async def main():
    await asyncio.gather(
        monitor(),
        listen_for_buttons()
    )

if __name__ == "__main__":
    asyncio.run(main())
