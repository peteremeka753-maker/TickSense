import asyncio
import json
import websockets
import requests
import time
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = "8783779196:AAGNldYhsoISW8GO21gVL9FSHcpsUj4Of6o"
CHAT_ID = "6918721957"

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

MIN_SCORE = 88
MAX_SIGNALS_PER_HOUR = 3

signal_history = []

# =========================
# TELEGRAM (RELIABLE DELIVERY)
# =========================
def send_telegram(msg):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for attempt in range(5):
        try:
            r = requests.post(
                url,
                data={"chat_id": CHAT_ID, "text": msg},
                timeout=10
            )

            if r.status_code == 200:
                print("✅ SENT")
                return True

        except Exception as e:
            print(f"❌ Telegram error: {e}")

        time.sleep(2)

    print("🚨 FAILED SEND")
    return False


# =========================
# SCORING ENGINE (REALISTIC)
# =========================
def score_market(price, prev_price):

    change = abs(price - prev_price)

    momentum = min(change * 120, 100)
    stability = max(0, 100 - (change * 150))
    trend_strength = min(abs(price - prev_price) * 200, 100)

    score = (momentum * 0.4) + (stability * 0.3) + (trend_strength * 0.3)

    return min(100, max(0, score))


# =========================
# SIGNAL FORMAT (UPDATED ONLY HERE)
# =========================
def build_signal(symbol, direction, score):

    now = datetime.now()

    # =========================
    # MARTINGALE TIME SYSTEM (ADDED ONLY)
    # =========================
    entry = now + timedelta(minutes=2)
    mg1 = now + timedelta(minutes=4)
    mg2 = now + timedelta(minutes=6)
    mg3 = now + timedelta(minutes=8)

    return f"""
🚨 PRO V9 REAL ENGINE SIGNAL 🚨

📊 Pair: {symbol}
📈 Direction: {direction}

🔥 Score: {round(score, 2)}

⏱ SIGNAL TIME: {now.strftime('%H:%M:%S')}

🎯 ENTRY: {entry.strftime('%H:%M:%S')}

🔁 MARTINGALE LEVELS:
MG1 ➜ {mg1.strftime('%H:%M:%S')}
MG2 ➜ {mg2.strftime('%H:%M:%S')}
MG3 ➜ {mg3.strftime('%H:%M:%S')}

⚡ DERIV FRX LIVE SYSTEM
"""


# =========================
# GET FRX SYMBOLS
# =========================
async def get_symbols(ws):

    await ws.send(json.dumps({
        "active_symbols": "brief",
        "product_type": "basic"
    }))

    symbols = []

    while True:
        data = json.loads(await ws.recv())

        if "active_symbols" in data:
            for item in data["active_symbols"]:
                if item["symbol"].startswith("frx"):
                    symbols.append(item["symbol"])
            break

    return symbols


# =========================
# SIGNAL LIMIT CHECK
# =========================
def can_send_signal():

    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)

    global signal_history
    signal_history = [t for t in signal_history if t > one_hour_ago]

    return len(signal_history) < MAX_SIGNALS_PER_HOUR


def register_signal():
    signal_history.append(datetime.now())


# =========================
# MAIN ENGINE
# =========================
async def stream():

    while True:
        try:
            async with websockets.connect(DERIV_WS) as ws:

                print("🔄 CONNECTED")

                symbols = await get_symbols(ws)
                print(f"FRX LOADED: {len(symbols)}")

                prev = {}

                for s in symbols:
                    await ws.send(json.dumps({
                        "ticks": s,
                        "subscribe": 1
                    }))

                print("🚀 STREAM ACTIVE")

                while True:

                    msg = await ws.recv()
                    data = json.loads(msg)

                    if "tick" not in data:
                        continue

                    symbol = data["tick"]["symbol"]
                    price = float(data["tick"]["quote"])

                    if symbol not in prev:
                        prev[symbol] = price
                        continue

                    score = score_market(price, prev[symbol])

                    direction = "BUY 📈" if price > prev[symbol] else "SELL 📉"

                    if score >= MIN_SCORE and can_send_signal():

                        signal = build_signal(symbol, direction, score)

                        if send_telegram(signal):
                            register_signal()

                    prev[symbol] = price

        except Exception as e:
            print("❌ DISCONNECTED:", e)
            print("🔁 RECONNECTING IN 5s...")
            await asyncio.sleep(5)


# =========================
# RUN
# =========================
async def main():
    await stream()

if __name__ == "__main__":
    asyncio.run(main())
