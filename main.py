# ======================================
# POCKET OPTION OTC SIGNAL BOT
# FINAL SNIPER + STABILITY VERSION
# ======================================

import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime, timedelta
import pytz

# ================================
# TELEGRAM
# ================================
BOT_TOKEN = "8751531182:AAGLr0K3N21LIalG-mgxbiIUjdcJTNghLTg"
CHAT_ID = "8308393231"

# ================================
# SETTINGS
# ================================
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

ENTRY_DELAY = 2
MG_STEP = 2
MAX_MG_STEPS = 3
EXPIRY_MINUTES = 2

MAX_PRICES = 700
TICK_CONFIRMATION = 4

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

# ================================
# STATE
# ================================
prices = {}
tick_confirm = {}
active_signal = {"pair": None, "expiry_time": None}
COOLDOWN = False

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
# STABILITY FILTER (CROSS-BROKER)
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
# BREAKOUT
# ================================
def breakout(price_list):
    if len(price_list) < 30:
        return None

    recent = price_list[-20:]
    high = max(recent[:-1])
    low = min(recent[:-1])
    last = recent[-1]

    if last > high:
        return "BUY"
    if last < low:
        return "SELL"

    return None

# ================================
# PULLBACK CONFIRMATION
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
# SIGNAL LOCK
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

    COOLDOWN = True

# ================================
# SEND SIGNAL
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
            # cooldown control
            if COOLDOWN and not signal_active():
                COOLDOWN = False
                print("RESUME SCANNING")

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

            print("SNIPER SCANNING...")

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

                    direction = breakout(prices[pair])

                    if not direction:
                        continue

                    if not pullback_confirm(prices[pair], direction):
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
# START (FIXED ERROR)
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
