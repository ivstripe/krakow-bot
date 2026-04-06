import os
import logging
import requests
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Daily request counter
request_tracker = {
    "date": date.today(),
    "count": 0,
    "limit": 450
}

def check_and_increment_counter():
    today = date.today()
    if request_tracker["date"] != today:
        request_tracker["date"] = today
        request_tracker["count"] = 0
    if request_tracker["count"] >= request_tracker["limit"]:
        return False
    request_tracker["count"] += 1
    logger.info(f"API request #{request_tracker['count']} today")
    return True

def search_nearby(lat, lng, place_type, open_until_hour=None):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": 3000,
        "type": place_type,
        "opennow": "true",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10).json()
        status = response.get("status")
        logger.info(f"Google API status: {status}")

        if status == "OVER_QUERY_LIMIT":
            return "limit_exceeded"
        elif status == "REQUEST_DENIED":
            return "denied"
        elif status == "ZERO_RESULTS":
            return []
        elif status != "OK":
            return "error"

        results = response.get("results", [])

        if open_until_hour:
            filtered = []
            now = datetime.now()
            weekday = now.weekday()
            for place in results:
                periods = place.get("opening_hours", {}).get("periods", [])
                for period in periods:
                    if period.get("open", {}).get("day") == weekday:
                        close_time = period.get("close", {}).get("time", "2359")
                        if int(close_time) >= open_until_hour * 100:
                            filtered.append(place)
                            break
            return filtered
        return results

    except requests.exceptions.Timeout:
        return "timeout"
    except Exception as e:
        logger.error(f"API error: {e}")
        return "error"

def format_results(places, place_type):
    if not places:
        return f"😔 No open {place_type}s found within 1km."
    lines = []
    for i, p in enumerate(places[:5], 1):
        name = p.get("name")
        address = p.get("vicinity")
        rating = p.get("rating", "N/A")
        place_id = p.get("place_id")
        maps_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        lines.append(f"{i}. *{name}*\n📍 {address}\n⭐ {rating}\n🔗 [Open in Maps]({maps_link})")
    return "\n\n".join(lines)

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE, place_type: str, open_until_hour=None):
    context.user_data["pending_search"] = {
        "type": place_type,
        "open_until": open_until_hour
    }
    button = KeyboardButton("📍 Share my location", request_location=True)
    markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
    if open_until_hour:
        msg = f"Looking for {place_type}s open until {open_until_hour}:00. Share your location 👇"
    else:
        msg = f"Tap below to find open {place_type}s near you 👇"
    await update.message.reply_text(msg, reply_markup=markup)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Kraków Places Bot!\n\n"
        "Available commands:\n"
        "/supermarket — open supermarkets within 3km\n"
        "/pharmacy — open pharmacies within 3km\n"
        "/restaurant — open restaurants within 3km\n"
        "/bakery — open bakeries within 3km\n"
        "/cafe — open cafes within 3km\n"
        "/open 18 — find places open until 6pm\n\n"
        f"📊 Searches used today: {request_tracker['count']}/{request_tracker['limit']}"
    )

async def supermarket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_search(update, context, "supermarket")

async def pharmacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_search(update, context, "pharmacy")

async def restaurant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_search(update, context, "restaurant")

async def bakery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_search(update, context, "bakery")

async def cafe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_search(update, context, "cafe")

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hour = None
    for word in context.args:
        if word.isdigit():
            hour = int(word)
            break
    if not hour:
        await update.message.reply_text(
            "Please specify an hour. Example:\n/open 18 — finds places open until 6pm"
        )
        return
    await handle_search(update, context, "supermarket", open_until_hour=hour)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = date.today()
    if request_tracker["date"] != today:
        count = 0
    else:
        count = request_tracker["count"]
    remaining = request_tracker["limit"] - count
    await update.message.reply_text(
        f"📊 API Usage Today:\n\n"
        f"✅ Used: {count}\n"
        f"🔵 Remaining: {remaining}\n"
        f"📅 Resets: midnight\n"
        f"🔒 Daily limit: {request_tracker['limit']}"
    )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Location received!")

    if not check_and_increment_counter():
        await update.message.reply_text(
            "⚠️ Daily search limit reached (450 searches).\n"
            "The bot resets at midnight. Please try again tomorrow!",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    loc = update.message.location
    logger.info(f"Coordinates: {loc.latitude}, {loc.longitude}")

    await update.message.reply_text(
        "📍 Got your location! Searching nearby...",
        reply_markup=ReplyKeyboardRemove()
    )

    search = context.user_data.get("pending_search", {"type": "supermarket"})
    place_type = search.get("type", "supermarket")
    open_until = search.get("open_until")

    places = search_nearby(loc.latitude, loc.longitude, place_type, open_until)

    if places == "limit_exceeded":
        await update.message.reply_text(
            "⚠️ Google API daily limit reached. Bot will be available again tomorrow."
        )
    elif places == "denied":
        await update.message.reply_text(
            "❌ API access denied. Please contact the bot admin."
        )
    elif places == "timeout":
        await update.message.reply_text(
            "⏱ Request timed out. Please try again in a moment."
        )
    elif places == "error":
        await update.message.reply_text(
            "❌ Something went wrong. Please try again later."
        )
    else:
        result_text = format_results(places, place_type)
        await update.message.reply_text(result_text, parse_mode="Markdown")

def main():
    logger.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("supermarket", supermarket_command))
    app.add_handler(CommandHandler("pharmacy", pharmacy_command))
    app.add_handler(CommandHandler("restaurant", restaurant_command))
    app.add_handler(CommandHandler("bakery", bakery_command))
    app.add_handler(CommandHandler("cafe", cafe_command))
    app.add_handler(CommandHandler("open", open_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
