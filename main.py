# ======================================
# V7.1 GLOBAL STREAM AI BOT
# ALL FX + CRYPTO PARALLEL STREAM ENGINE
# BUY / SELL ONLY (FORCED OUTPUT)
# REAL 2-MIN EXPIRY ENGINE
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

session = {"image": None, "symbol": None}

# GLOBAL MULTI-STREAM STORAGE
tick_map = {}
symbols = []

# =========================
# LOAD SYMBOLS (FX + CRYPTO)
# =========================

async def load_symbols():
    global symbols

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "active_symbols": "full",
            "product_type": "basic"
        }))

        data = json.loads(await ws.recv())

        result = []
        for item in data.get("active_symbols", []):
            s = item["symbol"]

            if s.startswith("frx"):
                result.append(s.upper())

            elif "BTC" in s or "ETH" in s:
                result.append(s.upper())

        symbols = list(set(result))
        print(f"STREAM READY: {len(symbols)} symbols")

# =========================
# LEARNING SYSTEM
# =========================

def load_learning():
    global learning
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            learning = json.load(f)
    else:
        learning = {}

def save_learning():
    with open(DATA_FILE, "w") as f:
        json.dump(learning, f, indent=2)

# =========================
# GLOBAL STREAM ENGINE (ALL PAIRS)
# =========================

async def stream(symbol):
    if symbol not in tick_map:
        tick_map[symbol] = []

    while True:
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

                        tick_map[symbol].append(price)

                        if len(tick_map[symbol]) > 100:
                            tick_map[symbol].pop(0)

        except:
            await asyncio.sleep(2)

# =========================
# MARKET ANALYSIS (PER SYMBOL)
# =========================

def market_analysis(symbol):
    if symbol not in tick_map or len(tick_map[symbol]) < 20:
        return 0

    diff = np.diff(tick_map[symbol][-20:])
    return np.mean(diff)

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

    return ("BUY" if up > down else "SELL"), momentum

# =========================
# DECISION ENGINE (FORCED BUY/SELL)
# =========================

def decision(img_dir, market_strength, momentum):
    score = 0

    if img_dir == "BUY":
        score += 2
    else:
        score -= 2

    if market_strength > 0:
        score += 1
    else:
        score -= 1

    score += momentum / 30

    return ("BUY" if score >= 0 else "SELL"), score

# =========================
# TIME ENGINE (REAL 2 MIN)
# =========================

def get_times():
    now = datetime.now(TIMEZONE)
    expiry = now + timedelta(minutes=2)
    return now, expiry

# =========================
# PROCESS SIGNAL
# =========================

async def process_signal(update):
    symbol = session["symbol"]
    image = session["image"]

    img_dir, momentum = image_analysis(image)
    market_strength = market_analysis(symbol)

    final, score = decision(img_dir, market_strength, momentum)

    now, expiry = get_times()

    trade_id = f"{symbol}_{datetime.now().timestamp()}"

    active_trades[trade_id] = {
        "symbol": symbol,
        "direction": final
    }

    msg = (
        f"AI SIGNAL SYSTEM\n\n"
        f"PAIR: {symbol}\n"
        f"DIRECTION: {final}\n"
        f"CONFIDENCE: {round(score,2)}\n\n"
        f"ENTRY: {now.strftime('%H:%M:%S')}\n"
        f"EXPIRY: {expiry.strftime('%H:%M:%S')} (2 MIN)\n"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win|{trade_id}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss|{trade_id}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

    session["image"] = None
    session["symbol"] = None

# =========================
# HANDLERS
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    session["image"] = Image.open(bio)

    if not session["symbol"]:
        await update.message.reply_text("Send pair first")
        return

    await process_signal(update)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()

    if symbol not in symbols:
        await update.message.reply_text("Invalid pair")
        return

    session["symbol"] = symbol

    if not session["image"]:
        await update.message.reply_text("Send screenshot")
        return

    await process_signal(update)

# =========================
# CALLBACK BUTTONS
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    result, trade_id = query.data.split("|")

    trade = active_trades.get(trade_id)
    if not trade:
        await query.edit_message_text("Expired")
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

    await query.edit_message_text(f"{result.upper()} recorded")

# =========================
# START ALL STREAMS
# =========================

async def start(app):
    await load_symbols()

    for s in symbols:
        asyncio.create_task(stream(s))

# =========================
# MAIN
# =========================

def main():
    load_learning()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(buttons))

    app.post_init = start

    print("V7.1 GLOBAL STREAM RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
