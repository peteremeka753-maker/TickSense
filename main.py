import asyncio
import json
import websockets
import requests
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = "8783779196:AAGNldYhsoISW8GO21gVL9FSHcpsUj4Of6o"
CHAT_ID = "6918721957"

CRYPTO_WS = "wss://stream.binance.com:9443/ws"

SYMBOLS = {
    "btcusdt@trade": "BTCUSD",
    "ethusdt@trade": "ETHUSD"
}

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# CONFIDENCE ENGINE (REAL SIGNAL FILTER)
# =========================
def calculate_confidence(price, prev_price):
    change = abs(price - prev_price)

    momentum = min(change * 100, 100)
    stability = max(0, 100 - (change * 120))

    confidence = (momentum * 0.6) + (stability * 0.4)

    return min(100, max(0, confidence))

# =========================
# SIGNAL FORMATTER
# =========================
def build_signal(symbol, direction, confidence):
    now = datetime.now()

    entry = now + timedelta(minutes=2)
    mg1 = now + timedelta(minutes=4)
    mg2 = now + timedelta(minutes=6)
    mg3 = now + timedelta(minutes=8)

    return f"""
🚨 LIVE V9 PRO SIGNAL 🚨

📊 Pair: {symbol}
📈 Direction: {direction}

🔥 Confidence: {round(confidence, 2)}%

⏱ ENTRY: {entry.strftime('%H:%M:%S')}

🔁 MG1: {mg1.strftime('%H:%M:%S')}
🔁 MG2: {mg2.strftime('%H:%M:%S')}
🔁 MG3: {mg3.strftime('%H:%M:%S')}

⚡ LIVE WEBSOCKET STREAM
"""

# =========================
# WEBSOCKET STREAM
# =========================
async def stream_market():
    url = f"{CRYPTO_WS}/btcusdt@trade"

    prev_price = None

    async with websockets.connect(url) as ws:
        print("LIVE STREAM STARTED...")

        while True:
            data = await ws.recv()
            tick = json.loads(data)

            price = float(tick["p"])

            if prev_price is None:
                prev_price = price
                continue

            confidence = calculate_confidence(price, prev_price)

            direction = "BUY 📈" if price > prev_price else "SELL 📉"

            # ONLY SEND 85%+
            if confidence >= 85:
                signal = build_signal("BTCUSD", direction, confidence)
                send_telegram(signal)

            prev_price = price

# =========================
# RUN
# =========================
async def main():
    await stream_market()

if __name__ == "__main__":
    asyncio.run(main())
