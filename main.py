import asyncio
import json
import requests
import websockets
import numpy as np
from datetime import datetime
import pytz

BOT_TOKEN = "8379555524:AAEPO3_ZQ0aHFpzOLr40hyHig89LxuJS7i4"
CHAT_ID = "6918721957"

WS_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TZ = pytz.timezone("Africa/Lagos")

prices = {}
pending_signal = None


def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    value = data[0]
    for price in data:
        value = price * k + value * (1 - k)
    return value


def get_trend(data):
    if len(data) < 100:
        return None, 0

    fast = ema(data[-50:], 10)
    slow = ema(data[-100:], 20)

    if fast is None or slow is None:
        return None, 0

    volatility = np.std(data[-100:])
    if volatility == 0:
        return None, 0

    strength = abs(fast - slow) / volatility * 100

    if fast > slow:
        return "BUY", strength
    elif fast < slow:
        return "SELL", strength

    return None, 0


def send_signal(pair, direction, strength):
    time_now = datetime.now(TZ).strftime("%H:%M:%S")

    message = f"""
🚨 SIGNAL

PAIR: {pair}
DIRECTION: {direction}
TIME: {time_now}
STRENGTH: {strength:.2f}%
"""

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )
    except:
        pass


async def get_symbols():
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"active_symbols": "brief"}))
            data = json.loads(await ws.recv())
            return [s["symbol"] for s in data["active_symbols"] if "frx" in s["symbol"]]
    except:
        return []


async def run_bot():
    global pending_signal

    while True:
        try:
            symbols = await get_symbols()

            for s in symbols:
                prices[s] = []

            async with websockets.connect(WS_URL) as ws:

                for s in symbols:
                    await ws.send(json.dumps({"ticks": s, "subscribe": 1}))

                async for msg in ws:
                    data = json.loads(msg)

                    if "tick" not in data:
                        continue

                    pair = data["tick"]["symbol"]
                    price = data["tick"]["quote"]

                    if pair not in prices:
                        continue

                    prices[pair].append(price)

                    if len(prices[pair]) > 200:
                        prices[pair].pop(0)

                    direction, strength = get_trend(prices[pair])

                    if direction and strength > 60:
                        pending_signal = (pair, direction, strength)

                    if pending_signal:
                        p, d, st = pending_signal
                        send_signal(p, d, st)
                        pending_signal = None

        except Exception as e:
            print("Restarting...", e)
            await asyncio.sleep(3)


asyncio.run(run_bot())
