# ======================================
# SMART SAFE AI TRADER (REALISTIC VERSION)
# Improved Decision + Better Entry + Stable Signals
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
loss_streak = 0

# -------------------
# INIT CSV
# -------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["time","direction","duration","result"])

# -------------------
# SMART ANALYSIS ENGINE
# -------------------
def analyze_chart(image: Image):

    img = np.array(image.convert("L"))

    series = np.mean(img, axis=0)
    diff = np.diff(series)

    momentum = np.std(diff)
    bullish = np.sum(diff > 0)
    bearish = np.sum(diff < 0)

    strength = abs(bullish - bearish) / len(diff)

    # -------------------
    # SMART FILTER (LESS STRICT)
    # -------------------
    if momentum < 0.4:
        return "NO TRADE", None, None, ["Low volatility"]

    if strength < 0.05:
        return "NO TRADE", None, None, ["Market indecision"]

    # -------------------
    # DIRECTION
    # -------------------
    direction = "BUY" if bullish > bearish else "SELL"

    # -------------------
    # SMART DURATION
    # -------------------
    if momentum > 2.2:
        duration = 1
    elif momentum > 1.4:
        duration = 2
    elif momentum > 0.9:
        duration = 3
    else:
        duration = 5

    # -------------------
    # SMART ENTRY DELAY
    # -------------------
    if momentum > 2:
        entry_delay = 3   # fast entry (strong move)
    elif momentum > 1.2:
        entry_delay = 5
    else:
        entry_delay = 8   # wait more (safer)

    # -------------------
    # CONFIDENCE CHECK
    # -------------------
    confidence = momentum * strength

    if confidence < 0.05:
        return "NO TRADE", None, None, ["Low confidence"]

    # -------------------
    # REASON
    # -------------------
    reason = []
    reason.append("Bullish pressure" if direction=="BUY" else "Bearish pressure")
    reason.append(f"Momentum: {round(momentum,2)}")
    reason.append("High probability setup" if confidence > 0.1 else "Moderate setup")

    return direction, duration, entry_delay, reason

# -------------------
# SAVE RESULT
# -------------------
def update_result(result, direction):
    global loss_streak

    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now(TIMEZONE), direction, "", result])

    if result == "WIN":
        confidence_bias[direction] = confidence_bias.get(direction, 0) + 0.02
        loss_streak = 0
    else:
        confidence_bias[direction] = confidence_bias.get(direction, 0) - 0.02
        loss_streak += 1

# -------------------
# TELEGRAM HANDLER
# -------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global cooldown_tracker, loss_streak

    now = datetime.now(TIMEZONE)

    # -------------------
    # LOSS PROTECTION
    # -------------------
    if loss_streak >= 2:
        await update.message.reply_text("🛑 Trading paused (loss protection). Wait.")
        return

    # -------------------
    # COOLDOWN
    # -------------------
    last = cooldown_tracker.get("global")
    if last and (now - last).seconds < 90:
        await update.message.reply_text("⏳ Wait... market stabilizing.")
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    bio = BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    image = Image.open(bio)

    direction, duration, entry_delay, reason = analyze_chart(image)

    if direction == "NO TRADE":
        await update.message.reply_text("❌ No trade\nReason: " + reason[0])
        return

    cooldown_tracker["global"] = now

    reason_text = "\n- ".join(reason)

    entry_time = datetime.now(TIMEZONE) + timedelta(seconds=entry_delay)
    entry_time_str = entry_time.strftime("%H:%M:%S")

    msg = (
        "📊 SMART SAFE SIGNAL\n\n"
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
# BUTTON HANDLER (SAFE)
# -------------------
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    try:
        await query.answer()
    except:
        return

    try:
        data = query.data.split("_")
        result = data[0]
        direction = data[1]

        update_result("WIN" if result=="win" else "LOSS", direction)

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

    print("SMART SAFE BOT RUNNING...")

    await app.run_polling()

# -------------------
# RUN
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
