# ======================================
# POCKET OPTION OTC SIGNAL BOT
# PRICE ACTION + STABILITY + PO ENTRY FIX
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz
import time

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

# 🔥 NEW (Pocket Option Fix)
ENTRY_CONFIRMATION_SECONDS = 7
MOMENTUM_LOOKBACK = 5

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

# ================================
# STATE
# ================================
prices = {}
tick_confirm = {}
active_signal = {"pair": None, "expiry_time": None}

# ================================
# PRICE ACTION
# ================================
def swing_highs_lows(prices, lookback=8):
    highs, lows = [], []

    for i in range(lookback, len(prices)-lookback):
        window = prices[i-lookback:i+lookback]

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

    if highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]:
        return "BUY"

    if highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]:
        return "SELL"

    return None


def rejection_signal(price_list):
    if len(price_list) < 10:
        return None

    last, prev, prev2 = price_list[-1], price_list[-2], price_list[-3]

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
# 🔥 MOMENTUM FILTER (NEW)
# ================================
def momentum_ok(price_list, direction):
    if len(price_list) < MOMENTUM_LOOKBACK:
        return False

    recent = price_list[-MOMENTUM_LOOKBACK:]

    # check movement direction
    movement = recent[-1] - recent[0]

    if direction == "BUY" and movement < 0:
        return False

    if direction == "SELL" and movement > 0:
        return False

    return True

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
# TELEGRAM
# ================================
def send_signal(pair, direction):
    if signal_active():
        return

    # 🔥 ENTRY CONFIRMATION DELAY
    time.sleep(ENTRY_CONFIRMATION_SECONDS)

    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    mg_times = [
        entry_time + timedelta(minutes=MG_STEP*i)
        for i in range(1, MAX_MG_STEPS+1)
    ]

    register_signal(pair)

    msg = (
        f"🚨 TRADE SIGNAL\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY: {entry_time.strftime('%I:%M %p')}\n"
        f"EXPIRY: {EXPIRY_MINUTES} min\n\n"
        f"📊 MARTINGALE\n"
        f"🔹 L1 → {mg_times[0].strftime('%I:%M %p')}\n"
        f"🔹 L2 → {mg_times[1].strftime('%I:%M %p')}\n"
        f"🔹 L3 → {mg_times[2].strftime('%I:%M %p')}"
    )

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

# ================================
# SYMBOLS
# ================================
async def load_symbols():
    try:
        async with websockets.connect(DERIV_WS) as ws:
            await ws.send(json.dumps({"active_symbols":"brief"}))
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
        symbols = await load_symbols()

        if not symbols:
            await asyncio.sleep(5)
            continue

        for s in symbols:
            prices[s] = []
            tick_confirm[s] = {"count": 0, "direction": None}

        print("BOT STARTED (PO FIX MODE)")

        async with websockets.connect(DERIV_WS) as ws:
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

                if not direction:
                    continue

                # 🔥 APPLY MOMENTUM FILTER
                if not momentum_ok(prices[pair], direction):
                    continue

                # confirmation
                if tick_confirm[pair]["direction"] == direction:
                    tick_confirm[pair]["count"] += 1
                else:
                    tick_confirm[pair]["direction"] = direction
                    tick_confirm[pair]["count"] = 1

                if tick_confirm[pair]["count"] >= TICK_CONFIRMATION:
                    send_signal(pair, direction)
                    tick_confirm[pair] = {"count": 0, "direction": None}

# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
