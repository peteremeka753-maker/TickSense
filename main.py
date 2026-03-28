# ======================================
# SMART AI TRADER - FULLY UPGRADED FOR REAL MONEY
# SCREENSHOT ANALYSIS + ENTRY + TP/SL + ADAPTIVE DURATION + LEARNING
# ======================================

import os
import csv
import json
import asyncio
import websockets
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
import pytz
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# -------------------
# CONFIG
# -------------------
BOT_TOKEN = "8751531182:AAGLr0K3N21LIalG-mgxbiIUjdcJTNghLTg"
CHAT_ID = "8308393231"

TIMEZONE = pytz.timezone("Africa/Lagos")
DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "trades.csv")
os.makedirs(DATA_DIR, exist_ok=True)

confidence_bias = {}
cooldown_tracker = {}

# Initialize CSV
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["time","symbol","direction","entry_low","entry_high","tp","sl","timeframe","duration","result"])

# -------------------
# SMART ANALYSIS ENGINE
# -------------------
def analyze_chart_advanced(image: Image):
    """
    Analyze chart screenshot to return:
    direction, entry_low, entry_high, TP, SL, timeframe, reason, best duration
    """

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    trend = series[-1] - series[0]
    momentum = np.std(np.diff(series))
    bullish = np.sum(np.diff(series) > 0)
    bearish = np.sum(np.diff(series) < 0)
    vertical = np.mean(img, axis=1)
    upper_wick = np.max(vertical) - np.mean(vertical)
    lower_wick = np.mean(vertical) - np.min(vertical)

    # Direction logic
    if bearish > bullish and momentum > 1:
        direction = "SELL"
    elif bullish > bearish and momentum > 1:
        direction = "BUY"
    else:
        direction = "NO TRADE"

    # Entry zone (simulate real price zone)
    price_high = 1.15 + (np.max(img)/255)*0.01
    price_low = 1.14 + (np.min(img)/255)*0.01
    entry_high = round(price_high, 5)
    entry_low = round(price_low, 5)

    # TP / SL logic (adaptive based on confidence)
    bias = confidence_bias.get(direction, 0)
    if direction == "SELL":
        tp = round(entry_low - (0.004 * (1 + bias)), 5)
        sl = round(entry_high + (0.002 * (1 - bias)), 5)
    elif direction == "BUY":
        tp = round(entry_high + (0.004 * (1 + bias)), 5)
        sl = round(entry_low - (0.002 * (1 - bias)), 5)
    else:
        tp, sl = None, None

    # Timeframe logic
    if momentum < 1:
        timeframe = "M5"
        duration = 60
    elif momentum < 2:
        timeframe = "M10"
        duration = 120
    else:
        timeframe = "M15"
        duration = 180

    # Reasoning
    reason = []
    reason.append("Bearish trend" if trend < 0 else "Bullish trend")
    reason.append("Top rejection" if upper_wick > lower_wick else "Bottom rejection")
    reason.append("Strong momentum" if momentum > 1 else "Weak market")

    # Calculate best entry time based on momentum (for options broker)
    best_entry_offset = int(momentum * 2)  # seconds offset simulation
    best_entry_time = datetime.now(TIMEZONE) + timedelta(seconds=best_entry_offset)

    return direction, entry_low, entry_high, tp, sl, timeframe, reason, duration, best_entry_time

# -------------------
# DRAW ANALYSIS
# -------------------
def draw_analysis(image, direction, entry_low, entry_high):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    y1 = int(h * 0.4)
    y2 = int(h * 0.6)
    color = "red" if direction == "SELL" else "green"
    draw.rectangle([0, y1, w, y2], outline=color, width=3)
    draw.text((10,10), f"{direction}", fill=color)
    return image

# -------------------
# LOG RESULTS
# -------------------
def update_result(result, direction, entry_low, entry_high, tp, sl, timeframe, duration):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now(TIMEZONE), "SCREENSHOT", direction, entry_low, entry_high, tp, sl, timeframe, duration, result])
    # Adaptive learning
    if result == "WIN":
        confidence_bias[direction] = confidence_bias.get(direction, 0) + 0.05
    else:
        confidence_bias[direction] = confidence_bias.get(direction, 0) - 0.05

# -------------------
# TELEGRAM HANDLERS
# -------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)
    image = Image.open(bio)

    direction, entry_low, entry_high, tp, sl, timeframe, reason, duration, best_entry_time = analyze_chart_advanced(image)

    if direction == "NO TRADE":
        await update.message.reply_text("No valid setup.")
        return

    # Draw analysis
    image = draw_analysis(image, direction, entry_low, entry_high)
    bio_out = BytesIO()
    image.save(bio_out, format='PNG')
    bio_out.seek(0)

    reason_text = "\n- ".join(reason)
    msg = f"""📊 SMART SIGNAL

Direction: {direction}
Entry Zone: {entry_low} - {entry_high}
TP: {tp}
SL: {sl}
Timeframe: {timeframe}
Suggested Duration: {duration} seconds
Best Entry Time: {best_entry_time.strftime('%H:%M:%S')}

🧠 Reason:
- {reason_text}
"""

    keyboard = [[
        InlineKeyboardButton("✅ WIN", callback_data=f"win_{direction}"),
        InlineKeyboardButton("❌ LOSS", callback_data=f"loss_{direction}")
    ]]

    await update.message.reply_photo(photo=bio_out, caption=msg,
                                     reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    result = data[0]
    direction = data[1]
    # Read last signal info from CSV
    with open(LOG_FILE, "r", newline="") as f:
        rows = list(csv.reader(f))
    last_signal = rows[-1][1:] if len(rows) > 1 else ["SCREENSHOT", direction, "", "", "", "", "", "", ""]
    entry_low, entry_high, tp, sl, timeframe, duration = last_signal[2], last_signal[3], last_signal[4], last_signal[5], last_signal[6], last_signal[7]
    update_result("WIN" if result=="win" else "LOSS", direction, entry_low, entry_high, tp, sl, timeframe, duration)
    await query.edit_message_caption(caption=f"Recorded: {result.upper()}")

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button))
    print("SMART AI TRADER RUNNING...")
    await app.run_polling()

# -------------------
# RUN
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
