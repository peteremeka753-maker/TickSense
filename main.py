# ======================================
# POCKET OPTION OTC SIGNAL BOT
# FINAL VERSION (PRICE ACTION + CONTROL)
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
BOT_TOKEN = "8751531182:AAGLr0K3N21LIalG-mgxbiIUjdcJTNghLTg"
CHAT_ID = "8308393231"

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
COOLDOWN = False

# ================================
# PRICE ACTION
# ================================
def swing_highs_lows(prices, lookback=8):
    highs, lows = [], []
    for i in range(lookback, len(prices)-lookback):
        window = prices[i-lookback:i+lookback]
        if prices[i] == max(window):
            highs.append(prices[i])
        if prices[i] == min(window):
            lows.append(prices[i])
    return highs, lows


def market_bias(price_list):
    if len(price_list) < 60:
        return None

    highs, lows = swing_highs_lows(price_list[-200:], 8)

    if len(highs) < 2 or len(lows) < 2:
        return None

    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "BUY"

    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
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
        elif last > prev:
            return "SELL"

    return None

# ================================
# SIGNAL LOCK (COOLDOWN SYSTEM)
# ================================
def signal_active():
    if active_signal["expiry_time"] is None:
        return False
    return datetime.now(TIMEZONE) < active_signal["expiry_time"]


def register_signal(pair):
    global COOLDOWN
    now = datetime.now(TIMEZONE)

    total = ENTRY_DELAY + (MG_STEP * MAX_MG_STEPS) + EXPIRY_MINUTES

    active_signal["pair"] = pair
    active_signal["expiry_time"] = now + timedelta(minutes=total)

    # 🔥 STOP SCANNING
    COOLDOWN = True


# ================================
# TELEGRAM SIGNAL
# ================================
def send_signal(pair, direction):
    now = datetime.now(TIMEZONE)

    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    mg_times = [
        entry_time + timedelta(minutes=MG_STEP * i)
        for i in range(1, MAX_MG_STEPS + 1)
    ]

    register_signal(pair)

    msg = (
        f"🚨 TRADE SIGNAL All Options Broker\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY: {entry_time.strftime('%I:%M %p')}\n"
        f"EXPIRY: {EXPIRY_MINUTES} min\n\n"
        f"📊 MARTINGALE LEVELS\n"
        f"🔹 L1 → {mg_times[0].strftime('%I:%M %p')}\n"
        f"🔹 L2 → {mg_times[1].strftime('%I:%M %p')}\n"
        f"🔹 L3 → {mg_times[2].strftime('%I:%M %p')}"
    )

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg},
        timeout=10
    )


# ================================
# LOAD SYMBOLS
# ================================
async def load_symbols():
    try:
        async with websockets.connect(DERIV_WS) as ws:
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
    global COOLDOWN

    while True:
        # 🔥 WAIT until signal finishes
        if COOLDOWN and not signal_active():
            COOLDOWN = False
            print("COOLDOWN FINISHED → RESUMING SCAN")

        if COOLDOWN:
            await asyncio.sleep(1)
            continue

        symbols = await load_symbols()

        if not symbols:
            await asyncio.sleep(5)
            continue

        for s in symbols:
            prices[s] = []
            tick_confirm[s] = {"count": 0, "direction": None}

        print("SCANNING MARKET...")

        try:
            async with websockets.connect(DERIV_WS) as ws:

                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for msg in ws:
                    if COOLDOWN:
                        break

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

                    if tick_confirm[pair]["direction"] == direction:
                        tick_confirm[pair]["count"] += 1
                    else:
                        tick_confirm[pair]["direction"] = direction
                        tick_confirm[pair]["count"] = 1

                    if tick_confirm[pair]["count"] >= TICK_CONFIRMATION:
                        send_signal(pair, direction)
                        break  # 🔥 STOP AFTER ONE SIGNAL

        except:
            await asyncio.sleep(3)


# ================================
# START BOT (FIXED ERROR)
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
