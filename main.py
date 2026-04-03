# ======================================
# ADAPTIVE OTC SIGNAL BOT + 3-STEP MARTINGALE
# FINAL DEPLOY VERSION
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
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

WS_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TZ = pytz.timezone("Africa/Lagos")

# ================================
# MARTINGALE SETTINGS (YOUR 3 STEPS)
# ================================
MARTINGALE_LEVELS = [1, 2, 3]
mg_index = 0

# ================================
# STATE
# ================================
IDLE = "IDLE"
WAIT_RESULT = "WAIT_RESULT"
PAUSED = "PAUSED"

state = IDLE

# ================================
# DATA STORAGE
# ================================
prices = defaultdict(lambda: deque(maxlen=500))
active_pair = None
loss_streak = 0

# ================================
# TIME
# ================================
def now():
    return datetime.now(TZ)

# ================================
# PRICE FEED
# ================================
def on_tick(symbol, price):
    prices[symbol].append(price)

# ================================
# MARKET FILTER
# ================================
def market_ok(symbol):
    data = prices[symbol]

    if len(data) < 60:
        return False

    arr = list(data)[-60:]

    change = arr[-1] - arr[0]
    volatility = np.mean([abs(arr[i] - arr[i-1]) for i in range(1, len(arr))])

    if volatility == 0:
        return False

    strength = abs(change) / volatility

    return strength >= 0.7   # only strong markets allowed

# ================================
# SIGNAL ENGINE
# ================================
def get_signal():
    global active_pair, mg_index

    if state != IDLE:
        return None

    best_symbol = None
    best_score = 0

    for sym in prices:

        if not market_ok(sym):
            continue

        arr = list(prices[sym])[-60:]
        score = (arr[-1] - arr[0]) / (np.mean([abs(arr[i]-arr[i-1]) for i in range(1, len(arr))]) + 1e-6)

        if abs(score) > abs(best_score):
            best_score = score
            best_symbol = sym

    if not best_symbol or abs(best_score) < 0.8:
        return None

    direction = "BUY" if best_score > 0 else "SELL"

    active_pair = best_symbol
    mg_index = 0

    return {
        "pair": best_symbol,
        "direction": direction
    }

# ================================
# SEND SIGNAL
# ================================
def send_signal(pair, direction, mg_level):
    global state

    entry_time = now() + timedelta(minutes=2)

    msg = (
        f"🚨 OTC SIGNAL\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n"
        f"MARTINGALE LEVEL: {mg_level + 1}/3\n\n"
        f"ENTRY: {entry_time.strftime('%H:%M:%S')}"
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "WIN", "callback_data": "WIN"},
            {"text": "LOSS", "callback_data": "LOSS"}
        ]]
    }

    requests.post(
        f"{API_URL}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "reply_markup": keyboard}
    )

    state = WAIT_RESULT

# ================================
# RESULT HANDLER (3 MARTINGALE STEPS)
# ================================
def handle_result(result):
    global state, mg_index, loss_streak

    if result == "WIN":
        mg_index = 0
        loss_streak = 0
        state = IDLE
        return

    # LOSS HANDLING
    loss_streak += 1

    if mg_index < len(MARTINGALE_LEVELS) - 1:
        mg_index += 1
        state = IDLE  # retry next martingale level
    else:
        # STOP AFTER 3 FAILS
        mg_index = 0
        loss_streak = 0
        state = PAUSED

# ================================
# TELEGRAM LISTENER
# ================================
async def telegram_listener():
    last_update = None

    while True:
        try:
            url = f"{API_URL}/getUpdates"
            if last_update:
                url += f"?offset={last_update+1}"

            res = requests.get(url).json()

            for u in res.get("result", []):
                last_update = u["update_id"]

                if "callback_query" in u:
                    data = u["callback_query"]["data"]

                    if data == "WIN":
                        handle_result("WIN")
                    elif data == "LOSS":
                        handle_result("LOSS")

            await asyncio.sleep(1)

        except:
            await asyncio.sleep(2)

# ================================
# WS CONNECT
# ================================
async def connect():
    async with websockets.connect(WS_URL) as ws:

        await ws.send(json.dumps({"active_symbols": "brief"}))
        data = json.loads(await ws.recv())

        symbols = [
            s["symbol"]
            for s in data.get("active_symbols", [])
            if "frx" in s["symbol"]
        ]

        for s in symbols:
            await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

        async for msg in ws:
            data = json.loads(msg)

            if "tick" in data:
                sym = data["tick"]["symbol"]
                price = float(data["tick"]["quote"])
                on_tick(sym, price)

# ================================
# ENGINE LOOP
# ================================
async def engine():
    global state

    while True:
        signal = get_signal()

        if signal:
            send_signal(signal["pair"], signal["direction"], mg_index)

        await asyncio.sleep(2)

# ================================
# MAIN
# ================================
async def main():
    await asyncio.gather(
        connect(),
        engine(),
        telegram_listener()
    )

if __name__ == "__main__":
    asyncio.run(main())
