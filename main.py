# ======================================
# REAL HYBRID AI TRADING BOT
# Screenshot + DRIFT WebSocket + Learning Engine
# ======================================

import os
import csv
import json
import asyncio
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
import pytz
from PIL import Image
import websockets
import threading

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

TRADE_LOG = os.path.join(DATA_DIR, "trades.csv")
LEARNING_FILE = os.path.join(DATA_DIR, "learning.json")

SYMBOL = "R_100"  # DRIFT (Deriv) synthetic index

# =========================
# GLOBAL STATE
# =========================

loss_streak = 0
pause_until = None
cooldown = {}

tick_buffer = []
learning = {"BUY": 0.0, "SELL": 0.0}

# =========================
# INIT FILES
# =========================

if not os.path.exists(TRADE_LOG):
    with open(TRADE_LOG, "w", newline="") as f:
        csv.writer(f).writerow(["time", "direction", "result"])

if os.path.exists(LEARNING_FILE):
    with open(LEARNING_FILE, "r") as f:
        learning = json.load(f)

def save_learning():
    with open(LEARNING_FILE, "w") as f:
        json.dump(learning, f)

# =========================
# DRIFT WEBSOCKET (REAL TICKS)
# =========================

async def drift_ticks():
    global tick_buffer

    url = "wss://ws.binaryws.com/websockets/v3?app_id=1089"

    while True:
        try:
            async with websockets.connect(url) as ws:

                await ws.send(json.dumps({
                    "ticks": SYMBOL,
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

        except Exception as e:
            print("WebSocket reconnecting...", e)
            await asyncio.sleep(3)

# =========================
# TICK ANALYSIS ENGINE
# =========================

def analyze_ticks():
    if len(tick_buffer) < 10:
        return "NEUTRAL", 0

    diff = np.diff(tick_buffer[-20:])
    strength = np.mean(diff)

    if strength > 0:
        return "BUY", abs(strength)
    else:
        return "SELL", abs(strength)

# =========================
# SCREENSHOT ANALYSIS
# =========================

def analyze_chart(image: Image.Image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)
    bullish = np.sum(diff > 0)

    direction = "BUY" if bullish > len(diff)/2 else "SELL"

    return direction, momentum

# =========================
# FINAL DECISION ENGINE
# =========================

def decision_engine(img_direction, momentum):

    tick_direction, strength = analyze_ticks()

    confidence = 0

    # screenshot weight
    if img_direction == tick_direction:
        confidence += 2
    else:
        confidence -= 1

    # tick strength weight
    confidence += strength

    # momentum weight
    confidence += momentum / 10

    if confidence > 2:
        return img_direction, "HIGH"
    elif confidence > 0:
        return img_direction, "MEDIUM"
    else:
        return tick_direction, "LOW"

# =========================
# LEARNING SYSTEM
# =========================

def update_learning(direction, result):
    global loss_streak, pause_until

    if result == "WIN":
        learning[direction] += 0.05
        loss_streak = 0
    else:
        learning[direction] -= 0.05
        loss_streak += 1

    save_learning()

    if loss_streak >= 3:
        pause_until = datetime.now(TIMEZONE) + timedelta(minutes=10)

# =========================
# TELEGRAM HANDLER
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global cooldown, pause_until

    now = datetime.now(TIMEZONE)

    if pause_until and now < pause_until:
        await update.message.reply_text("⛔ Bot cooling down after losses.")
        return

    if cooldown.get("global") and (now - cooldown["global"]).seconds < 60:
        await update.message.reply_text("⏳ Wait a moment...")
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    img_dir, momentum = analyze_chart(image)

    final_dir, strength = decision_engine(img_dir, momentum)

    entry_time = datetime.now(TIMEZONE) + timedelta(minutes=2)

    duration = 1 if strength == "HIGH" else 3 if strength == "MEDIUM" else 5

    cooldown["global"] = now

    msg = (
        f"📊 REAL HYBRID SIGNAL\n\n"
        f"Direction: {final_dir}\n"
        f"Strength: {strength}\n"
        f"Entry: {entry_time.strftime('%H:%M:%S')}\n"
        f"Duration: {duration} min\n"
    )

    keyboard = [[
        InlineKeyboardButton("WIN", callback_data=f"win_{final_dir}"),
        InlineKeyboardButton("LOSS", callback_data=f"loss_{final_dir}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# BUTTON HANDLER
# =========================

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    result, direction = query.data.split("_")

    update_learning(direction, "WIN" if result == "win" else "LOSS")

    await query.edit_message_text(f"Recorded: {result.upper()}")

# =========================
# MAIN BOT
# =========================

async def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button))

    loop = asyncio.get_event_loop()
    loop.create_task(drift_ticks())

    print("REAL HYBRID BOT RUNNING...")
    await app.run_polling()

# =========================
# START
# =========================

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
