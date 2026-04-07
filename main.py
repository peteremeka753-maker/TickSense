# ======================================
# V4.1 + V4 MERGED DERIV AI TRADING SYSTEM
# FULL LIVE ENGINE + TELEGRAM + LEARNING + AUTO SYMBOLS
# ======================================

import os
import json
import csv
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

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LEARNING_FILE = os.path.join(DATA_DIR, "learning.json")

WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# =========================
# GLOBAL STATE
# =========================

tick_buffer = {}
learning = {}
pause_until = None
cooldown = {}

symbols = []

# =========================
# LOAD LEARNING
# =========================

def load_learning():
    global learning
    if os.path.exists(LEARNING_FILE):
        learning = json.load(open(LEARNING_FILE))
    else:
        learning = {}

def save_learning():
    with open(LEARNING_FILE, "w") as f:
        json.dump(learning, f)

# =========================
# AUTO SYMBOL LOADER
# =========================

async def load_symbols():
    global symbols

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "active_symbols": "full",
            "product_type": "basic"
        }))

        msg = await ws.recv()
        data = json.loads(msg)

        syms = []

        for item in data.get("active_symbols", []):
            s = item["symbol"]

            if s.startswith("frx") or s.startswith("R_") or "BTC" in s or "ETH" in s:
                syms.append(s)

        symbols = list(set(syms))

        for s in symbols:
            tick_buffer[s] = []

        print(f"Loaded {len(symbols)} symbols")

# =========================
# WEBSOCKET STREAM
# =========================

async def stream_ticks():

    async with websockets.connect(WS_URL) as ws:

        for s in symbols:
            await ws.send(json.dumps({
                "ticks": s,
                "subscribe": 1
            }))

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if "tick" in data:
                symbol = data["tick"]["symbol"]
                price = float(data["tick"]["quote"])

                if symbol in tick_buffer:
                    buf = tick_buffer[symbol]
                    buf.append(price)

                    if len(buf) > 50:
                        buf.pop(0)

# =========================
# ANALYSIS ENGINE
# =========================

def tick_analysis(symbol):
    buf = tick_buffer.get(symbol, [])

    if len(buf) < 10:
        return "NEUTRAL", 0

    diff = np.diff(buf[-20:])
    strength = np.mean(diff)

    return ("BUY", abs(strength)) if strength > 0 else ("SELL", abs(strength))


def image_analysis(image: Image.Image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)
    direction = "BUY" if np.sum(diff > 0) > np.sum(diff < 0) else "SELL"

    return direction, momentum


def decision_engine(img_dir, tick_dir, momentum, strength):

    score = 0

    if img_dir == tick_dir:
        score += 2
    else:
        score -= 1

    score += strength
    score += momentum / 10

    final = img_dir if score >= 1 else tick_dir

    return final, score

# =========================
# ENTRY LOGIC
# =========================

def entry_time():
    now = datetime.now(TIMEZONE)
    return now + timedelta(seconds=(60 - now.second))

def expiry(momentum, strength):
    score = momentum + strength
    if score > 2:
        return 1
    elif score > 1:
        return 3
    return 5

# =========================
# TELEGRAM HANDLERS
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global cooldown

    now = datetime.now(TIMEZONE)

    if cooldown.get("global") and (now - cooldown["global"]).seconds < 60:
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    symbol = symbols[0] if symbols else "R_100"

    img_dir, momentum = image_analysis(image)
    tick_dir, strength = tick_analysis(symbol)

    final, score = decision_engine(img_dir, tick_dir, momentum, strength)

    msg = (
        f"📊 MERGED V4 SYSTEM\n\n"
        f"Symbol: {symbol}\n"
        f"Direction: {final}\n"
        f"Score: {round(score,2)}\n"
        f"Entry: {entry_time().strftime('%H:%M:%S')}\n"
        f"Expiry: {expiry(momentum, strength)} min\n"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win_{symbol}_{final}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss_{symbol}_{final}")
    ]]

    cooldown["global"] = now

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# LEARNING SYSTEM
# =========================

def update_learning(symbol, direction, result):

    if symbol not in learning:
        learning[symbol] = {"BUY": 0.0, "SELL": 0.0}

    if result == "WIN":
        learning[symbol][direction] += 0.05
    else:
        learning[symbol][direction] -= 0.05

    save_learning()

# =========================
# BUTTONS
# =========================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, symbol, direction = query.data.split("_")

    update_learning(symbol, direction, "WIN" if result == "win" else "LOSS")

    await query.edit_message_text(f"Recorded {result.upper()}")

# =========================
# MAIN START
# =========================

async def main():

    load_learning()
    await load_symbols()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_buttons))

    asyncio.create_task(stream_ticks())

    print("MERGED V4 SYSTEM RUNNING...")

    await app.run_polling()

# =========================
# START
# =========================

if __name__ == "__main__":
    asyncio.run(main())
