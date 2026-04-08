# ======================================
# FINAL V5 AI TRADING BOT (2-MIN SYSTEM)
# SCREENSHOT + DERIV WS + LEARNING FIXED
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

def trade_id(symbol):
    return f"{symbol}_{datetime.now().timestamp()}"

# =========================
# SCREENSHOT ANALYSIS
# =========================

def image_analysis(image: Image.Image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)

    direction = "BUY" if np.sum(diff > 0) > np.sum(diff < 0) else "SELL"

    return direction, momentum

# =========================
# DERIV LIVE TICKS
# =========================

async def deriv_stream(symbol="frxUSDCHF"):

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

# =========================
# MARKET CONFIRMATION
# =========================

def market_analysis():

    if len(tick_buffer) < 10:
        return "BUY", 0.5

    diff = np.diff(tick_buffer[-10:])
    strength = np.mean(diff)

    return ("BUY", abs(strength)) if strength > 0 else ("SELL", abs(strength))

# =========================
# ENTRY + EXPIRY RULE
# =========================

def entry_time():
    now = datetime.now(TIMEZONE)
    return now + timedelta(minutes=2)

def expiry_time():
    return 2  # fixed

# =========================
# MAIN SIGNAL ENGINE
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

    symbol = "USDCHF"  # user input in real version

    img_dir, momentum = image_analysis(image)
    mkt_dir, strength = market_analysis()

    final, score = decision(img_dir, mkt_dir, momentum, strength)

    t_id = trade_id(symbol)

    active_trades[t_id] = {
        "symbol": symbol,
        "direction": final
    }

    msg = (
        f"📊 AI 2-MIN TRADING SYSTEM\n\n"
        f"Pair: {symbol}\n"
        f"Direction: {final}\n"
        f"Score: {round(score,2)}\n"
        f"Entry: {entry_time().strftime('%H:%M:%S')}\n"
        f"Expiry: 2 MINUTES\n"
        f"Trade ID: {t_id}\n"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win|{t_id}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss|{t_id}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# WIN / LOSS FIXED
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, t_id = query.data.split("|")

    trade = active_trades.get(t_id)

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
    del active_trades[t_id]

    await query.edit_message_text(f"{result.upper()} recorded ✔")

# =========================
# BACKGROUND
# =========================

async def start(app):
    asyncio.create_task(deriv_stream())

# =========================
# MAIN
# =========================

def main():

    load_learning()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(buttons))

    app.post_init = start

    print("V5 AI BOT RUNNING...")

    app.run_polling()

if __name__ == "__main__":
    main()
