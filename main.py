def update_user_job(user_id):
    state = user_states.get(user_id)
    if not state:
        print(f"[JobUpdate] Нет состояния для user_id={user_id}")
        return
    send_time = state.get("send_time")
    notify_city = state.get("notify_city")
    timezones = state.get("timezones", {})
    timezone = timezones.get(notify_city, "Europe/Moscow")
    job_id = f"weather_{user_id}"
    print(f"[JobUpdate] user_id={user_id}, send_time={send_time}, notify_city={notify_city}, timezone={timezone}")
    if send_time and notify_city:
        hour, minute = map(int, send_time.split(":"))
        print(f"[JobUpdate] Обновление задачи: user_id={user_id}, job_id={job_id}, time={send_time}, city={notify_city}, tz={timezone}")
        scheduler.add_job(send_weather_job_sync, "cron", hour=hour, minute=minute, args=[user_id], id=job_id, replace_existing=True, timezone=timezone)
        print(f"[JobUpdate] Задача добавлена: {scheduler.get_job(job_id)}")
    else:
        print(f"[JobUpdate] Не хватает данных для задачи: user_id={user_id}")
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        # Предупреждение пользователю
        # Найти update.message для user_id (через context не получится, поэтому только если есть активный update)
        # Лучше отправлять предупреждение прямо в city_handler после выбора города, если нет времени
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
    [KeyboardButton("Добавить город 🏙️"), KeyboardButton("Удалить город 🗑️")],
    [KeyboardButton("Мои города 📋"), KeyboardButton("Расписание уведомлений 🕒")],
    [KeyboardButton("Показать погоду 🌦️"), KeyboardButton("Посмотреть погоду 🌍"), KeyboardButton("Установить время ⏰")],
    [KeyboardButton("Остановить уведомления ❌"), KeyboardButton("Помощь /help")]
], resize_keyboard=True)

scheduler = BackgroundScheduler()

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

async def get_weather_brief(city):
    try:
        translate_url = "https://libretranslate.de/translate"
        payload = {"q": city, "source": "ru", "target": "en", "format": "text"}
        resp = requests.post(translate_url, json=payload, timeout=5)
        city_en = resp.json().get("translatedText", city) if resp.status_code == 200 else city
    except Exception:
        city_en = city
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city_en}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('cod') != "200":
            return f"Не удалось получить прогноз для {city}."
        temps, winds, rain_hours = [], [], []
        for item in data['list']:
            hour = int(item['dt_txt'][11:13])
            if 6 <= hour <= 21:
                temps.append(item['main']['temp'])
                winds.append(item['wind']['speed'])
                if 'rain' in item and item['rain'].get('3h', 0) > 0:
                    rain_hours.append(item['dt_txt'][11:16])
        if not temps:
            return f"Нет данных о прогнозе на световой день для {city}."
        temp_max = max(temps)
        temp_min = min(temps)
        wind_avg = round(sum(winds) / len(winds), 1)
        rain_hours = sorted(set(rain_hours), key=lambda x: x)
        rain_ranges = []
        if rain_hours:
            start = end = rain_hours[0]
            for h in rain_hours[1:]:
                prev_hour = int(end[:2])
                curr_hour = int(h[:2])
                if curr_hour == prev_hour + 3:
                    end = h
                else:
                    rain_ranges.append((start, end))
                    start = end = h
            rain_ranges.append((start, end))
            # Если дождь почти весь день (например, с 6 до 21)
            day_start, day_end = "06:00", "21:00"
            if len(rain_ranges) == 1 and rain_ranges[0][0] == day_start and rain_ranges[0][1] == day_end:
                rain_text = "Дождь весь день"
            elif len(rain_ranges) == 1 and rain_ranges[0][0] == rain_ranges[0][1]:
                rain_text = f"Дождь ожидается в {rain_ranges[0][0]}"
            else:
                rain_text = "Дождь:\n" + '\n'.join([f"• с {r[0]} по {r[1]}" if r[0] != r[1] else f"• в {r[0]}" for r in rain_ranges])
        else:
            rain_text = "Без дождя"
        return f"{city}:\n{rain_text}\nВетер: {wind_avg} м/с\nТемпература: от {temp_min}°C до {temp_max}°C"
    except Exception as e:
        return f"Ошибка: {e}"

async def get_weather_5days(city):
    try:
        translate_url = "https://libretranslate.de/translate"
        payload = {"q": city, "source": "ru", "target": "en", "format": "text"}
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
            return f"Не удалось получить прогноз на 5 дней для {city}."
        forecasts = []
        for item in data['list']:
            dt = item['dt']
            date = datetime.utcfromtimestamp(dt).strftime('%Y-%m-%d')
            hour = int(item['dt_txt'][11:13])
            if 6 <= hour <= 21:
                day_forecast = {
                    "date": date,
                    "temp_max": item['main']['temp_max'],
                    "temp_min": item['main']['temp_min'],
                    "wind_speed": item['wind']['speed'],
                    "rain": item.get('rain', {}).get('3h', 0)
                }
                forecasts.append(day_forecast)
        if not forecasts:
            return f"Нет данных о прогнозе на световой день для {city}."
        result = [f"Прогноз погоды на 5 дней для {city}:"]
        for f in forecasts:
            date = f["date"]
            temp_max = f["temp_max"]
            temp_min = f["temp_min"]
            wind_speed = f["wind_speed"]
            rain = f["rain"]
            rain_text = f"Дождь: {rain} мм" if rain > 0 else "Без дождя"
            result.append(f"Дата: {date}, Макс. температура: {temp_max}°C, Мин. температура: {temp_min}°C, Ветер: {wind_speed} м/с, {rain_text}")
        return "\n".join(result)
    except Exception as e:
        return f"Ошибка: {e}"

async def send_weather_job_sync(user_id):
    state = user_states.get(user_id)
    if not state:
        return
    notify_city = state.get("notify_city")
    if not notify_city:
        return
    chat_id = state.get("chat_id")
    if not chat_id:
        return
    text = await get_weather_brief(notify_city)
    if text.startswith("Ошибка:"):
        await send_message(chat_id, text)
    else:
        wish = get_wish()
        await send_message(chat_id, f"{text}\n\n{wish}")

async def send_message(chat_id, text):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_states[user_id] = {"chat_id": chat_id}
    save_user_states()
    await update.message.reply_text("Добро пожаловать! Выберите действие:", reply_markup=main_keyboard)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Помощь по боту:\n\n"
                                      "1. Добавить город 🏙️ - добавляет город для получения прогноза погоды.\n"
                                      "2. Удалить город 🗑️ - удаляет город из списка отслеживаемых.\n"
                                      "3. Мои города 📋 - показывает список добавленных городов.\n"
                                      "4. Расписание уведомлений 🕒 - показывает расписание уведомлений о погоде.\n"
                                      "5. Показать погоду 🌦️ - показывает погоду на текущий момент.\n"
                                      "6. Посмотреть погоду 🌍 - показывает погоду на 5 дней вперёд.\n"
                                      "7. Установить время ⏰ - устанавливает время для ежедневных уведомлений о погоде.\n"
                                      "8. Остановить уведомления ❌ - останавливает уведомления о погоде.\n"
                                      "9. Помощь /help - показывает это сообщение.")

async def add_city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    state = user_states.get(user_id, {})
    timezones = state.get("timezones", {})
    if not timezones:
        await update.message.reply_text("Сначала установите часовой пояс командой /set_timezone")
        return
    keyboard = ReplyKeyboardMarkup([[KeyboardButton(city) for city in timezones.keys()]], resize_keyboard=True)
    await update.message.reply_text("Выберите город:", reply_markup=keyboard)

async def city_chosen_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    city = update.message.text
    state = user_states.get(user_id, {})
    timezones = state.get("timezones", {})
    if city not in timezones:
        await update.message.reply_text("Город не найден. Пожалуйста, выберите из предложенных вариантов.")
        return
    timezone = timezones[city]
    user_states[user_id] = {"chat_id": chat_id, "notify_city": city, "timezone": timezone}
    save_user_states()
    await update.message.reply_text(f"Город установлен: {city}. Теперь укажите время для уведомлений в формате ЧЧ:ММ.")

async def set_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    state = user_states.get(user_id, {})
    if "notify_city" not in state:
        await update.message.reply_text("Сначала добавьте город командой /add_city")
        return
    text = update.message.text
    if not re.match(r"^\d{1,2}:\d{2}$", text):
        await update.message.reply_text("Неверный формат времени. Пожалуйста, укажите время в формате ЧЧ:ММ.")
        return
    hour, minute = map(int, text.split(":"))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        await update.message.reply_text("Некорректное время. Часы должны быть от 0 до 23, минуты от 0 до 59.")
        return
    user_states[user_id]["send_time"] = text
    save_user_states()
    update_user_job(user_id)
    await update.message.reply_text(f"Время уведомлений установлено на {text}.")

async def stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_states.pop(user_id, None)
    try:
        scheduler.remove_job(f"weather_{user_id}")
    except Exception:
        pass
    await update.message.reply_text("Уведомления остановлены. Если захотите снова получить прогноз погоды, просто напишите мне.")

async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я вас не понимаю. Пожалуйста, воспользуйтесь командой /help для получения списка доступных команд.")

def main():
    load_user_states()
    print(f"[Main] user_states: {user_states}")
    for user_id, state in user_states.items():
        send_time = state.get("send_time")
        notify_city = state.get("notify_city")
        timezones = state.get("timezones", {})
        timezone = timezones.get(notify_city, "Europe/Moscow")
        print(f"[Main] user_id={user_id}, send_time={send_time}, notify_city={notify_city}")
        if send_time:
            hour, minute = map(int, send_time.split(":"))
            job_id = f"weather_{user_id}"
            print(f"[Main] Добавление задачи: user_id={user_id}, job_id={job_id}, time={send_time}, city={notify_city}")
            scheduler.add_job(send_weather_job_sync, "cron", hour=hour, minute=minute, args=[user_id], id=job_id, replace_existing=True, timezone=timezone)
    scheduler.start()
    print("[Main] Scheduler запущен")
    print(f"[Main] Список задач: {scheduler.get_jobs()}")

    if TELEGRAM_TOKEN is None:
        raise ValueError("TELEGRAM_TOKEN не задан в .env")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CommandHandler('test_notify', test_notify_handler))
    app.add_handler(MessageHandler(filters.Regex("^Добавить город 🏙️$"), add_city))
    app.add_handler(MessageHandler(filters.Regex("^Удалить город 🗑️$"), remove_city))
    app.add_handler(MessageHandler(filters.Regex("^Мои города 📋$"), show_cities))
    app.add_handler(MessageHandler(filters.Regex("^Расписание уведомлений 🕒$"), show_schedule))
    app.add_handler(MessageHandler(filters.Regex("^Остановить уведомления ❌$"), stop_notifications))
    app.add_handler(MessageHandler(filters.Regex("^Показать погоду 🌦️$"), weather))
    app.add_handler(MessageHandler(filters.Regex("^Посмотреть погоду 🌍$"), view_weather_cmd))
    app.add_handler(MessageHandler(filters.Regex("^Установить время ⏰$"), set_time))
    app.add_handler(MessageHandler(filters.Regex("^Помощь /help$|^/help$"), help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, city_handler))
    app.run_polling()

if __name__ == "__main__":
    main()