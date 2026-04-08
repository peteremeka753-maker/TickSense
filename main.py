# ======================================
# V5 + V6 MERGED AI TRADING SYSTEM
# BUY + SELL SYSTEM FUSION ENGINE
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

BOT_TOKEN = "8783779196:AAGNldYhsoISW8GO21gVL9FSHcpsUj4Of6o"
TIMEZONE = pytz.timezone("Africa/Lagos")
WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

DATA_FILE = "learning.json"

learning = {}
active_trades = {}

tick_buffer = []

# =========================
# LOAD LEARNING
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
# IMAGE ANALYSIS (SYSTEM 1 + SYSTEM 2 COMBINED)
# =========================

def image_analysis(image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)

    up = np.sum(diff > 0)
    down = np.sum(diff < 0)

    # SYSTEM 1 STYLE
    direction_1 = "BUY" if up > down else "SELL"

    # SYSTEM 2 STYLE
    if up > down:
        direction_2 = "BUY"
    elif down > up:
        direction_2 = "SELL"
    else:
        direction_2 = "NEUTRAL"

    return direction_1, direction_2, momentum

# =========================
# MARKET ANALYSIS (SYSTEM 1 + SYSTEM 2 COMBINED)
# =========================

def market_analysis():

    if len(tick_buffer) < 10:
        return "BUY", "NEUTRAL", 0.5

    diff = np.diff(tick_buffer[-10:])
    strength = np.mean(diff)

    # SYSTEM 1 STYLE
    direction_1 = ("BUY", abs(strength)) if strength > 0 else ("SELL", abs(strength))

    # SYSTEM 2 STYLE
    if abs(strength) < 0.00001:
        direction_2 = "NEUTRAL"
    else:
        direction_2 = "BUY" if strength > 0 else "SELL"

    return direction_1[0], direction_2, direction_1[1]

# =========================
# FINAL FUSION ENGINE (NEW)
# =========================

def fusion_decision(img1, img2, mkt1, mkt2, momentum, strength):

    score_buy = 0
    score_sell = 0

    # image system vote
    if img1 == "BUY":
        score_buy += 1
    elif img1 == "SELL":
        score_sell += 1

    if img2 == "BUY":
        score_buy += 1
    elif img2 == "SELL":
        score_sell += 1

    # market system vote
    if mkt1 == "BUY":
        score_buy += 1
    elif mkt1 == "SELL":
        score_sell += 1

    if mkt2 == "BUY":
        score_buy += 1
    elif mkt2 == "SELL":
        score_sell += 1

    # momentum weighting
    score_buy += momentum / 50
    score_sell += momentum / 50

    # strength weighting
    score_buy += strength
    score_sell += strength

    if score_buy > score_sell:
        return "BUY", score_buy, score_sell
    elif score_sell > score_buy:
        return "SELL", score_buy, score_sell
    else:
        return "NEUTRAL", score_buy, score_sell

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

    img1, img2, momentum = image_analysis(image)
    mkt1, mkt2, strength = market_analysis()

    final, sb, ss = fusion_decision(img1, img2, mkt1, mkt2, momentum, strength)

    symbol = "USDCHF"
    t_id = trade_id(symbol)

    active_trades[t_id] = {
        "symbol": symbol,
        "direction": final
    }

    msg = (
        f"📊 MERGED AI SIGNAL\n\n"
        f"PAIR: {symbol}\n"
        f"FINAL: {final}\n"
        f"BUY SCORE: {round(sb,2)}\n"
        f"SELL SCORE: {round(ss,2)}\n"
        f"ENTRY: {datetime.now().strftime('%H:%M:%S')}\n"
        f"EXPIRY: 2 MINUTES\n"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win|{t_id}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss|{t_id}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# WIN / LOSS
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
# MAIN
# =========================

def main():

    load_learning()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(buttons))

    print("🚀 MERGED BUY + SELL SYSTEM RUNNING")

    app.run_polling()

if __name__ == "__main__":
    main()
