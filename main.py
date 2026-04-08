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

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# CONFIDENCE ENGINE (UNCHANGED)
# =========================
def calculate_confidence(price, prev_price):
    change = abs(price - prev_price)

    momentum = min(change * 100, 100)
    stability = max(0, 100 - (change * 120))

    confidence = (momentum * 0.6) + (stability * 0.4)

    return min(100, max(0, confidence))

# =========================
# SIGNAL FORMATTER (UNCHANGED)
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

⚡ LIVE DERIV FRX STREAM
"""

# =========================
# GET ALL FRX PAIRS
# =========================
async def get_frx_symbols(ws):
    await ws.send(json.dumps({
        "active_symbols": "brief",
        "product_type": "basic"
    }))

    symbols = []

    while True:
        response = await ws.recv()
        data = json.loads(response)

        if "active_symbols" in data:
            for item in data["active_symbols"]:
                symbol = item["symbol"]

                if symbol.startswith("frx"):
                    symbols.append(symbol)

            break

    return symbols

# =========================
# MAIN STREAM WITH AUTO RECONNECT
# =========================
async def stream_market():

    while True:  # 🔁 AUTO RECONNECT LOOP
        try:
            async with websockets.connect(DERIV_WS) as ws:

                print("🔄 CONNECTED TO DERIV")

                symbols = await get_frx_symbols(ws)

                print(f"✅ FRX LOADED: {len(symbols)} pairs")

                prev_price = {}

                # subscribe to ALL FRX
                for symbol in symbols:
                    await ws.send(json.dumps({
                        "ticks": symbol,
                        "subscribe": 1
                    }))

                print("🚀 LIVE FRX STREAM RUNNING...")

                while True:
                    data = await ws.recv()
                    tick = json.loads(data)

                    if "tick" not in tick:
                        continue

                    symbol = tick["tick"]["symbol"]
                    price = float(tick["tick"]["quote"])

                    if symbol not in prev_price:
                        prev_price[symbol] = price
                        continue

                    confidence = calculate_confidence(price, prev_price[symbol])

                    direction = "BUY 📈" if price > prev_price[symbol] else "SELL 📉"

                    if confidence >= 85:
                        signal = build_signal(symbol, direction, confidence)
                        send_telegram(signal)

                    prev_price[symbol] = price

        except Exception as e:
            print("❌ DISCONNECTED:", e)
            print("🔁 RECONNECTING IN 5 SECONDS...")
            await asyncio.sleep(5)

# =========================
# RUN
# =========================
async def main():
    await stream_market()

if __name__ == "__main__":
    asyncio.run(main())
