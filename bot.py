import os
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

def search_nearby(lat, lng, place_type, open_until_hour=None):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": 1000,
        "type": place_type,
        "opennow": "true",
        "key": GOOGLE_API_KEY,
    }
    response = requests.get(url, params=params).json()
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

def format_results(places):
    if not places:
        return "😔 No open places found within 1km."
    lines = []
    for i, p in enumerate(places[:5], 1):
        name = p.get("name")
        address = p.get("vicinity")
        rating = p.get("rating", "N/A")
        place_id = p.get("place_id")
        maps_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        lines.append(f"{i}. *{name}*\n📍 {address}\n⭐ {rating}\n🔗 [Open in Maps]({maps_link})")
    return "\n\n".join(lines)

async def supermarket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pending_search"] = {"type": "supermarket"}
    button = KeyboardButton("📍 Share my location", request_location=True)
    markup = ReplyKeyboardMarkup([[button]], one_time_keyboard=True)
    await update.message.reply_text("Share your location to find supermarkets near you:", reply_markup=markup)

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args).lower()
    hour = None
    for word in args.split():
        if word.isdigit():
            hour = int(word)
    context.user_data["pending_search"] = {"type": "supermarket", "open_until": hour}
    button = KeyboardButton("📍 Share my location", request_location=True)
    markup = ReplyKeyboardMarkup([[button]], one_time_keyboard=True)
    await update.message.reply_text(f"Looking for places open till {hour}:00. Share your location:", reply_markup=markup)

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    search = context.user_data.get("pending_search", {"type": "supermarket"})
    places = search_nearby(loc.latitude, loc.longitude, search["type"], search.get("open_until"))
    await update.message.reply_text(format_results(places), parse_mode="Markdown")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Kraków Places Bot!\n\n"
        "Commands:\n"
        "/supermarket — find open supermarkets within 1km\n"
        "/open till 6 pm — find places open until a specific time\n"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("supermarket", supermarket_command))
    app.add_handler(CommandHandler("open", open_command))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
