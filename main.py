

import logging
import os
import random
import re
import requests
import json
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

from dotenv import load_dotenv
load_dotenv()

from dotenv import load_dotenv
load_dotenv()

USER_DATA_FILE = 'users.json'
user_states = {}
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
TIMEZONEDB_API_KEY = os.getenv('TIMEZONEDB_API_KEY')

# Для отладки, можно временно включить:
print("TELEGRAM_TOKEN:", TELEGRAM_TOKEN)

def save_user_states():
    global user_states
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_states, f, ensure_ascii=False, indent=2)

def load_user_states():
    global user_states
    try:
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            user_states = json.load(f)
    except Exception:
        user_states = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

main_keyboard = ReplyKeyboardMarkup([
    [
        KeyboardButton("Добавить город 🏙️"),
        KeyboardButton("Удалить город 🗑️")
    ],
    [
        KeyboardButton("Показать погоду 🌦️"),
        KeyboardButton("Установить время ⏰")
    ]
], resize_keyboard=True)

scheduler = BackgroundScheduler()

async def get_weather(city):
    try:
        translate_url = "https://libretranslate.de/translate"
        payload = {
            "q": city,
            "source": "ru",
            "target": "en",
            "format": "text"
        }
        resp = requests.post(translate_url, json=payload, timeout=5)
        if resp.status_code == 200:
            city_en = resp.json().get("translatedText", city)
        else:
            city_en = city
    except Exception:
        city_en = city
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_en}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('cod') != 200:
            return f"Не удалось получить погоду для {city}."
        temp = data['main']['temp']
        desc = data['weather'][0]['description']
        return f"Погода в {city}: {desc}, {temp}°C."
    except Exception as e:
        return f"Ошибка: {e}"

def get_wish():
    wishes = [
        "Желаю отличного дня и прекрасного настроения! 😊🌞",
        "Пусть сегодня всё получится! 💪✨",
        "Солнечного настроения и удачи! ☀️🍀",
        "Пусть день будет лёгким и радостным! 🕊️😃",
        "Пусть погода радует, а дела спорятся! 🌤️📈",
        "Хорошего дня и приятных сюрпризов! 🎁😄",
        "Пусть каждый момент сегодня будет счастливым! 🥳🌈",
        "Пусть улыбка не сходит с лица! 😁😊",
        "Пусть день принесёт только хорошие новости! 📰👍",
        "Пусть всё задуманное исполнится! 🎯🙌"
    ]
    return random.choice(wishes)

async def get_timezone_by_city(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_API_KEY}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if not data:
            return None
        lat = data[0]['lat']
        lon = data[0]['lon']
    except Exception:
        return None
    try:
        tz_url = f"http://api.timezonedb.com/v2.1/get-time-zone?key={TIMEZONEDB_API_KEY}&format=json&by=position&lat={lat}&lng={lon}"
        tz_resp = requests.get(tz_url, timeout=5)
        tz_data = tz_resp.json()
        if tz_data.get('status') == 'OK':
            return tz_data.get('zoneName')
        else:
            return None
    except Exception:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    user_states[user_id]["remove_mode"] = False
    user_states[user_id]["add_mode"] = False
    user_states[user_id]["time_mode"] = False
    text = "Привет! Я бот прогноза погоды и хорошего настроения. Выберите действие:"
    # Если время не установлено, сразу предложить установить
    if user_states[user_id].get("send_time") is None:
        text += "\n\n❗ Для автоматических напоминаний о погоде установите время (кнопка \"Установить время ⏰\")."
    await update.message.reply_text(text, reply_markup=main_keyboard)

async def add_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    # Сохраняем режим добавления города только для текущего пользователя
    for uid in user_states:
        user_states[uid]["add_mode"] = False
    user_states[user_id]["add_mode"] = True
    user_states[user_id]["remove_mode"] = False
    user_states[user_id]["time_mode"] = False
    await update.message.reply_text("Введите название города для добавления:")

async def remove_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    state = user_states[user_id]
    cities = state["cities"]
    if not cities:
        await update.message.reply_text("У вас нет городов для удаления.", reply_markup=main_keyboard)
        return
    state["remove_mode"] = True
    state["add_mode"] = False
    state["time_mode"] = False
    await update.message.reply_text(f"Ваши города: {', '.join(cities)}\nВведите название города для удаления:")

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    user_states[user_id]["time_mode"] = True
    user_states[user_id]["add_mode"] = False
    user_states[user_id]["remove_mode"] = False
    await update.message.reply_text("Введите время для получения прогноза (например, 09:00):")

async def city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    state = user_states[user_id]
    city = update.message.text.strip()
    # Привести к виду: первая буква заглавная, остальные строчные, но для сложных названий использовать title()
    if city:
        city = city.title()
    if state.get("add_mode"):
        state["add_mode"] = False
        # Проверяем наличие города без учёта регистра
        cities_lower = [c.lower() for c in state["cities"]]
        if city.lower() not in cities_lower:
            state["cities"].append(city)
            timezone = await get_timezone_by_city(city)
            state["timezone"] = timezone
            await update.message.reply_text(f"✅ Город {city} добавлен! Часовой пояс: {timezone if timezone else 'не найден'}.", reply_markup=main_keyboard)
            save_user_states()
        else:
            await update.message.reply_text(f"⚠️ Город {city} уже есть в вашем списке.", reply_markup=main_keyboard)
        return
    if state.get("remove_mode"):
        state["remove_mode"] = False
        if city in state["cities"]:
            state["cities"].remove(city)
            await update.message.reply_text(f"Город {city} удалён.", reply_markup=main_keyboard)
            save_user_states()
        else:
            await update.message.reply_text(f"Город {city} не найден в вашем списке.", reply_markup=main_keyboard)
        return
    if state.get("time_mode"):
        if city is None:
            await update.message.reply_text("Пожалуйста, введите время в формате ЧЧ:ММ (например, 09:00)", reply_markup=main_keyboard)
            return
        time_text = city.strip()
        if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", time_text):
            await update.message.reply_text("Пожалуйста, введите время в формате ЧЧ:ММ (например, 09:00)", reply_markup=main_keyboard)
            return
        state["time_mode"] = False
        state["send_time"] = time_text
        await update.message.reply_text(f"Время {time_text} сохранено! Теперь прогноз будет приходить автоматически.", reply_markup=main_keyboard)
        save_user_states()
        job_id = f"weather_{user_id}"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        hour, minute = map(int, time_text.split(":"))
        timezone = state.get("timezone", "Europe/Moscow")
        scheduler.add_job(send_weather_job, "cron", hour=hour, minute=minute, args=[user_id], id=job_id, replace_existing=True, timezone=timezone)
        return

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    state = user_states[user_id]
    cities = state["cities"]
    if not cities:
        await update.message.reply_text("Сначала добавьте хотя бы один город.", reply_markup=main_keyboard)
        return
    result = []
    for city in cities:
        weather_text = await get_weather(city)
        result.append(weather_text)
    wish = get_wish()
    await update.message.reply_text("\n".join(result) + f"\n{wish}", reply_markup=main_keyboard)

async def send_weather_job(user_id):
    state = user_states.get(user_id)
    if not state or not state.get("cities"):
        return
    result = []
    for city in state["cities"]:
        weather_text = await get_weather(city)
        result.append(weather_text)
    wish = get_wish()
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=user_id, text="\n".join(result) + f"\n{wish}")
    except Exception:
        pass

def main():
    load_user_states()
    for user_id, state in user_states.items():
        send_time = state.get("send_time")
        timezone = state.get("timezone", "Europe/Moscow")
        if send_time:
            hour, minute = map(int, send_time.split(":"))
            job_id = f"weather_{user_id}"
            scheduler.add_job(send_weather_job, "cron", hour=hour, minute=minute, args=[user_id], id=job_id, replace_existing=True, timezone=timezone)
    scheduler.start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.Regex("^Добавить город$"), add_city))
    app.add_handler(MessageHandler(filters.Regex("^Удалить город$"), remove_city))
    app.add_handler(MessageHandler(filters.Regex("^Установить время$"), set_time))
    app.add_handler(MessageHandler(filters.Regex("^Показать погоду$"), weather))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^Добавить город$|^Удалить город$|^Показать погоду$|^Установить время$"), city_handler))
    app.run_polling()

if __name__ == '__main__':
    main()