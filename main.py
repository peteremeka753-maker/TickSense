# ======================================
# V7 FUSION SYSTEM (BUY/SELL ONLY)
# IMAGE + MARKET STREAM MERGE ENGINE
# FRX + CRYPTO ONLY
# NO NEUTRAL OUTPUT (FORCED DECISION)
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

tick_buffer = []
symbols = []
current_symbol = None
stream_task = None

# =========================
# LOAD SYMBOLS
# =========================
async def load_symbols():
    global symbols
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "active_symbols": "full",
            "product_type": "basic"
        }))

        data = json.loads(await ws.recv())

        filtered = []
        for item in data.get("active_symbols", []):
            s = item["symbol"]
            if s.startswith("frx"):
                filtered.append(s.upper())
            elif "BTC" in s or "ETH" in s:
                filtered.append(s.upper())

        symbols = list(set(filtered))
        print(f"Loaded {len(symbols)} symbols")

# =========================
# LEARNING
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
# STREAM ENGINE
# =========================
async def stream(symbol):
    global tick_buffer, current_symbol

    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({
                    "ticks": symbol,
                    "subscribe": 1
                }))

                current_symbol = symbol
                tick_buffer = []

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if "tick" in data:
                        price = float(data["tick"]["quote"])
                        tick_buffer.append(price)

                        if len(tick_buffer) > 100:
                            tick_buffer.pop(0)

        except:
            await asyncio.sleep(2)

async def switch_symbol(symbol):
    global stream_task
    if stream_task:
        stream_task.cancel()
    stream_task = asyncio.create_task(stream(symbol))

# =========================
# IMAGE ANALYSIS (SYSTEM 1)
# =========================
def image_analysis(image):
    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)

    up = np.sum(diff > 0)
    down = np.sum(diff < 0)

    if up > down:
        return "BUY", momentum
    else:
        return "SELL", momentum

# =========================
# MARKET ANALYSIS (SYSTEM 2)
# =========================
def market_analysis():
    if len(tick_buffer) < 20:
        return 0

    diff = np.diff(tick_buffer[-20:])
    strength = np.mean(diff)

    return strength

# =========================
# FINAL DECISION ENGINE (NO NEUTRAL)
# =========================
def decision(img_dir, market_strength, momentum):
    score = 0

    # image bias
    if img_dir == "BUY":
        score += 2
    else:
        score -= 2

    # market bias
    if market_strength > 0:
        score += 1
    else:
        score -= 1

    # momentum weight
    score += (momentum / 30)

    # FORCE OUTPUT (NO NEUTRAL)
    if score >= 0:
        return "BUY", score
    else:
        return "SELL", score

# =========================
# PROCESS SIGNAL
# =========================
async def process_signal(update):
    symbol = session["symbol"]
    image = session["image"]

    img_dir, momentum = image_analysis(image)
    market_strength = market_analysis()

    final, score = decision(img_dir, market_strength, momentum)

    trade_id = f"{symbol}_{datetime.now().timestamp()}"

    active_trades[trade_id] = {
        "symbol": symbol,
        "direction": final
    }

    msg = (
        f"AI SIGNAL\n\n"
        f"PAIR: {symbol}\n"
        f"DIRECTION: {final}\n"
        f"CONFIDENCE: {round(score,2)}\n\n"
        f"TIME: {datetime.now(TIMEZONE).strftime('%H:%M:%S')}\n"
        f"EXPIRY: 2 MINUTES\n"
        f"STREAM: {current_symbol}"
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
    await switch_symbol(symbol)

    if not session["image"]:
        await update.message.reply_text("Send screenshot")
        return

    await process_signal(update)

# =========================
# CALLBACK
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

    await query.edit_message_text(f"{result.upper()} saved")

# =========================
# START
# =========================
async def start(app):
    await load_symbols()
    if symbols:
        await switch_symbol(symbols[0])

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

    print("V7 FUSION RUNNING (BUY/SELL ONLY)")
    app.run_polling()

if __name__ == "__main__":
    main()
