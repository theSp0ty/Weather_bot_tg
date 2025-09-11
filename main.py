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

USER_DATA_FILE = 'users.json'
user_states = {}
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
TIMEZONEDB_API_KEY = os.getenv('TIMEZONEDB_API_KEY')

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
        "Пусть всё задуманное исполнится! 🎯🙌",
        "Пусть этот день будет наполнен радостью и светом! 🌟",
        "Пусть удача сопутствует во всех делах! 🍀",
        "Пусть настроение будет на высоте! 😃",
        "Пусть каждый час приносит приятные сюрпризы! 🎉",
        "Пусть в душе будет тепло и гармония! 🧘‍♂️",
        "Пусть все мечты сбудутся! ✨",
        "Пусть день будет ярким и незабываемым! 🌈",
        "Пусть вокруг будут только добрые люди! 🤗",
        "Пусть будет много поводов для улыбки! 😄",
        "Пусть всё задуманное реализуется легко и просто! 🚀"
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
    if user_states[user_id].get("send_time") is None:
        text += "\n\n❗ Для автоматических напоминаний о погоде установите время (кнопка \"Установить время ⏰\")."
    await update.message.reply_text(text, reply_markup=main_keyboard)

async def add_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
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
    city = update.message.text
    if city is not None:
        city = city.strip()
        city = city.title()
    else:
        city = ""
    if state.get("add_mode"):
        state["add_mode"] = False
        cities_lower = [c.lower() for c in state["cities"]]
        if city.lower() not in cities_lower:
            state["cities"].append(city)
            timezone = await get_timezone_by_city(city)
            state["timezone"] = timezone
            await update.message.reply_text(
                f"✅ Город {city} добавлен! Часовой пояс: {timezone if timezone else 'не найден'}.\n\nХотите получать ежедневные уведомления по этому городу? Выберите его ниже или используйте команду 'Показать погоду 🌦️' для выбора.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c)] for c in state["cities"]] + [[KeyboardButton('➕ Добавить город')]], resize_keyboard=True)
            )
            state["choose_city_mode"] = True
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
    # --- ВЫБОР ГОРОДА ДЛЯ УВЕДОМЛЕНИЙ ---
    if state.get("choose_city_mode"):
        chosen_city = update.message.text
        if chosen_city is not None:
            chosen_city = chosen_city.strip().title()
        else:
            chosen_city = ""
        city_buttons = [[KeyboardButton(c)] for c in state["cities"]]
        city_buttons.append([KeyboardButton('➕ Добавить город')])
        if chosen_city.strip().lower() == '➕ добавить город'.lower():
            state["add_mode"] = True
            state["choose_city_mode"] = False
            await update.message.reply_text("Введите название города для добавления:")
            save_user_states()
            return
        if chosen_city in state["cities"]:
            state["notify_city"] = chosen_city
            state["choose_city_mode"] = False
            time_options = ['07:00', '07:30', '08:00', '08:30', '09:00', '09:30', '10:00', '10:30',
                            '18:00', '18:30', '19:00', '19:30', '20:00', '20:30']
            keyboard = [[KeyboardButton(t)] for t in time_options]
            keyboard.append([KeyboardButton('Ввести своё время')])
            await update.message.reply_text(
                f"Вы выбрали город {chosen_city} для уведомлений.\nВыберите время для получения ежедневных уведомлений или нажмите 'Ввести своё время':",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            state["choose_time_mode"] = True
            save_user_states()
            return
        else:
            await update.message.reply_text(
                f"⚠️ Город {chosen_city} не найден в вашем списке.\nВыберите город или добавьте новый:",
                reply_markup=ReplyKeyboardMarkup(city_buttons, resize_keyboard=True)
            )
        return
    # --- ОБРАБОТКА ВЫБОРА ВРЕМЕНИ ---
    if state.get("choose_time_mode"):
        time_text = update.message.text
        if time_text is not None:
            time_text = time_text.strip()
        else:
            time_text = ""
        time_options = ['07:00', '07:30', '08:00', '08:30', '09:00', '09:30', '10:00', '10:30',
                        '18:00', '18:30', '19:00', '19:30', '20:00', '20:30']
        if time_text == 'Ввести своё время':
            state["custom_time_mode"] = True
            state["choose_time_mode"] = False
            await update.message.reply_text("Введите время в формате ЧЧ:ММ (например, 06:45):")
            save_user_states()
            return
        if time_text in time_options:
            state["send_time"] = time_text
            state["choose_time_mode"] = False
            await update.message.reply_text(
                f"⏰ Уведомления по городу {state['notify_city']} будут приходить каждый день в {time_text}!",
                reply_markup=main_keyboard
            )
            save_user_states()
            return
    if state.get("custom_time_mode"):
        time_text = update.message.text
        if time_text is not None:
            time_text = time_text.strip()
        else:
            time_text = ""
        if re.match(r'^([01]\\d|2[0-3]):[0-5]\\d$', time_text):
            state["send_time"] = time_text
            state["custom_time_mode"] = False
            await update.message.reply_text(
                f"⏰ Уведомления по городу {state['notify_city']} будут приходить каждый день в {time_text}!",
                reply_markup=main_keyboard
            )
            save_user_states()
        else:
            await update.message.reply_text("Некорректный формат времени. Введите в формате ЧЧ:ММ, например 06:45.")
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
    notify_city = state.get("notify_city")
    if not notify_city or notify_city not in cities:
        await update.message.reply_text(
            "Выберите город для прогноза:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c)] for c in cities] + [[KeyboardButton('➕ Добавить город')]], resize_keyboard=True)
        )
        state["choose_city_mode"] = True
        return
    weather_text = await get_weather_brief(notify_city)
    wish = get_wish()
    await update.message.reply_text(f"{weather_text}\n{wish}", reply_markup=main_keyboard)

async def get_weather_brief(city):
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
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city_en}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('cod') != "200":
            return f"Не удалось получить прогноз для {city}."
        temps = []
        winds = []
        rain_hours = []
        for item in data['list']:
            hour = int(item['dt_txt'][11:13])
            if 6 <= hour <= 21:
                temps.append(item['main']['temp'])
                winds.append(item['wind']['speed'])
                if 'rain' in item and item['rain'].get('3h', 0) > 0:
                    rain_hours.append(item['dt_txt'][11:16])  # формат HH:MM
        if not temps:
            return f"Нет данных о прогнозе на световой день для {city}."
        temp_max = max(temps)
        temp_min = min(temps)
        wind_avg = round(sum(winds) / len(winds), 1)
        if rain_hours:
            # Группируем подряд идущие часы дождя в диапазон
            rain_ranges = []
            start = end = None
            for h in rain_hours:
                try:
                    if start is None:
                        start = end = h
                    elif end is not None and h is not None and int(h[:2]) == int(end[:2]) + 3:
                        end = h
                    else:
                        rain_ranges.append((start, end))
                        start = end = h
                except Exception:
                    # Если вдруг формат времени некорректен, просто начинаем новый диапазон
                    rain_ranges.append((start, end))
                    start = end = h
            if start is not None and end is not None:
                rain_ranges.append((start, end))
            # Формируем текст
            if len(rain_ranges) == 1 and rain_ranges[0][0] == rain_ranges[0][1]:
                rain_text = f"Дождь ожидается в {rain_ranges[0][0]}"
            else:
                ranges_str = ', '.join([f"с {r[0]} по {r[1]}" if r[0] != r[1] else f"в {r[0]}" for r in rain_ranges])
                rain_text = f"Дождь: {ranges_str}"
        else:
            rain_text = "Без дождя"
        return f"{city}: {rain_text}, ветер {wind_avg} м/с, температура от {temp_min}°C до {temp_max}°C"
    except Exception as e:
        return f"Ошибка: {e}"

async def send_weather_job(user_id):
    state = user_states.get(user_id)
    if not state or not state.get("cities"):
        return
    notify_city = state.get("notify_city")
    if not notify_city:
        return
    weather_text = await get_weather_brief(notify_city)
    wish = get_wish()
    if TELEGRAM_TOKEN is None:
        raise ValueError("TELEGRAM_TOKEN не задан в .env")
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=user_id, text=f"{weather_text}\n{wish}")
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
    if TELEGRAM_TOKEN is None:
        raise ValueError("TELEGRAM_TOKEN не задан в .env")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.Regex("^Добавить город"), add_city))
    app.add_handler(MessageHandler(filters.Regex("^Удалить город"), remove_city))
    app.add_handler(MessageHandler(filters.Regex("^Установить время"), set_time))
    app.add_handler(MessageHandler(filters.Regex("^Показать погоду"), weather))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, city_handler))
    app.run_polling()

if __name__ == '__main__':
    main()