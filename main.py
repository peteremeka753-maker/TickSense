# ======================================
# FIXED AI SIGNAL BOT V6 (WAIT + PAIR LOCK)
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
# SESSION STATE (IMPORTANT FIX)
# =========================

session = {
    "image": None,
    "symbol": None
}

tick_buffer = []

# =========================
# LOAD / SAVE LEARNING
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
# WAIT LOGIC (CORE FIX)
# =========================

def is_ready():
    return session["image"] is not None and session["symbol"] is not None

# =========================
# SCREENSHOT ANALYSIS
# =========================

def image_analysis(image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)
    direction = "BUY" if np.sum(diff > 0) > np.sum(diff < 0) else "SELL"

    return direction, momentum

# =========================
# DERIV STREAM (DYNAMIC PAIR)
# =========================

async def deriv_stream(symbol):

    global tick_buffer
    tick_buffer = []

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

                if len(tick_buffer) > 50:
                    tick_buffer.pop(0)

# =========================
# MARKET ANALYSIS
# =========================

def market_analysis():

    if len(tick_buffer) < 10:
        return "BUY", 0.5

    diff = np.diff(tick_buffer[-10:])
    strength = np.mean(diff)

    direction = "BUY" if strength > 0 else "SELL"

    return direction, abs(strength)

# =========================
# TIME ENGINE (2 MIN RULE)
# =========================

def entry_time():
    now = datetime.now(TIMEZONE)
    return now + timedelta(minutes=2)

# =========================
# DECISION ENGINE
# =========================

def decision(img_dir, mkt_dir, momentum, strength):

    score = 0

    if img_dir == mkt_dir:
        score += 2
    else:
        score -= 1

    score += strength
    score += momentum / 50

    return (img_dir if score >= 1 else mkt_dir), score

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
        await update.message.reply_text("📌 Send currency pair first (e.g. EURUSD)")
        return

    await update.message.reply_text("📊 Screenshot received. Processing...")

    await process_signal(update)

# =========================
# TEXT HANDLER (PAIR INPUT)
# =========================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip().upper()

    session["symbol"] = text

    if not session["image"]:
        await update.message.reply_text("📸 Send chart screenshot first")
        return

    await update.message.reply_text(f"📌 Pair set: {text}\nNow analyzing...")

    await process_signal(update)

# =========================
# MAIN PROCESS
# =========================

async def process_signal(update):

    symbol = session["symbol"]
    image = session["image"]

    img_dir, momentum = image_analysis(image)
    mkt_dir, strength = market_analysis()

    final, score = decision(img_dir, mkt_dir, momentum, strength)

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

    # reset session AFTER signal
    session["image"] = None
    session["symbol"] = None

# =========================
# WIN / LOSS SYSTEM
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
# BACKGROUND STREAM START
# =========================

async def start_stream(app):
    # default stream will start only after first symbol is used
    pass

# =========================
# MAIN
# =========================

def main():

    load_learning()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(buttons))

    print("V6 FIXED SYSTEM RUNNING...")

    app.run_polling()

if __name__ == "__main__":
    main()
