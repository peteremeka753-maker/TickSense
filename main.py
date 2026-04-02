# ======================================
# POCKET OPTION OTC SIGNAL BOT
# CLEAN REBUILD SYSTEM (STABLE CORE)
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
COOLDOWN_MINUTES = 5
MAX_PRICES = 200
TREND_WINDOW = 12
MIN_VOLATILITY = 0.00005

BLOCKED_PAIRS = [
    "frxUSDNOK","frxGBPNOK","frxUSDPLN",
    "frxGBPNZD","frxUSDSEK"
]

# ================================
# STATE
# ================================
prices = {}
last_signal_pair = None
cooldown_until = None


# ================================
# SESSION FILTER
# ================================
def valid_session():
    hour = datetime.now(TIMEZONE).hour
    return 8 <= hour <= 22


# ================================
# VOLATILITY CHECK
# ================================
def good_market(price_list):
    if len(price_list) < 20:
        return False

    return np.std(price_list[-20:]) > MIN_VOLATILITY


# ================================
# SIMPLE TREND DETECTION
# ================================
def get_trend(price_list):
    if len(price_list) < TREND_WINDOW:
        return None

    start = price_list[-TREND_WINDOW]
    end = price_list[-1]

    diff = end - start

    if abs(diff) < 0.0001:
        return None

    return "BUY" if diff > 0 else "SELL"


# ================================
# ENTRY CONFIRMATION (TICK FILTER)
# ================================
def confirm_entry(price_list, direction):
    if len(price_list) < 3:
        return False

    if direction == "BUY":
        return price_list[-1] > price_list[-2] > price_list[-3]

    if direction == "SELL":
        return price_list[-1] < price_list[-2] < price_list[-3]

    return False


# ================================
# ANTI-SPAM
# ================================
def can_send(pair):
    global cooldown_until, last_signal_pair

    now = datetime.now(TIMEZONE)

    if cooldown_until and now < cooldown_until:
        return False

    if last_signal_pair == pair:
        return False

    return True


def register_signal(pair):
    global cooldown_until, last_signal_pair

    last_signal_pair = pair
    cooldown_until = datetime.now(TIMEZONE) + timedelta(minutes=COOLDOWN_MINUTES)


# ================================
# SEND SIGNAL
# ================================
def send_signal(pair, direction):
    now = datetime.now(TIMEZONE)
    entry = now + timedelta(minutes=ENTRY_DELAY)

    msg = (
        f"🚨 CLEAN SIGNAL BOT\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n\n"
        f"ENTRY: {entry.strftime('%I:%M %p')}\n"
        f"EXPIRY: {EXPIRY_MINUTES} min"
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

                    # FILTER 1: MARKET QUALITY
                    if not good_market(prices[pair]):
                        continue

                    # FILTER 2: TREND
                    direction = get_trend(prices[pair])
                    if not direction:
                        continue

                    # FILTER 3: CONFIRMATION
                    if not confirm_entry(prices[pair], direction):
                        continue

                    # FILTER 4: ANTI-SPAM
                    if not can_send(pair):
                        continue

                    send_signal(pair, direction)

        except Exception:
            await asyncio.sleep(3)


# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
