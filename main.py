# ======================================
# POCKET OPTION OTC SIGNAL BOT
# FINAL SNIPER + STABILITY VERSION (FIXED + ANTI-REENTRY LOCK)
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz

BOT_TOKEN = "8379555524:AAEPO3_ZQ0aHFpzOLr40hyHig89LxuJS7i4"
CHAT_ID = "6918721957"

DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

ENTRY_DELAY = 2
MG_STEP = 2
MAX_MG_STEPS = 3
EXPIRY_MINUTES = 2

MAX_PRICES = 700
TICK_CONFIRMATION = 3

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

prices = {}
tick_confirm = {}

active_signal = {"pair": None, "expiry_time": None}

COOLDOWN = False

# ================================
# NEW ANTI-SPAM MEMORY SYSTEM
# ================================
last_trade = {
    "pair": None,
    "direction": None,
    "block_until": None
}

# ================================
# SESSION FILTER
# ================================
def valid_session():
    hour = datetime.now(TIMEZONE).hour
    return 8 <= hour <= 22

# ================================
# VOLATILITY
# ================================
def good_volatility(price_list):
    if len(price_list) < 50:
        return False
    return np.std(price_list[-50:]) > 0.0003

# ================================
# STABILITY FILTER
# ================================
def stable_market(price_list):
    if len(price_list) < 20:
        return False

    recent = price_list[-20:]
    moves = [abs(recent[i] - recent[i-1]) for i in range(1, len(recent))]

    avg_move = np.mean(moves)
    max_move = max(moves)

    if max_move > avg_move * 3:
        return False

    if avg_move < 0.00005:
        return False

    return True

# ================================
# STRONG MOVE
# ================================
def strong_movement(price_list):
    if len(price_list) < 20:
        return False

    move = abs(price_list[-1] - price_list[-5])
    volatility = np.std(price_list[-20:])

    return move > volatility * 1.2

# ================================
# MID-TREND FILTER
# ================================
def mid_trend_filter(price_list, direction):
    if len(price_list) < 20:
        return False

    recent = price_list[-10:]
    net_move = recent[-1] - recent[-0]
    volatility = np.std(recent)

    moves = [recent[i] - recent[i-1] for i in range(1, len(recent))]

    if direction == "BUY":
        if net_move <= 0:
            return False
        if abs(net_move) < volatility * 1.2:
            return False
        if sum(1 for m in moves if m > 0) < 6:
            return False
        return True

    if direction == "SELL":
        if net_move >= 0:
            return False
        if abs(net_move) < volatility * 1.2:
            return False
        if sum(1 for m in moves if m < 0) < 6:
            return False
        return True

    return False

# ================================
# EARLY TREND
# ================================
def early_trend(price_list):
    if len(price_list) < 15:
        return None

    move = price_list[-1] - price_list[-10]

    if move > 0:
        return "BUY"
    elif move < 0:
        return "SELL"

    return None

# ================================
# PULLBACK CONFIRM
# ================================
def pullback_confirm(price_list, direction):
    if len(price_list) < 5:
        return False

    if direction == "BUY":
        return price_list[-1] > price_list[-2]

    if direction == "SELL":
        return price_list[-1] < price_list[-2]

    return False

# ================================
# TREND BUILDING
# ================================
def trend_building(price_list, direction):
    if len(price_list) < 15:
        return False

    moves = [price_list[i] - price_list[i-1] for i in range(-5, 0)]

    if direction == "BUY":
        return sum(1 for m in moves if m > 0) >= 3

    if direction == "SELL":
        return sum(1 for m in moves if m < 0) >= 3

    return False

# ================================
# NEW: CROSS-PAIR REENTRY + TIME LOCK
# ================================
def avoid_reentry(price_list, pair, direction):
    now = datetime.now(TIMEZONE)

    # block if still in cooldown window
    if last_trade["block_until"] and now < last_trade["block_until"]:
        return False

    if last_trade["pair"] == pair:
        if last_trade["direction"] == direction:
            return False  # same signal spam block

        # prevent flip-flop immediately after expiry
        if len(price_list) >= 10:
            move = price_list[-1] - price_list[-10]

            if last_trade["direction"] == "BUY" and move < 0:
                return False

            if last_trade["direction"] == "SELL" and move > 0:
                return False

    return True

# ================================
# SIGNAL LOCK
# ================================
def reset_signal():
    global active_signal, COOLDOWN
    active_signal = {"pair": None, "expiry_time": None}
    COOLDOWN = False

def signal_active():
    if active_signal["expiry_time"] is None:
        return False

    if datetime.now(TIMEZONE) >= active_signal["expiry_time"]:
        reset_signal()
        return False

    return True

def register_signal(pair):
    reset_signal()

    now = datetime.now(TIMEZONE)
    active_signal["pair"] = pair
    active_signal["expiry_time"] = now + timedelta(minutes=EXPIRY_MINUTES + 1)

    global COOLDOWN
    COOLDOWN = True

# ================================
# SEND SIGNAL
# ================================
def send_signal(pair, direction):
    global last_trade

    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    mg_times = [
        entry_time + timedelta(minutes=MG_STEP * i)
        for i in range(1, MAX_MG_STEPS + 1)
    ]

    register_signal(pair)

    # 🔒 STRONG LOCK (THIS FIXES YOUR ISSUE)
    last_trade["pair"] = pair
    last_trade["direction"] = direction
    last_trade["block_until"] = now + timedelta(minutes=EXPIRY_MINUTES + 2)

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

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

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
    global COOLDOWN

    while True:
        try:
            if COOLDOWN and not signal_active():
                COOLDOWN = False

            if COOLDOWN:
                await asyncio.sleep(1)
                continue

            if not valid_session():
                await asyncio.sleep(30)
                continue

            symbols = await load_symbols()

            if not symbols:
                await asyncio.sleep(5)
                continue

            for s in symbols:
                prices[s] = []
                tick_confirm[s] = {"count": 0, "direction": None}

            async with websockets.connect(DERIV_WS, ping_interval=20) as ws:

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

                    if not good_volatility(prices[pair]):
                        continue

                    if not stable_market(prices[pair]):
                        continue

                    if not strong_movement(prices[pair]):
                        continue

                    direction = early_trend(prices[pair])

                    if not direction:
                        continue

                    if not pullback_confirm(prices[pair], direction):
                        continue

                    if not trend_building(prices[pair], direction):
                        continue

                    if not mid_trend_filter(prices[pair], direction):
                        continue

                    if not avoid_reentry(prices[pair], pair, direction):
                        continue

                    if tick_confirm[pair]["direction"] == direction:
                        tick_confirm[pair]["count"] += 1
                    else:
                        tick_confirm[pair]["direction"] = direction
                        tick_confirm[pair]["count"] = 1

                    if tick_confirm[pair]["count"] >= TICK_CONFIRMATION:
                        send_signal(pair, direction)
                        break

        except Exception:
            await asyncio.sleep(3)

# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
