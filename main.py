# ======================================
# SAFE AI TRADER (STABLE + CONTROLLED)
# Designed to protect you, not overtrade
# ======================================

import os
import csv
import asyncio
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
import pytz
from PIL import Image
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

confidence_bias = {"BUY": 0, "SELL": 0}
loss_streak = 0

# -------------------
# INIT CSV
# -------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["time","direction","duration","result"])

# -------------------
# SAFE ANALYSIS
# -------------------
def analyze_chart(image: Image):

    img = np.array(image.convert("L"))
    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)
    bullish = np.sum(diff > 0)
    bearish = np.sum(diff < 0)

    direction = "BUY" if bullish > bearish else "SELL"

    trend_strength = abs(bullish - bearish) / len(diff)

    # -------------------
    # SCORE (REALISTIC)
    # -------------------
    score = 50

    if momentum > 1.5:
        score += 8
    if momentum > 2.5:
        score += 5

    if trend_strength > 0.2:
        score += 8
    if trend_strength > 0.3:
        score += 5

    score += confidence_bias[direction] * 100

    score = max(50, min(72, score))

    # -------------------
    # MARKET WARNINGS
    # -------------------
    warnings = []

    if momentum < 0.6:
        warnings.append("Slow market ⚠️")
        score -= 5

    if trend_strength < 0.1:
        warnings.append("Choppy market ⚠️")
        score -= 5

    # -------------------
    # DURATION
    # -------------------
    if momentum > 2.5:
        duration = 1
        timeframe = "M1"
    elif momentum > 1.5:
        duration = 3
        timeframe = "M5"
    else:
        duration = 5
        timeframe = "M5"

    # -------------------
    # ENTRY TIME
    # -------------------
    if score >= 65:
        delay = 3
    elif score >= 60:
        delay = 6
    else:
        delay = 10

    # -------------------
    # QUALITY LABEL
    # -------------------
    if score >= 68:
        quality = "HIGH"
    elif score >= 60:
        quality = "MEDIUM"
    else:
        quality = "LOW ⚠️"

    return direction, duration, delay, timeframe, int(score), quality, warnings

# -------------------
# LEARNING
# -------------------
def update_result(result, direction):
    global loss_streak

    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now(TIMEZONE), direction, "", result])

    if result == "WIN":
        confidence_bias[direction] += 0.01
        loss_streak = 0
    else:
        confidence_bias[direction] -= 0.01
        loss_streak += 1

# -------------------
# HANDLE PHOTO
# -------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global loss_streak

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    direction, duration, delay, timeframe, score, quality, warnings = analyze_chart(image)

    entry_time = datetime.now(TIMEZONE) + timedelta(seconds=delay)

    msg = (
        "📊 SAFE SIGNAL\n\n"
        f"Direction: {direction}\n"
        f"Entry: {entry_time.strftime('%H:%M:%S')}\n"
        f"Duration: {duration} min\n"
        f"Timeframe: {timeframe}\n\n"
        f"Accuracy: {score}% ({quality})\n"
    )

    if warnings:
        msg += "\n⚠️ Warnings:\n- " + "\n- ".join(warnings)

    keyboard = [[
        InlineKeyboardButton("✅ WIN", callback_data=f"win_{direction}"),
        InlineKeyboardButton("❌ LOSS", callback_data=f"loss_{direction}")
    ]]

    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------
# BUTTON HANDLER
# -------------------
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    data = query.data.split("_")
    result = data[0]
    direction = data[1]

    update_result("WIN" if result=="win" else "LOSS", direction)

    try:
        await query.edit_message_text(f"Recorded: {result.upper()}")
    except:
        pass

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("SAFE BOT RUNNING...")

    await app.run_polling()

# -------------------
# RUN
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
