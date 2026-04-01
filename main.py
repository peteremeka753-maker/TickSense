# ======================================
# PRO PRICE ACTION SIGNAL BOT (UPGRADED)
# TELEGRAM STYLE + FILTERED QUALITY ENGINE
# ======================================

import asyncio
import json
import requests
import websockets
from datetime import datetime
import pytz

# ================================
# CONFIG
# ================================
BOT_TOKEN = "8751531182:AAGLr0K3N21LIalG-mgxbiIUjdcJTNghLTg"
CHAT_ID = "8308393231"

WS_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")

TIMEFRAME = "1 MINUTE"
EXPIRY = "1M"

# ================================
# CONTROL SETTINGS
# ================================
MIN_PRICE_HISTORY = 30
MIN_SIGNAL_SCORE = 75

cooldown = 90
last_signal_time = {}

prices = {}

# ================================
# STEP 1: ALERT
# ================================
def send_step1(pair):
    msg = f"""
📊 PLATFORM ➜ POCKET OPTION
📈 ASSET ➜ {pair}
⏰ TIMEFRAME ➜ {TIMEFRAME}

⚠️ SCANNING MARKET... WAIT FOR SIGNAL
"""
    send(msg)


# ================================
# TELEGRAM SENDER
# ================================
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass


# ================================
# PRICE ACTION ENGINE (PRO LOGIC)
# ================================
def analyze(pair):
    data = prices.get(pair, [])

    if len(data) < MIN_PRICE_HISTORY:
        return None, 0

    last = data[-1]
    prev = data[-5]
    mid = data[-10]

    # TREND STRENGTH
    trend_up = last > prev > mid
    trend_down = last < prev < mid

    # MOMENTUM
    momentum_up = (last - prev) > (prev - mid)
    momentum_down = (last - prev) < (prev - mid)

    # REJECTION (simple price action)
    rejection_buy = data[-2] < data[-3] and last > data[-2]
    rejection_sell = data[-2] > data[-3] and last < data[-2]

    score = 0
    direction = None

    if trend_up and momentum_up:
        score += 40
    if trend_down and momentum_down:
        score += 40

    if rejection_buy:
        score += 25
        direction = "CALL"

    if rejection_sell:
        score += 25
        direction = "PUT"

    if trend_up and direction is None:
        direction = "CALL"
        score += 20

    if trend_down and direction is None:
        direction = "PUT"
        score += 20

    return direction, score


# ================================
# COOLDOWN CHECK
# ================================
def can_send(pair):
    now = datetime.now().timestamp()
    last = last_signal_time.get(pair, 0)

    if now - last < cooldown:
        return False

    last_signal_time[pair] = now
    return True


# ================================
# STEP 3 SIGNAL
# ================================
def send_signal(pair, direction, score):
    color = "🟢 CALL 🔼" if direction == "CALL" else "🔴 PUT 🔽"

    msg = f"""
📊 ASSET ➜ {pair}
⏰ TIMEFRAME ➜ {TIMEFRAME}

📌 SIGNAL ➜ {color}
📊 SCORE ➜ {score}/100
📉 EXPIRY ➜ {EXPIRY}

⚠️ ENTER ON NEXT CANDLE
"""
    send(msg)


# ================================
# MAIN BOT
# ================================
async def run():
    global prices

    async with websockets.connect(WS_URL, ping_interval=20) as ws:

        await ws.send(json.dumps({"active_symbols": "brief"}))
        data = json.loads(await ws.recv())

        symbols = [
            s["symbol"]
            for s in data.get("active_symbols", [])
            if s["symbol"].startswith("frx")
        ]

        for s in symbols:
            prices[s] = []
            send_step1(s)

        for s in symbols:
            await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if "tick" not in data:
                continue

            pair = data["tick"]["symbol"]
            price = float(data["tick"]["quote"])

            if pair not in prices:
                prices[pair] = []

            prices[pair].append(price)

            if len(prices[pair]) > 80:
                prices[pair].pop(0)

            direction, score = analyze(pair)

            if not direction:
                continue

            if score < MIN_SIGNAL_SCORE:
                continue

            if not can_send(pair):
                continue

            send_signal(pair, direction, score)


# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(run())
