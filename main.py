# ======================================
# SAFE AI TRADER (NO GAMBLING VERSION)
# Screenshot → Smart Entry + Duration + Filter
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

confidence_bias = {}
cooldown_tracker = {}

# -------------------
# INIT CSV
# -------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["time","direction","duration","result"])

# -------------------
# SAFE ANALYSIS ENGINE
# -------------------
def analyze_chart_safe(image: Image):

    img = np.array(image.convert("L"))

    series = np.mean(img, axis=0)
    diff = np.diff(series)

    trend_strength = series[-1] - series[0]
    momentum = np.std(diff)

    bullish = np.sum(diff > 0)
    bearish = np.sum(diff < 0)

    # -------------------
    # STRICT TRADE FILTER (ANTI-GAMBLING)
    # -------------------
    if momentum < 0.8:
        return "NO TRADE", None, None, ["Market too slow"]

    if abs(bullish - bearish) < len(diff) * 0.1:
        return "NO TRADE", None, None, ["Market choppy"]

    # -------------------
    # DIRECTION
    # -------------------
    if bullish > bearish:
        direction = "BUY"
    else:
        direction = "SELL"

    # -------------------
    # SMART DURATION (FIXED PROBLEM)
    # -------------------
    if momentum > 2.5:
        duration = 1   # fast market
    elif momentum > 1.5:
        duration = 3
    else:
        duration = 5   # slow market

    # -------------------
    # ENTRY DELAY (VERY IMPORTANT FIX)
    # -------------------
    # Instead of instant entry, wait small time
    if momentum > 2:
        entry_delay = 5   # seconds
    else:
        entry_delay = 10

    # -------------------
    # REASON
    # -------------------
    reason = []
    reason.append("Bullish pressure" if direction=="BUY" else "Bearish pressure")
    reason.append("Strong momentum" if momentum > 1.5 else "Moderate momentum")
    reason.append("Filtered safe entry")

    return direction, duration, entry_delay, reason

# -------------------
# SAVE RESULT
# -------------------
def update_result(result, direction):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now(TIMEZONE), direction, "", result])

    if result == "WIN":
        confidence_bias[direction] = confidence_bias.get(direction, 0) + 0.02
    else:
        confidence_bias[direction] = confidence_bias.get(direction, 0) - 0.02

# -------------------
# TELEGRAM HANDLER
# -------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global cooldown_tracker

    now = datetime.now(TIMEZONE)

    # -------------------
    # COOLDOWN (ANTI OVERTRADING)
    # -------------------
    last = cooldown_tracker.get("global")
    if last and (now - last).seconds < 120:
        await update.message.reply_text("Wait... market stabilizing.")
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    direction, duration, entry_delay, reason = analyze_chart_safe(image)

    if direction == "NO TRADE":
        await update.message.reply_text("❌ No safe setup\nReason: " + reason[0])
        return

    cooldown_tracker["global"] = now

    # -------------------
    # BUILD MESSAGE (FIXED ERROR HERE)
    # -------------------
    reason_text = "\n- ".join(reason)

    entry_time = datetime.now(TIMEZONE) + timedelta(seconds=entry_delay)
    entry_time_str = entry_time.strftime("%H:%M:%S")

    msg = (
        "📊 SAFE SIGNAL\n\n"
        f"Direction: {direction}\n"
        f"Entry Time: {entry_time_str}\n"
        f"Duration: {duration} min\n\n"
        "🧠 Reason:\n"
        f"- {reason_text}"
    )

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
    await query.answer()

    data = query.data.split("_")
    result = data[0]
    direction = data[1]

    update_result("WIN" if result=="win" else "LOSS", direction)

    await query.edit_message_text(f"Recorded: {result.upper()}")

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
