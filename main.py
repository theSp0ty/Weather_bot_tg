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
    [KeyboardButton("Остановить уведомления ❌"), KeyboardButton("Помощь /help")],
    [KeyboardButton("Домой 🏠")]
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
        city_en = resp.json().get("translatedText", city) if resp.status_code == 200 else city
    except Exception:
        city_en = city
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city_en}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('cod') != "200":
            return f"Не удалось получить прогноз для {city}."
        days = {}
        for item in data['list']:
            date = item['dt_txt'][:10]
            temp = item['main']['temp']
            desc = item['weather'][0]['description']
            wind = item['wind']['speed']
            if date not in days:
                days[date] = {"temps": [], "descs": [], "winds": []}
            days[date]["temps"].append(temp)
            days[date]["descs"].append(desc)
            days[date]["winds"].append(wind)
        msg = f"Прогноз на 5 дней для {city}:\n"
        for i, (date, info) in enumerate(days.items()):
            if i >= 5:
                break
            t_min = int(min(info["temps"]))
            t_max = int(max(info["temps"]))
            wind_avg = round(sum(info["winds"]) / len(info["winds"]), 1)
            desc_main = max(set(info["descs"]), key=info["descs"].count)
            msg += f"\n{date}: {desc_main.capitalize()}\nТемпература: от {t_min}°C до {t_max}°C\nВетер: {wind_avg} м/с\n"
        return msg
    except Exception as e:
        return f"Ошибка: {e}"

async def send_weather_job(user_id):
        state = user_states.get(user_id)
        print(f"[Job] user_id={user_id}, state={state}")
        if not state or not state.get("cities"):
            print(f"[Job] Нет городов для user_id={user_id}")
            return
        notify_city = state.get("notify_city")
        if not notify_city:
            print(f"[Job] Нет выбранного города для уведомлений у user_id={user_id}")
            return
        print(f"[Job] Получение прогноза для города: {notify_city}")
        weather_text = await get_weather_brief(notify_city)
        wish = get_wish()
        if TELEGRAM_TOKEN is None:
            print("[Job] TELEGRAM_TOKEN не задан в .env")
            raise ValueError("TELEGRAM_TOKEN не задан в .env")
        bot = Bot(token=TELEGRAM_TOKEN)
        try:
            await bot.send_message(chat_id=user_id, text=f"{weather_text}\n{wish}")
            print(f"[Job] Уведомление отправлено user_id={user_id}")
        except Exception as e:
            print(f"[Job] Ошибка при отправке сообщения: {e}")

def send_weather_job_sync(user_id):
    import asyncio
    print(f"[Scheduler] Запуск уведомления для user_id={user_id}")
    try:
        print(f"[Scheduler] Перед запуском: user_states={user_states.get(user_id)}")
        asyncio.run(send_weather_job(user_id))
        print(f"[Scheduler] После запуска: user_states={user_states.get(user_id)}")
    except Exception as e:
        print(f"[Scheduler] Ошибка при отправке уведомления: {e}")

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
    user_states[user_id]["add_mode"] = True
    await update.message.reply_text("Введите название города для добавления:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Домой 🏠")]], resize_keyboard=True))

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
    await update.message.reply_text(f"Ваши города: {', '.join(cities)}\nВведите название города для удаления:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Домой 🏠")]], resize_keyboard=True))

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    state = user_states[user_id]
    state["time_mode"] = True
    state["add_mode"] = False
    state["remove_mode"] = False
    cities = state["cities"]
    if cities:
        state["choose_time_city_mode"] = True
        await update.message.reply_text(
            "Выберите город для которого хотите установить время:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c)] for c in cities] + [[KeyboardButton("Домой 🏠")]], resize_keyboard=True)
        )
        # После выбора города сразу предложить время (дизайн как выше)
        # Это реализовано в city_handler, но если город уже выбран, можно сразу показать клавиатуру времени
    else:
        await update.message.reply_text("Сначала добавьте хотя бы один город.", reply_markup=main_keyboard)

async def city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    state = user_states[user_id]
    # Handle city selection for time setting
    if state.get("choose_time_city_mode"):
        if update.message and update.message.text:
            chosen_city = update.message.text.strip().title()
        else:
            chosen_city = ""
        if chosen_city in state["cities"]:
            state["notify_city"] = chosen_city
            state["choose_time_city_mode"] = False
            # Предложить выбрать время сразу после выбора города
            # Новый дизайн клавиатуры времени
            await update.message.reply_text(
                f"Вы выбрали город {chosen_city} для уведомлений.\nВыберите время для получения ежедневных уведомлений или нажмите 'Ввести своё время':",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton('Ввести своё время')]] +
                    [
                        [KeyboardButton('07:00'), KeyboardButton('07:30'), KeyboardButton('08:00')],
                        [KeyboardButton('08:30'), KeyboardButton('09:00'), KeyboardButton('09:30')],
                        [KeyboardButton('10:00'), KeyboardButton('10:30'), KeyboardButton('18:00')],
                        [KeyboardButton('18:30'), KeyboardButton('19:00'), KeyboardButton('19:30')],
                        [KeyboardButton('20:00'), KeyboardButton('20:30')]
                    ], resize_keyboard=True)
                )
            state["choose_time_mode"] = True
            save_user_states()
            return
        else:
            await update.message.reply_text(
                f"Город {chosen_city} не найден в вашем списке. Выберите город из списка:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c)] for c in state["cities"]] + [[KeyboardButton("Домой 🏠")]], resize_keyboard=True)
            )
            return
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
            if "timezones" not in state:
                state["timezones"] = {}
            state["timezones"][city] = timezone
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
            save_user_states()
            update_user_job(user_id)
            send_time = state.get("send_time")
            if send_time:
                await update.message.reply_text(
                    f"✅ Город {chosen_city} выбран для уведомлений!\nУведомления будут приходить каждый день в {send_time}.",
                    reply_markup=main_keyboard
                )
            else:
                await update.message.reply_text(
                    f"✅ Город {chosen_city} выбран для уведомлений!\n❗ Уведомления будут приходить только после выбора времени!\nВыберите время для получения ежедневных уведомлений или нажмите 'Ввести своё время':",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton('Ввести своё время')]] +
                        [
                            [KeyboardButton('07:00'), KeyboardButton('07:30'), KeyboardButton('08:00')],
                            [KeyboardButton('08:30'), KeyboardButton('09:00'), KeyboardButton('09:30')],
                            [KeyboardButton('10:00'), KeyboardButton('10:30'), KeyboardButton('18:00')],
                            [KeyboardButton('18:30'), KeyboardButton('19:00'), KeyboardButton('19:30')],
                            [KeyboardButton('20:00'), KeyboardButton('20:30')]
                        ], resize_keyboard=True)
                )
                state["choose_time_mode"] = True
            return
        else:
            await update.message.reply_text(
                f"⚠️ Город {chosen_city} не найден в вашем списке.\nВыберите город или добавьте новый:",
                reply_markup=ReplyKeyboardMarkup(city_buttons, resize_keyboard=True)
            )
        return
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
            save_user_states()
            update_user_job(user_id)
            await update.message.reply_text(
                f"⏰ Уведомления по городу {state['notify_city']} будут приходить каждый день в {time_text}!",
                reply_markup=main_keyboard
            )
            return
    if state.get("custom_time_mode"):
        time_text = update.message.text
        if time_text is not None:
            time_text = time_text.strip()
        else:
            time_text = ""
        if re.match(r'^([01]\d|2[0-3]):[0-5]\d$', time_text):
            state["send_time"] = time_text
            state["custom_time_mode"] = False
            save_user_states()
            update_user_job(user_id)
            await update.message.reply_text(
                f"⏰ Уведомления по городу {state['notify_city']} будут приходить каждый день в {time_text}!",
                reply_markup=main_keyboard
            )
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

async def view_weather_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    if user_id not in user_states:
        user_states[user_id] = {"cities": [], "remove_mode": False, "add_mode": False, "time_mode": False, "send_time": None}
    state = user_states[user_id]
    state["view_weather_mode"] = True
    cities = state.get("cities", [])
    if not cities:
        await update.message.reply_text("Сначала добавьте хотя бы один город.", reply_markup=main_keyboard)
        save_user_states()
        return
    if len(cities) == 1:
        city = cities[0]
        weather_text = await get_weather_5days(city)
        wish = get_wish()
        await update.message.reply_text(f"{weather_text}\n{wish}", reply_markup=main_keyboard)
        save_user_states()
        return
    await update.message.reply_text("🌍 Выберите город из списка или введите название:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(c)] for c in cities] + [[KeyboardButton("Домой 🏠")]], resize_keyboard=True))
    save_user_states()

async def show_cities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    state = user_states.get(user_id, {})
    cities = state.get("cities", [])
    timezones = state.get("timezones", {})
    if not cities:
        await update.message.reply_text("У вас пока нет добавленных городов.", reply_markup=main_keyboard)
        return
    msg = "Ваши города:\n"
    for c in cities:
        tz = timezones.get(c, "?")
        msg += f"• {c} (часовой пояс: {tz})\n"
    await update.message.reply_text(msg, reply_markup=main_keyboard)
    save_user_states()

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    state = user_states.get(user_id, {})
    notify_city = state.get("notify_city")
    send_time = state.get("send_time")
    timezones = state.get("timezones", {})
    if notify_city and send_time:
        tz = timezones.get(notify_city, "?")
        await update.message.reply_text(
            f"Уведомления настроены:\nГород: {notify_city}\nВремя: {send_time}\nЧасовой пояс: {tz}",
            reply_markup=main_keyboard
        )
    else:
        await update.message.reply_text("Уведомления не настроены.", reply_markup=main_keyboard)
    save_user_states()

async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    state = user_states.get(user_id, {})
    state["send_time"] = None
    update_user_job(user_id)
    await update.message.reply_text("Уведомления остановлены. Вы можете включить их снова, выбрав город и время.", reply_markup=main_keyboard)
    save_user_states()

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🌦️ Я бот прогноза погоды и напоминаний!\n\n"
        "Доступные команды и кнопки:\n"
        "• Добавить город — добавить новый город в список\n"
        "• Удалить город — удалить город из списка\n"
        "• Мои города — посмотреть список городов и их часовые пояса\n"
        "• Расписание уведомлений — узнать, по какому городу и в какое время приходят уведомления\n"
        "• Остановить уведомления — временно отключить напоминания\n"
        "• Показать погоду — получить прогноз по выбранному городу\n"
        "• Посмотреть погоду — выбрать город для прогноза\n"
        "• Установить время — выбрать время для уведомлений\n"
        "• Помощь — показать это сообщение\n"
    )
    await update.message.reply_text(msg, reply_markup=main_keyboard)

async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or update.message is None:
        return
    # Сброс всех временных режимов
    state = user_states.get(user_id, {})
    for key in ["add_mode", "remove_mode", "time_mode", "choose_city_mode", "choose_time_mode", "custom_time_mode", "choose_time_city_mode", "view_weather_mode"]:
        state[key] = False
    await update.message.reply_text("Главное меню:", reply_markup=main_keyboard)
    save_user_states()

def main():
    load_user_states()
    print(f"[Main] user_states: {user_states}")
    scheduler.start()
    print("[Main] Scheduler запущен")
    print(f"[Main] Список задач: {scheduler.get_jobs()}")

    if TELEGRAM_TOKEN is None:
        raise ValueError("TELEGRAM_TOKEN не задан в .env")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(MessageHandler(filters.Regex("^Добавить город 🏙️$"), add_city))
    app.add_handler(MessageHandler(filters.Regex("^Удалить город 🗑️$"), remove_city))
    app.add_handler(MessageHandler(filters.Regex("^Мои города 📋$"), show_cities))
    app.add_handler(MessageHandler(filters.Regex("^Расписание уведомлений 🕒$"), show_schedule))
    app.add_handler(MessageHandler(filters.Regex("^Остановить уведомления ❌$"), stop_notifications))
    app.add_handler(MessageHandler(filters.Regex("^Показать погоду 🌦️$"), weather))
    app.add_handler(MessageHandler(filters.Regex("^Посмотреть погоду 🌍$"), view_weather_cmd))
    app.add_handler(MessageHandler(filters.Regex("^Установить время ⏰$"), set_time))
    app.add_handler(MessageHandler(filters.Regex("^Помощь /help$|^/help$"), help_cmd))
    app.add_handler(MessageHandler(filters.Regex("^Домой 🏠$"), go_home))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, city_handler))
    app.run_polling()

if __name__ == '__main__':
    main()