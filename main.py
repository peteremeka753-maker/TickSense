# ======================================
# AI TRADER WITH AUTOMATIC PAIRS FETCHING + SMART READER + LEARNING
# ======================================

import os
import csv
import json
import asyncio
import websockets
import numpy as np
from datetime import datetime
from io import BytesIO
import pytz
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters

# -------------------
# CONFIG
# -------------------
BOT_TOKEN = "8751531182:AAGLr0K3N21LIalG-mgxbiIUjdcJTNghLTg"
CHAT_ID = "8308393231"
DERIV_WS = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
TIMEZONE = pytz.timezone("Africa/Lagos")
DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "trades.csv")
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------
# INIT CSV
# -------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "time","symbol","direction","tp","sl","timeframe","demand_zone","supply_zone","result"
        ])

# -------------------
# GLOBAL VARIABLES
# -------------------
market_volatility = {}
confidence_bias = {}
cooldown_tracker = {}

# -------------------
# SAFE MARKET LISTENER (ANTI-CRASH)
# -------------------
async def market_listener():
    global market_volatility
    while True:
        try:
            async with websockets.connect(DERIV_WS, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps({"active_symbols": "brief"}))
                data = json.loads(await ws.recv())

                symbols = [s["symbol"] for s in data["active_symbols"]]
                pairs = [s for s in symbols if s.startswith("OTC")]

                for p in pairs:
                    await ws.send(json.dumps({"ticks": p, "subscribe": 1}))
                    market_volatility[p] = []

                async for msg in ws:
                    data = json.loads(msg)
                    if "tick" not in data:
                        continue
                    symbol = data["tick"]["symbol"]
                    quote = data["tick"]["quote"]

                    market_volatility[symbol].append(quote)
                    if len(market_volatility[symbol]) > 100:
                        market_volatility[symbol].pop(0)

        except Exception as e:
            print("Reconnecting WebSocket...", e)
            await asyncio.sleep(3)

# -------------------
# 🔥 SMART CANDLE READER (NEW)
# -------------------
def analyze_chart(image: Image):
    img = np.array(image.convert("L"))

    h, w = img.shape
    left = np.mean(img[:, :w//3])
    right = np.mean(img[:, -w//3:])
    trend = right - left

    vertical = np.mean(img, axis=1)
    wick_strength = np.std(vertical)

    momentum = np.std(np.diff(np.mean(img, axis=0)))

    # Detect direction
    if trend > 2 and momentum > 1:
        direction = "BUY"
    elif trend < -2 and momentum > 1:
        direction = "SELL"
    else:
        direction = "NO TRADE"

    # Simulated BoS / FVG
    bos = momentum > 1.2
    fvg = wick_strength > 20

    demand_zone = round(np.min(img)/255*100,2)
    supply_zone = round(np.max(img)/255*100,2)

    return direction, bos, fvg, demand_zone, supply_zone

# -------------------
# TP/SL WITH LEARNING
# -------------------
def calculate_tp_sl(direction, bos, fvg, vol):
    base = 100
    risk = max(1, np.std(vol)*50 + (5 if fvg else 0))

    bias = confidence_bias.get(direction, 0)
    risk *= (1 + bias)

    if direction == "BUY":
        sl = base - risk
        tp = base + risk*2
    else:
        sl = base + risk
        tp = base - risk*2

    distance = abs(tp - sl)

    if distance <= 5:
        timeframe = "M1"
    elif distance <= 10:
        timeframe = "M5"
    elif distance <= 20:
        timeframe = "M15"
    elif distance <= 40:
        timeframe = "M30"
    else:
        timeframe = "H1"

    return round(tp,2), round(sl,2), timeframe

# -------------------
# SAVE TRADE
# -------------------
def save_trade(symbol, direction, tp, sl, timeframe, demand_zone, supply_zone):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(TIMEZONE), symbol, direction, tp, sl, timeframe, demand_zone, supply_zone, "PENDING"
        ])

# -------------------
# UPDATE RESULT (LEARNING)
# -------------------
def update_last_result(result):
    rows = []
    with open(LOG_FILE, "r") as f:
        rows = list(csv.reader(f))

    rows[-1][-1] = result

    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerows(rows)

    last_direction = rows[-1][2]

    if result == "WIN":
        confidence_bias[last_direction] = confidence_bias.get(last_direction, 0) + 0.05
    else:
        confidence_bias[last_direction] = confidence_bias.get(last_direction, 0) - 0.05

# -------------------
# TELEGRAM HANDLERS
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send chart screenshot.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cooldown_tracker

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)
    image = Image.open(bio)

    # 🔥 SMART ANALYSIS
    direction, bos, fvg, demand_zone, supply_zone = analyze_chart(image)

    if direction == "NO TRADE":
        await update.message.reply_text("No valid setup.")
        return

    symbol = "SCREENSHOT"
    vol = market_volatility.get(symbol, [1]*10)

    tp, sl, timeframe = calculate_tp_sl(direction, bos, fvg, vol)

    now = datetime.now(TIMEZONE)
    last_time = cooldown_tracker.get(symbol)

    if last_time and (now - last_time).total_seconds() < 600:
        await update.message.reply_text("Cooldown active.")
        return

    cooldown_tracker[symbol] = now

    save_trade(symbol, direction, tp, sl, timeframe, demand_zone, supply_zone)

    keyboard = [[
        InlineKeyboardButton("✅ WIN", callback_data="win"),
        InlineKeyboardButton("❌ LOSS", callback_data="loss")
    ]]

    msg = f"""
📊 SIGNAL
Direction: {direction}
TP: {tp}
SL: {sl}
Timeframe: {timeframe}
Demand: {demand_zone}
Supply: {supply_zone}
"""

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "win":
        update_last_result("WIN")
        await query.edit_message_text("Recorded: WIN ✅")
    else:
        update_last_result("LOSS")
        await query.edit_message_text("Recorded: LOSS ❌")

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button))

    asyncio.create_task(market_listener())

    print("Bot running (SMART MODE)...")
    await app.run_polling()

# -------------------
# ENTRY POINT
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
