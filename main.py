# ======================================
# FIXED AI SIGNAL BOT V6 (REAL FIXED)
# SCREENSHOT + MANUAL PAIR + DERIV WS
# 2-MIN EXPIRY SYSTEM (STRICT)
# ======================================

import os
import json
import asyncio
import numpy as np
import websockets
from io import BytesIO
from datetime import datetime, timedelta

import pytz
from PIL import Image

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = "8783779196:AAGNldYhsoISW8GO21gVL9FSHcpsUj4Of6o"
TIMEZONE = pytz.timezone("Africa/Lagos")
WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

DATA_FILE = "learning.json"

learning = {}
active_trades = {}

# =========================
# SESSION STATE
# =========================

session = {
    "image": None,
    "symbol": None
}

tick_buffer = []
stream_task = None

# =========================
# LOAD / SAVE
# =========================

def load_learning():
    global learning
    if os.path.exists(DATA_FILE):
        learning = json.load(open(DATA_FILE))
    else:
        learning = {}

def save_learning():
    with open(DATA_FILE, "w") as f:
        json.dump(learning, f, indent=2)

# =========================
# TRADE ID
# =========================

def create_trade_id(symbol):
    return f"{symbol}_{datetime.now().timestamp()}"

# =========================
# IMAGE ANALYSIS
# =========================

def image_analysis(image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)

    up = np.sum(diff > 0)
    down = np.sum(diff < 0)

    if abs(up - down) < len(diff) * 0.1:
        return "NEUTRAL", momentum

    direction = "BUY" if up > down else "SELL"

    return direction, momentum

# =========================
# DERIV STREAM
# =========================

async def deriv_stream(symbol):

    global tick_buffer
    tick_buffer = []

    try:
        async with websockets.connect(WS_URL) as ws:

            await ws.send(json.dumps({
                "ticks": symbol,
                "subscribe": 1
            }))

            while True:
                msg = await ws.recv()
                data = json.loads(msg)

                if "tick" in data:
                    price = float(data["tick"]["quote"])
                    tick_buffer.append(price)

                    if len(tick_buffer) > 100:
                        tick_buffer.pop(0)

    except Exception as e:
        print("WebSocket error:", e)

# =========================
# MARKET ANALYSIS
# =========================

def market_analysis():

    if len(tick_buffer) < 15:
        return "NEUTRAL", 0

    diff = np.diff(tick_buffer[-20:])
    strength = np.mean(diff)

    if abs(strength) < 0.00001:
        return "NEUTRAL", 0

    direction = "BUY" if strength > 0 else "SELL"

    return direction, abs(strength)

# =========================
# TIME ENGINE
# =========================

def entry_time():
    now = datetime.now(TIMEZONE)
    return now + timedelta(minutes=2)

# =========================
# DECISION ENGINE
# =========================

def decision(img_dir, mkt_dir, momentum, strength):

    if mkt_dir == "NEUTRAL":
        return img_dir, momentum

    score = 0

    if img_dir == mkt_dir:
        score += 2
    else:
        score -= 1

    score += strength
    score += momentum / 50

    final = img_dir if score >= 1 else mkt_dir

    return final, score

# =========================
# PHOTO HANDLER
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    session["image"] = image

    if not session["symbol"]:
        await update.message.reply_text("📌 Send currency pair first (e.g. frxEURUSD)")
        return

    await update.message.reply_text("📊 Screenshot received. Processing...")

    await process_signal(update)

# =========================
# TEXT HANDLER
# =========================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global stream_task

    text = update.message.text.strip()

    session["symbol"] = text

    # 🔥 START REAL STREAM HERE
    if stream_task:
        stream_task.cancel()

    stream_task = asyncio.create_task(deriv_stream(text))

    if not session["image"]:
        await update.message.reply_text("📸 Send chart screenshot first")
        return

    await update.message.reply_text(f"📌 Pair set: {text}\nAnalyzing...")

    await process_signal(update)

# =========================
# PROCESS SIGNAL
# =========================

async def process_signal(update):

    symbol = session["symbol"]
    image = session["image"]

    img_dir, momentum = image_analysis(image)
    mkt_dir, strength = market_analysis()

    final, score = decision(img_dir, mkt_dir, momentum, strength)

    if final == "NEUTRAL":
        await update.message.reply_text("⚠️ Market unclear. No trade.")
        return

    trade_id = create_trade_id(symbol)

    active_trades[trade_id] = {
        "symbol": symbol,
        "direction": final
    }

    msg = (
        f"📊 AI SIGNAL SYSTEM (V6 FIXED)\n\n"
        f"PAIR: {symbol}\n"
        f"DIRECTION: {final}\n"
        f"CONFIDENCE: {round(score,2)}\n\n"
        f"ENTRY TIME: {entry_time().strftime('%H:%M:%S')}\n"
        f"EXPIRY: 2 MINUTES\n"
        f"TRADE ID: {trade_id}"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win|{trade_id}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss|{trade_id}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

    session["image"] = None
    session["symbol"] = None

# =========================
# BUTTON HANDLER
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, trade_id = query.data.split("|")

    trade = active_trades.get(trade_id)

    if not trade:
        await query.edit_message_text("Trade not found")
        return

    symbol = trade["symbol"]
    direction = trade["direction"]

    if symbol not in learning:
        learning[symbol] = {"BUY": 0, "SELL": 0}

    if result == "win":
        learning[symbol][direction] += 1
    else:
        learning[symbol][direction] -= 1

    save_learning()
    del active_trades[trade_id]

    await query.edit_message_text(f"{result.upper()} recorded ✔")

# =========================
# MAIN
# =========================

def main():

    load_learning()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(buttons))

    print("V6 REAL FIX RUNNING...")

    app.run_polling()

if __name__ == "__main__":
    main()
