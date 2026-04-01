# ======================================
# POCKET OPTION OTC SIGNAL BOT
# PRICE ACTION VERSION + STABILITY LAYER
# ======================================

import asyncio
import json
import requests
import websockets
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
TICK_CONFIRMATION = 2  # reduced slightly to avoid over-filtering

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

# ================================
# STATE
# ================================
prices = {}
tick_confirm = {}
active_signal = {"pair": None, "expiry_time": None}

# ================================
# SIMPLE RISK FILTER (LIGHT)
# ================================
paused = False
bad_count = 0
PAUSE_LIMIT = 12


def risk_engine(direction):
    global paused, bad_count

    if direction is None:
        bad_count += 1
    else:
        bad_count = max(0, bad_count - 1)

    if bad_count >= PAUSE_LIMIT:
        paused = True

    if paused and bad_count <= 4:
        paused = False

    return paused


# ================================
# PRICE ACTION CORE
# ================================
def market_bias(price_list):
    if len(price_list) < 40:
        return None

    last = price_list[-1]
    prev = price_list[-5]

    if last > prev:
        return "BUY"
    if last < prev:
        return "SELL"

    return None


def rejection_signal(price_list):
    if len(price_list) < 5:
        return None

    if price_list[-1] > price_list[-2] and price_list[-2] < price_list[-3]:
        return "BUY"

    if price_list[-1] < price_list[-2] and price_list[-2] > price_list[-3]:
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
    if signal_active() or paused:
        return

    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    l1 = entry_time
    l2 = entry_time + timedelta(minutes=MG_STEP)
    l3 = entry_time + timedelta(minutes=MG_STEP * 2)

    register_signal(pair)

    msg = (
        f"🚨 TRADE SIGNAL (PRICE ACTION)\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY: {entry_time.strftime('%I:%M %p')}\n"
        f"EXPIRY: {EXPIRY_MINUTES} min\n\n"
        f"📊 MARTINGALE LEVELS\n"
        f"🔹 L1 → {l1.strftime('%I:%M %p')}\n"
        f"🔹 L2 → {l2.strftime('%I:%M %p')}\n"
        f"🔹 L3 → {l3.strftime('%I:%M %p')}\n\n"
        f"CONFIDENCE: {score}%\n"
        f"{'PAUSED' if paused else 'ACTIVE'}"
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
    global paused

    while True:
        symbols = await load_symbols()

        if not symbols:
            await asyncio.sleep(5)
            continue

        for s in symbols:
            prices[s] = []
            tick_confirm[s] = {"count": 0, "direction": None}

        print("BOT STARTED (CLEAN PRICE ACTION MODE)")

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

                    paused = risk_engine(direction)

                    if not direction or paused:
                        continue

                    if tick_confirm[pair]["direction"] == direction:
                        tick_confirm[pair]["count"] += 1
                    else:
                        tick_confirm[pair]["direction"] = direction
                        tick_confirm[pair]["count"] = 1

                    if tick_confirm[pair]["count"] >= TICK_CONFIRMATION:
                        send_signal(pair, direction, 90)
                        tick_confirm[pair] = {"count": 0, "direction": None}

        except Exception:
            await asyncio.sleep(3)


# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
