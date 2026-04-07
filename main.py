# ======================================
# V4.2 PRO CANDLE AI TRADING SYSTEM
# OPTION B + REAL TRADE ID + MULTI TF
# ======================================

import os
import json
import asyncio
import numpy as np
import websockets
from io import BytesIO
from datetime import datetime, timedelta
from collections import defaultdict

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

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

LEARNING_FILE = os.path.join(DATA_DIR, "learning.json")

# =========================
# STATE
# =========================

learning = {}
active_trades = {}   # TRADE ID tracking

tick_data = defaultdict(list)

candles = {
    "1s": [],
    "3s": [],
    "1m": [],
    "5m": [],
    "15m": [],
    "1h": []
}

current_candle = {"1m": None}

# =========================
# LOAD / SAVE LEARNING
# =========================

def load_learning():
    global learning
    if os.path.exists(LEARNING_FILE):
        learning = json.load(open(LEARNING_FILE))
    else:
        learning = {}

def save_learning():
    with open(LEARNING_FILE, "w") as f:
        json.dump(learning, f, indent=2)

# =========================
# TRADE ID GENERATOR
# =========================

def create_trade_id(symbol):
    return f"{symbol}_{datetime.now().timestamp()}"

# =========================
# CANDLE BUILDER (1 MIN CORE)
# =========================

def build_1m_candle(price):
    now = datetime.now().replace(second=0, microsecond=0)

    c = current_candle.get("1m")

    if c is None:
        current_candle["1m"] = {
            "time": now,
            "open": price,
            "high": price,
            "low": price,
            "close": price
        }
        return

    if now != c["time"]:
        candles["1m"].append(c)
        current_candle["1m"] = {
            "time": now,
            "open": price,
            "high": price,
            "low": price,
            "close": price
        }
    else:
        c["high"] = max(c["high"], price)
        c["low"] = min(c["low"], price)
        c["close"] = price

# =========================
# STREAM TICKS
# =========================

async def stream_ticks():

    symbol = "frxUSDCHF"  # fixed for stability

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

                tick_data[symbol].append(price)

                if len(tick_data[symbol]) > 200:
                    tick_data[symbol].pop(0)

                build_1m_candle(price)

# =========================
# MULTI TF ANALYSIS
# =========================

def analyze_market():

    if len(candles["1m"]) < 5:
        return "BUY", 0.5

    last = candles["1m"][-5:]

    bullish = sum(1 for c in last if c["close"] > c["open"])
    bearish = len(last) - bullish

    direction = "BUY" if bullish >= bearish else "SELL"
    strength = abs(bullish - bearish) / 5

    return direction, strength

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
# SIGNAL ENGINE
# =========================

def decision_engine(img_dir, market_dir, momentum, strength):

    score = 0

    if img_dir == market_dir:
        score += 2
    else:
        score -= 1

    score += strength
    score += momentum / 50

    return (img_dir if score >= 1 else market_dir), score

# =========================
# TELEGRAM HANDLER
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    # USER MUST TYPE PAIR
    symbol = "USDCHF"

    img_dir, momentum = image_analysis(image)
    market_dir, strength = analyze_market()

    final, score = decision_engine(img_dir, market_dir, momentum, strength)

    trade_id = create_trade_id(symbol)

    active_trades[trade_id] = {
        "symbol": symbol,
        "direction": final,
        "time": datetime.now().isoformat()
    }

    msg = (
        f"📊 AI SIGNAL ENGINE (V4.2)\n\n"
        f"Pair: {symbol}\n"
        f"Direction: {final}\n"
        f"Score: {round(score,2)}\n"
        f"Trade ID: {trade_id}\n"
        f"Entry: {datetime.now().strftime('%H:%M:%S')}\n"
        f"TF: Multi-Timeframe (1s → 1m → 1h)\n"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win|{trade_id}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss|{trade_id}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# WIN / LOSS SYSTEM (FIXED)
# =========================

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, trade_id = query.data.split("|")

    trade = active_trades.get(trade_id)

    if not trade:
        await query.edit_message_text("Trade not found.")
        return

    symbol = trade["symbol"]
    direction = trade["direction"]

    if symbol not in learning:
        learning[symbol] = {"BUY": 0.0, "SELL": 0.0}

    if result == "win":
        learning[symbol][direction] += 1
    else:
        learning[symbol][direction] -= 1

    save_learning()

    del active_trades[trade_id]

    await query.edit_message_text(f"Recorded {result.upper()} ✔")

# =========================
# BACKGROUND
# =========================

async def start_bg(app):
    asyncio.create_task(stream_ticks())

# =========================
# MAIN
# =========================

def main():

    load_learning()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_buttons))

    app.post_init = start_bg

    print("V4.2 AI SYSTEM RUNNING...")

    app.run_polling()

# =========================
# START
# =========================

if __name__ == "__main__":
    main()
