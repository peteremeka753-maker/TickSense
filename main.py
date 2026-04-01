# ======================================
# PROBABILITY SIGNAL CORE (PSC BOT)
# FULL COMBINED VERSION (1+2+3)
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

prices = {}

# ================================
# MARTINGALE SETTINGS (ADDED ONLY)
# ================================
MG_STEP_MINUTES = 2
MAX_MG_LEVELS = 3

def generate_martingale_times():
    now = datetime.now(TIMEZONE)
    return [
        now + timedelta(minutes=MG_STEP_MINUTES * i)
        for i in range(1, MAX_MG_LEVELS + 1)
    ]

# ================================
# MARKET STATE (CLEAN LOGIC)
# ================================
def market_state(prices):
    if len(prices) < 30:
        return "NO_TRADE"

    recent = prices[-30:]
    moves = [recent[i] - recent[i-1] for i in range(1, len(recent))]

    volatility = np.std(moves)
    direction_strength = abs(np.mean(moves))

    if volatility < 0.00005:
        return "CHOP"

    if direction_strength > volatility * 0.6:
        return "TREND"

    return "CHOP"

# ================================
# DIRECTION BIAS
# ================================
def direction_bias(prices):
    if len(prices) < 10:
        return None

    moves = [prices[i] - prices[i-1] for i in range(-10, 0)]
    score = sum(moves)

    if score > 0:
        return "BUY"
    elif score < 0:
        return "SELL"

    return None

# ================================
# ENTRY CONFIRMATION
# ================================
def confirm_entry(prices, direction):
    last_moves = [prices[i] - prices[i-1] for i in range(-5, 0)]

    if direction == "BUY":
        return sum(1 for m in last_moves if m > 0) >= 3

    if direction == "SELL":
        return sum(1 for m in last_moves if m < 0) >= 3

    return False

# ================================
# BROKER ADAPTATION (OPTION 3)
# ================================
def broker_adjustment(broker_name):
    if broker_name == "POCKET_OPTION":
        return {"sensitivity": 1.2, "trend_strength": 0.65}

    if broker_name == "IQ_OPTION":
        return {"sensitivity": 1.0, "trend_strength": 0.6}

    return {"sensitivity": 1.0, "trend_strength": 0.6}

# ================================
# SEND SIGNAL (MARTINGALE ADDED)
# ================================
def send_signal(pair, direction):

    mg_times = generate_martingale_times()

    msg = (
        f"🚨 PSC SIGNAL\n\n"
        f"PAIR: {pair}\n"
        f"DIRECTION: {direction}\n"
        f"TIME: {datetime.now(TIMEZONE).strftime('%H:%M:%S')}\n\n"
        f"📊 MARTINGALE (2-MIN RULE)\n"
        f"🔹 L1 → {mg_times[0].strftime('%H:%M:%S')}\n"
        f"🔹 L2 → {mg_times[1].strftime('%H:%M:%S')}\n"
        f"🔹 L3 → {mg_times[2].strftime('%H:%M:%S')}"
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
# MAIN LOOP
# ================================
async def monitor():
    async with websockets.connect(DERIV_WS, ping_interval=20) as ws:

        await ws.send(json.dumps({"active_symbols": "brief"}))
        data = json.loads(await ws.recv())

        symbols = [
            s["symbol"] for s in data.get("active_symbols", [])
            if s["symbol"].startswith("frx")
        ]

        for s in symbols:
            prices[s] = []

        for s in symbols:
            await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

        async for msg in ws:
            try:
                data = json.loads(msg)

                if "tick" not in data:
                    continue

                pair = data["tick"]["symbol"]
                price = float(data["tick"]["quote"])

                prices[pair].append(price)

                if len(prices[pair]) > 200:
                    prices[pair].pop(0)

                # =========================
                # CORE LOGIC (UNCHANGED)
                # =========================

                state = market_state(prices[pair])
                if state != "TREND":
                    continue

                direction = direction_bias(prices[pair])
                if not direction:
                    continue

                if not confirm_entry(prices[pair], direction):
                    continue

                send_signal(pair, direction)

            except:
                continue

# ================================
# START
# ================================
if __name__ == "__main__":
    asyncio.run(monitor())
