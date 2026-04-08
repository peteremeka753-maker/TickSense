# ======================================
# V6 CHOCOLATE FIX (STABLE + REAL TICKS + CANDLES)
# FRX + CRYPTO ONLY
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

learning = {}
active_trades = {}

session = {"image": None, "symbol": None}

tick_buffer = []
candle_buffer = []

current_symbol = None
stream_task = None


# =========================
# TICK STREAM (FIXED STABLE)
# =========================
async def deriv_stream(symbol):

    global tick_buffer, current_symbol, candle_buffer

    while True:
        try:
            async with websockets.connect(WS_URL) as ws:

                await ws.send(json.dumps({
                    "ticks": symbol,
                    "subscribe": 1
                }))

                current_symbol = symbol
                tick_buffer = []
                candle_buffer = []

                print(f"STREAMING: {symbol}")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if "tick" in data:
                        price = float(data["tick"]["quote"])
                        tick_buffer.append(price)

                        # keep buffer clean
                        if len(tick_buffer) > 200:
                            tick_buffer.pop(0)

                        # build simple candles (5 ticks per candle)
                        if len(tick_buffer) % 5 == 0:
                            chunk = tick_buffer[-5:]
                            candle = {
                                "open": chunk[0],
                                "close": chunk[-1],
                                "high": max(chunk),
                                "low": min(chunk)
                            }
                            candle_buffer.append(candle)

                            if len(candle_buffer) > 50:
                                candle_buffer.pop(0)

        except Exception as e:
            print("RECONNECTING STREAM...", e)
            await asyncio.sleep(2)


# =========================
# SWITCH SYMBOL
# =========================
async def switch_symbol(symbol):
    global stream_task

    if stream_task:
        stream_task.cancel()

    stream_task = asyncio.create_task(deriv_stream(symbol))


# =========================
# IMAGE ANALYSIS (LIGHT FIX)
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
    elif down > up:
        return "SELL", momentum
    else:
        return "NEUTRAL", momentum


# =========================
# MARKET ANALYSIS (FIXED - NO SELL BIAS)
# =========================
def market_analysis():

    if len(candle_buffer) < 10:
        return "NEUTRAL", 0

    last = candle_buffer[-10:]

    bullish = sum(1 for c in last if c["close"] > c["open"])
    bearish = sum(1 for c in last if c["close"] < c["open"])

    strength = abs(bullish - bearish)

    if strength < 2:
        return "NEUTRAL", strength

    if bullish > bearish:
        return "BUY", strength
    else:
        return "SELL", strength


# =========================
# DECISION ENGINE (BALANCED)
# =========================
def decision(img_dir, mkt_dir, momentum, strength):

    score = 0

    if img_dir == mkt_dir:
        score += 2
    elif mkt_dir != "NEUTRAL":
        score -= 1

    score += strength * 0.8
    score += momentum / 50

    if score > 2:
        return img_dir, score
    elif score < -2:
        return mkt_dir, score
    else:
        return "NEUTRAL", score


# =========================
# ENTRY TIME
# =========================
def entry_time():
    return datetime.now(TIMEZONE) + timedelta(minutes=2)


# =========================
# PROCESS SIGNAL
# =========================
async def process_signal(update):

    image = session["image"]
    symbol = session["symbol"]

    img_dir, momentum = image_analysis(image)
    mkt_dir, strength = market_analysis()

    final, score = decision(img_dir, mkt_dir, momentum, strength)

    trade_id = f"{symbol}_{datetime.now().timestamp()}"

    active_trades[trade_id] = {
        "symbol": symbol,
        "direction": final
    }

    msg = (
        f"📊 V6 CHOCOLATE SIGNAL\n\n"
        f"PAIR: {symbol}\n"
        f"DIRECTION: {final}\n"
        f"CONFIDENCE: {round(score,2)}\n\n"
        f"ENTRY: {entry_time().strftime('%H:%M:%S')}\n"
        f"EXPIRY: 2 MIN\n"
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
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    symbol = update.message.text.strip().upper()

    session["symbol"] = symbol

    await switch_symbol(symbol)

    if not session["image"]:
        await update.message.reply_text(f"PAIR SET: {symbol}\nSEND SCREENSHOT")
        return

    await process_signal(update)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    session["image"] = Image.open(bio)

    if not session["symbol"]:
        await update.message.reply_text("SEND PAIR FIRST")
        return

    await process_signal(update)


# =========================
# START STREAM ON BOOT
# =========================
async def start_background(app):
    pass  # starts only after user selects pair


# =========================
# MAIN
# =========================
def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(lambda u, c: None))

    app.post_init = start_background

    print("🔥 V6 CHOCOLATE FIX RUNNING")

    app.run_polling()


if __name__ == "__main__":
    main()
