# ======================================
# POCKET OPTION OTC SIGNAL BOT
# SAFE DEPLOY VERSION (SYNTAX FIXED)
# ======================================

import asyncio
import json
import requests
import websockets
import logging
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

TREND_SCORE_THRESHOLD = 75
TREND_STRENGTH_THRESHOLD = 60

ENTRY_DELAY = 2
MG_STEP = 2
MAX_MG_STEPS = 3
EXPIRY_MINUTES = 2

MAX_PRICES = 700
RETRY_SECONDS = 5

TICK_CONFIRMATION = 8

BLOCKED_PAIRS = [
    "frxUSDNOK",
    "frxGBPNOK",
    "frxUSDPLN",
    "frxGBPNZD",
    "frxUSDSEK"
]

# ================================
# STATE
# ================================
prices = {}
tick_confirm = {}
active_signal = {"pair": None, "expiry_time": None}
pending_signal = None

# ================================
# EMA
# ================================
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    value = data[0]
    for price in data:
        value = price * k + value * (1 - k)
    return value

# ================================
# RANGE FILTER
# ================================
def is_ranging(price_list):
    if len(price_list) < 120:
        return True

    recent = price_list[-100:]
    if len(recent) < 20:
        return True

    return (max(recent) - min(recent)) < (np.std(recent) * 2)

# ================================
# MOMENTUM FILTER
# ================================
def has_momentum(price_list):
    if len(price_list) < 120:
        return False

    recent = price_list[-5:]
    return (max(recent) - min(recent)) > (np.std(price_list[-100:]) * 0.4)

# ================================
# TREND STRENGTH
# ================================
def trend_strength(price_list):
    if len(price_list) < 150:
        return 0

    ema_fast = ema(price_list[-50:], 10)
    ema_slow = ema(price_list[-100:], 20)

    if ema_fast is None or ema_slow is None:
        return 0

    separation = abs(ema_fast - ema_slow)
    volatility = np.std(price_list[-100:])

    if volatility == 0:
        return 0

    return (separation / volatility) * 100

# ================================
# TREND DETECTION
# ================================
def detect_trend(price_list):
    if len(price_list) < 300:
        return 0, 0, None

    if is_ranging(price_list):
        return 0, 0, None

    ema_fast = ema(price_list[-50:], 10)
    ema_slow = ema(price_list[-100:], 20)
    ema_long_fast = ema(price_list[-200:], 30)
    ema_long_slow = ema(price_list[-300:], 60)

    if not all([ema_fast, ema_slow, ema_long_fast, ema_long_slow]):
        return 0, 0, None

    if not has_momentum(price_list):
        return 0, 0, None

    strength = trend_strength(price_list)
    score = min(strength, 100)

    direction = None

    if ema_fast > ema_slow and ema_long_fast > ema_long_slow:
        direction = "BUY"
    elif ema_fast < ema_slow and ema_long_fast < ema_long_slow:
        direction = "SELL"

    return score, strength, direction

# ================================
# SIGNAL LOCK
# ================================
def signal_active():
    if active_signal["expiry_time"] is None:
        return False
    return datetime.now(TIMEZONE) < active_signal["expiry_time"]

def register_signal(pair):
    total = ENTRY_DELAY + (MG_STEP * MAX_MG_STEPS) + EXPIRY_MINUTES
    active_signal["pair"] = pair
    active_signal["expiry_time"] = datetime.now(TIMEZONE) + timedelta(minutes=total)

# ================================
# TELEGRAM
# ================================
def send_signal(pair, direction, score, strength):
    if signal_active():
        return

    register_signal(pair)

    entry_time = datetime.now(TIMEZONE) + timedelta(minutes=ENTRY_DELAY)

    msg = f"""
🚨 TRADE SIGNAL

PAIR: {pair}
DIRECTION: {direction}
ENTRY: {entry_time.strftime('%H:%M:%S')}
EXPIRY: {EXPIRY_MINUTES} min

CONFIDENCE: {score:.1f}%
STRENGTH: {strength:.1f}%
"""

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
        async with websockets.connect(DERIV_WS) as ws:
            await ws.send(json.dumps({"active_symbols": "brief"}))
            data = json.loads(await ws.recv())

            return [
                s["symbol"]
                for s in data["active_symbols"]
                if s["symbol"].startswith("frx")
                and s["symbol"] not in BLOCKED_PAIRS
            ]
    except:
        return []

# ================================
# MAIN LOOP (FIXED TRY/EXCEPT)
# ================================
async def monitor():
    global pending_signal

    while True:
        try:
            symbols = await load_symbols()

            for s in symbols:
                prices[s] = []
                tick_confirm[s] = {"count": 0, "direction": None}

            async with websockets.connect(DERIV_WS) as ws:

                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for msg in ws:
                    try:
                        data = json.loads(msg)

                        if "tick" not in data:
                            continue

                        pair = data["tick"]["symbol"]
                        price = data["tick"]["quote"]

                        if pair not in prices:
                            continue

                        prices[pair].append(price)

                        if len(prices[pair]) > MAX_PRICES:
                            prices[pair].pop(0)

                        score, strength, direction = detect_trend(prices[pair])

                        if direction and score >= TREND_SCORE_THRESHOLD:

                            if tick_confirm[pair]["direction"] == direction:
                                tick_confirm[pair]["count"] += 1
                            else:
                                tick_confirm[pair]["direction"] = direction
                                tick_confirm[pair]["count"] = 1

                            if tick_confirm[pair]["count"] >= TICK_CONFIRMATION:
                                pending_signal = (pair, direction, score, strength)

                        else:
                            tick_confirm[pair]["count"] = 0
                            tick_confirm[pair]["direction"] = None

                        if pending_signal and not signal_active():
                            p, d, sc, st = pending_signal
