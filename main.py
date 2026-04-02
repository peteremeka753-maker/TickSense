# ======================================
# POCKET OPTION OTC SIGNAL BOT
# CLEAN RESET VERSION (STABLE + NO SPAM)
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

# ================================
# SETTINGS
# ================================
ENTRY_DELAY = 2
EXPIRY_MINUTES = 2
COOLDOWN_MINUTES = 5  # prevents spam
MAX_PRICES = 300

BLOCKED_PAIRS = ["frxUSDNOK","frxGBPNOK","frxUSDPLN","frxGBPNZD","frxUSDSEK"]

# ================================
# STATE
# ================================
prices = {}
last_signal_time = {}
last_signal_pair = None

COOLDOWN_UNTIL = None


# ================================
# SESSION FILTER
# ================================
def valid_session():
    hour = datetime.now(TIMEZONE).hour
    return 8 <= hour <= 22


# ================================
# SIMPLE TREND
# ================================
def get_direction(price_list):
    if len(price_list) < 10:
        return None

    move = price_list[-1] - price_list[-10]

    if abs(move) < 0.0001:
        return None

    return "BUY" if move > 0 else "SELL"


# ================================
# VOLATILITY CHECK (simple)
# ================================
def good_market(price_list):
    if len(price_list) < 20:
        return False

    volatility = np.std(price_list[-20:])
    return volatility > 0.00005


# ================================
# ANTI-SPAM CHECK
# ================================
def can_send_signal(pair):
    global COOLDOWN_UNTIL, last_signal_pair

    now = datetime.now(TIMEZONE)

    # cooldown active
    if COOLDOWN_UNTIL and now < COOLDOWN_UNTIL:
        return False

    # prevent same pair spam
    if last_signal_pair == pair:
        return False

    return True


# ================================
# REGISTER SIGNAL
# ================================
def register_signal(pair):
    global COOLDOWN_UNTIL, last_signal_pair

    last_signal_pair = pair
    COOLDOWN_UNTIL = datetime.now(TIMEZONE) + timedelta(minutes=COOLDOWN_MINUTES)


# ================================
# SEND SIGNAL
# ================================
def send_signal(pair, direction):
    now = datetime.now(TIMEZONE)
    entry_time = now + timedelta(minutes=ENTRY_DELAY)

    msg = (
        f"🚨 TRADE SIGNAL\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY: {entry_time.strftime('%I:%M %p')}\n"
        f"EXPIRY: {EXPIRY_MINUTES} min\n"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

    register_signal(pair)


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

            symbols = await load_symbols()

            if not symbols:
                await asyncio.sleep(5)
                continue

            for s in symbols:
                if s not in prices:
                    prices[s] = []

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

                    # skip weak data
                    if not good_market(prices[pair]):
                        continue

                    direction = get_direction(prices[pair])

                    if not direction:
                        continue

                    # ANTI-SPAM CHECK
                    if not can_send_signal(pair):
                        continue

                    send_signal(pair, direction)

        except Exception:
            await asyncio.sleep(3)


# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
