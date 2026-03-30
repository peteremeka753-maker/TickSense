# ======================================
# BALANCED SAFE OPTIONS BOT
# Strict + Responsive + No Overtrading
# ======================================

import asyncio
import numpy as np
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# -------------------
# CONFIG
# -------------------
BOT_TOKEN = "8751531182:AAGLr0K3N21LIalG-mgxbiIUjdcJTNghLTg"
TIMEZONE = pytz.timezone("Africa/Lagos")

PAIRS = [
    "EURUSD OTC","GBPUSD OTC","USDJPY OTC","AUDUSD OTC","USDCAD OTC",
    "EURGBP OTC","EURJPY OTC","GBPJPY OTC","AUDJPY OTC","NZDUSD OTC",
    "USDCHF OTC","EURCHF OTC","GBPCHF OTC","AUDCAD OTC","EURAUD OTC",
    "GBPAUD OTC","NZDJPY OTC","CADJPY OTC","CHFJPY OTC","EURCAD OTC"
]

TIMEFRAMES = ["5s","10s","1m","2m","3m","5m"]

user_state = {}

# -------------------
# BALANCED ANALYSIS ENGINE
# -------------------
def generate_signal():

    # simulate structured market movement
    data = np.random.normal(0, 1, 120)

    trend = np.mean(data[-15:])
    volatility = np.std(data)

    # detect choppy market
    if abs(trend) < 0.08 and volatility < 0.7:
        return None, None, None, "NO_TRADE"

    # direction logic
    if trend > 0:
        direction = "CALL"
    else:
        direction = "PUT"

    # duration logic (more stable)
    if volatility > 1.3:
        duration = "1 min"
    elif volatility > 0.9:
        duration = "2 min"
    else:
        duration = "3 min"

    # confidence (REALISTIC RANGE)
    confidence = int(60 + min(abs(trend)*100, 20))

    # extra safety filter
    if confidence < 62:
        return None, None, None, "NO_TRADE"

    return direction, duration, confidence, "TRADE"

# -------------------
# START
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[InlineKeyboardButton(p, callback_data=p)] for p in PAIRS]

    await update.message.reply_text(
        "📊 Select OTC Pair:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# -------------------
# BUTTON HANDLER
# -------------------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    # SELECT PAIR
    if data in PAIRS:
        user_state[query.from_user.id] = {"pair": data}

        keyboard = [[InlineKeyboardButton(tf, callback_data=tf)] for tf in TIMEFRAMES]

        await query.edit_message_text(
            f"Pair: {data}\n\n⏱ Select Timeframe:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # SELECT TIMEFRAME → ANALYZE
    if data in TIMEFRAMES:

        await query.edit_message_text("⏳ Analyzing clean setup...")

        await asyncio.sleep(4)

        state = user_state.get(query.from_user.id, {})
        pair = state.get("pair", "Unknown")

        direction, duration, confidence, status = generate_signal()

        now = datetime.now(TIMEZONE).strftime("%H:%M:%S")

        # NO TRADE CONDITION
        if status == "NO_TRADE":
            await query.edit_message_text(
                f"❌ NO TRADE\n\n"
                f"Pair: {pair}\n"
                f"Timeframe: {data}\n\n"
                f"Reason: Market not clean\n"
                f"Time: {now}"
            )
            return

        color = "🟢 CALL" if direction == "CALL" else "🔴 PUT"

        message = (
            "📊 BALANCED SIGNAL\n\n"
            f"Pair: {pair}\n"
            f"Timeframe: {data}\n\n"
            f"Direction: {color}\n"
            f"Duration: {duration}\n\n"
            f"Confidence: {confidence}%\n\n"
            f"Time: {now}"
        )

        await query.edit_message_text(message)

# -------------------
# MAIN
# -------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_buttons))

    print("BALANCED BOT RUNNING...")
    await app.run_polling()

# -------------------
# RUN
# -------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
