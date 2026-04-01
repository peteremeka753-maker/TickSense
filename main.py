# ======================================
# POCKET OPTION OTC SIGNAL BOT
# PRICE ACTION VERSION + STABILITY LAYER
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz

# ================================
# TELEGRAM SETTINGS
# ================================
BOT_TOKEN = "8379555524:AAEPO3_ZQ0aHFpzOLr40hyHig89LxuJS7i4"
CHAT_ID = "6918721957"

# ================================
# GENERAL SETTINGS
# ================================
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

ENTRY_DELAY = 2
MG_STEP = 2
MAX_MG_STEPS = 3
EXPIRY_MINUTES = 2

MAX_PRICES = 700
TICK_CONFIRMATION = 3

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

# ================================
# STATE
# ================================
prices = {}
tick_confirm = {}
active_signal = {"pair": None, "expiry_time": None}

# ================================
# STABILITY / RISK ENGINE
# ================================
bad_market_counter = 0
PAUSE_THRESHOLD = 10
PAUSED = False


def risk_engine(direction):
    global bad_market_counter, PAUSED

    if direction is None:
        bad_market_counter += 1
    else:
        bad_market_counter = max(0, bad_market_counter - 1)

    if bad_market_counter >= PAUSE_THRESHOLD:
        PAUSED = True

    if PAUSED and bad_market_counter <= 3:
        PAUSED = False

    return PAUSED


# ================================
# PRICE ACTION CORE
# ================================
def swing_highs_lows(prices, lookback=8):
    highs = []
    lows = []

    for i in range(lookback, len(prices) - lookback):
        window = prices[i - lookback:i + lookback]

        if prices[i] == max(window):
            highs.append((i, prices[i]))

        if prices[i] == min(window):
            lows.append((i, prices[i]))

    return highs, lows


def market_bias(price_list):
    if len(price_list) < 60:
        return None

    highs, lows = swing_highs_lows(price_list[-200:], 8)

    if len(highs) < 2 or len(lows) < 2:
        return None

    last_high = highs[-1][1]
    prev_high = highs[-2][1]
    last_low = lows[-1][1]
    prev_low = lows[-2][1]

    if last_high > prev_high and last_low > prev_low:
        return "BUY"

    if last_high < prev_high and last_low < prev_low:
        return "SELL"

    return None


def rejection_signal(price_list):
    if len(price_list) < 10:
        return None

    last = price_list[-1]
    prev = price_list[-2]
    prev2 = price_list[-3]

    body = abs(prev - prev2)
    wick = abs(last - prev)

    if body == 0:
        return None

    if wick > body * 1.5:
        if last < prev:
            return "BUY"
        if last > prev:
            return "SELL"

    return None


# ================================
# SIGNAL LOCK
# ================================
def signal_active():
    if active_signal["expiry_time"] is None:
        return False
    return datetime.now(TIMEZONE) < active_signal["expiry_time"]


def register_signal(pair):
    now = datetime.now(TIMEZONE)
    total_lock = ENTRY_DELAY + (MG_STEP * MAX_MG_STEPS) + EXPIRY_MINUTES
    active_signal["pair"] = pair
    active_signal["expiry_time"] = now + timedelta(minutes=total_lock)


# ================================
# TELEGRAM SIGNAL
# ================================
def send_signal(pair, direction, score):
    if signal_active() or PAUSED:
        return

    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    level1 = entry_time
    level2 = entry_time + timedelta(minutes=MG_STEP)
    level3 = entry_time + timedelta(minutes=MG_STEP * 2)

    register_signal(pair)

    msg = (
        f"🚨 TRADE SIGNAL (PRICE ACTION)\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY TIME: {entry_time.strftime('%I:%M %p')}\n\n"
        f"📊 MARTINGALE LEVELS\n"
        f"🔹 Level 1 → {level1.strftime('%I:%M %p')}\n"
        f"🔹 Level 2 → {level2.strftime('%I:%M %p')}\n"
        f"🔹 Level 3 → {level3.strftime('%I:%M %p')}\n\n"
        f"CONFIDENCE: {score}%\n"
        f"{'PAUSED MODE ACTIVE' if PAUSED else 'ACTIVE MODE'}"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass


# ================================
# SYMBOL LOADING
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
    global PAUSED

    while True:
        symbols = await load_symbols()

        if not symbols:
            await asyncio.sleep(5)
            continue

        for s in symbols:
            prices[s] = []
            tick_confirm[s] = {"count": 0, "direction": None}

        print("BOT STARTED (STABLE PRICE ACTION MODE)")

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

                    prices[pair].append(price)

                    if len(prices[pair]) > MAX_PRICES:
                        prices[pair].pop(0)

                    direction = market_bias(prices[pair])

                    if not direction:
                        direction = rejection_signal(prices[pair])

                    PAUSED = risk_engine(direction)

                    if not direction or PAUSED:
                        continue

                    if tick_confirm[pair]["direction"] == direction:
                        tick_confirm[pair]["count"] += 1
                    else:
                        tick_confirm[pair]["direction"] = direction
                        tick_confirm[pair]["count"] = 1

                    if tick_confirm[pair]["count"] >= TICK_CONFIRMATION:
                        send_signal(pair, direction, 92)
                        tick_confirm[pair] = {"count": 0, "direction": None}

        except Exception:
            await asyncio.sleep(3)


# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
