import os
import logging
from datetime import datetime, timedelta
import httpx  # Для async requests
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# --- НАСТРОЙКА ЛОГГИРОВАНИЯ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ЗАГРУЗКА КОНФИГУРАЦИИ ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AVIASALES_API_TOKEN = os.getenv("AVIASALES_API_TOKEN")
AVIASALES_API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

# Словарь для IATA-кодов городов
IATA_CODES = {
    "москва": "MOW",
    "минеральные воды": "MRV"
}

# Словарь для названий авиакомпаний (фокус на RU + популярные)
AIRLINE_NAMES = {
    'SU': 'Aeroflot',
    'S7': 'S7 Airlines',
    'DP': 'Pobeda',
    'Y7': 'NordStar',
    'U6': 'Ural Airlines',
    'UT': 'UTair',
    'A4': 'Azimuth',
    '5N': 'Smartavia',
    'N4': 'Nordwind Airlines',
    'ZF': 'Azur Air',
    'EO': 'Ikar',
    'FV': 'Rossiya Airlines',
    'D2': 'Severstal Aircompany',
    'YC': 'Yamal Airlines',
    'R3': 'Yakutia Airlines',
    # Добавь больше, если нужно
}

# Словарь для названий аэропортов (фокус на Москве и MRV)
AIRPORT_NAMES = {
    'SVO': 'Шереметьево (Москва)',
    'VKO': 'Внуково (Москва)',
    'DME': 'Домодедово (Москва)',
    'ZIA': 'Жуковский (Москва)',
    'MRV': 'Минеральные Воды',
    # Добавь другие, если появятся
}

# Функция для форматирования даты на русском
def format_date(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 
                  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    except ValueError:
        return date_str

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
DATABASE_FILE = "subscriptions.db"
engine = create_engine(f"sqlite:///{DATABASE_FILE}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, index=True)
    direction = Column(String)  # 'outbound' для MOW->MRV, 'return' для MRV->MOW
    target_date = Column(String)  # Целевая дата (departure для outbound, return для return)
    price_threshold = Column(Float)

Base.metadata.create_all(bind=engine)

# --- АСИНХРОННЫЙ ПОИСК БИЛЕТОВ ---
async def fetch_flight_for_date(client: httpx.AsyncClient, origin, destination, date_str, token):
    params = {
        'origin': origin,
        'destination': destination,
        'departure_at': date_str,
        'one_way': 'true',  # One-way
        'token': token,
        'currency': 'rub',
        'market': 'ru',
        'limit': 5,  # До 5 вариантов на дату
        'sorting': 'price',
        'direct': 'false'
    }
    try:
        response = await client.get(AVIASALES_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('success') and data.get('data'):
            return [
                {
                    "price": flight['price'],
                    "link": f"https://www.aviasales.ru{flight['link']}",
                    "airline": flight['airline'],
                    "origin_airport": flight['origin_airport'],
                    "destination_airport": flight['destination_airport'],
                    "departure_date": flight['departure_at'].split('T')[0],
                    "departure_time": flight['departure_at'].split('T')[1][:5] if 'T' in flight['departure_at'] else ''
                }
                for flight in data['data']
            ]
    except Exception as e:
        logger.error(f"Ошибка для даты {date_str}: {e}")
    return []

async def find_flights_for_dates(origin, destination, target_date_str, token, threshold, exact_only=False):
    """Ищет билеты на target_date ±3 дня параллельно, или только на exact."""
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
    except ValueError:
        return []

    if exact_only:
        dates = [target_date_str]
    else:
        dates = [(target_date + timedelta(days=d)).strftime('%Y-%m-%d') for d in range(-3, 4) if d != 0]  # Исключаем target

    async with httpx.AsyncClient() as client:
        tasks = [fetch_flight_for_date(client, origin, destination, date, token) for date in dates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_flights = []
    for res in results:
        if isinstance(res, list):
            all_flights.extend(res)

    # Фильтруем по threshold, сортируем по цене, топ 5
    filtered = sorted([f for f in all_flights if f['price'] <= threshold], key=lambda x: x['price'])
    return filtered[:5]

# --- ОБРАБОТЧИКИ КОМАНД БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для отслеживания дешевых билетов между Москвой и Минеральными Водами на **конкретные даты** (±3 дня).\n\n"
        "Используйте команду /track для подписки на уведомления.\n\n"
        "**Формат:**\n`/track [Дата вылета] [Дата возврата] [Макс. цена]`\n\n"
        "**Пример:**\n`/track 2025-10-15 2025-10-22 15000`\n\n"
        "Даты указывайте в формате `ГГГГ-ММ-ДД`."
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    args = context.args

    if len(args) != 3:
        await update.message.reply_text(
            "Неверный формат. Пример:\n`/track 2025-10-15 2025-10-22 15000`"
        )
        return

    depart_date_str, return_date_str, price_str = args

    # Валидация данных
    try:
        datetime.strptime(depart_date_str, '%Y-%m-%d')
        datetime.strptime(return_date_str, '%Y-%m-%d')
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Используйте `ГГГГ-ММ-ДД`.")
        return
    
    try:
        price_threshold = float(price_str)
    except ValueError:
        await update.message.reply_text("Цена должна быть числом.")
        return
        
    db = SessionLocal()
    try:
        # Проверяем на дубликаты
        existing_out = db.query(Subscription).filter_by(
            chat_id=chat_id, direction='outbound', target_date=depart_date_str
        ).first()
        existing_ret = db.query(Subscription).filter_by(
            chat_id=chat_id, direction='return', target_date=return_date_str
        ).first()
        if existing_out or existing_ret:
            await update.message.reply_text("Такая подписка уже существует!")
            return

        # Добавляем две подписки: outbound и return (one-way каждая)
        sub_out = Subscription(
            chat_id=chat_id, direction='outbound', target_date=depart_date_str, price_threshold=price_threshold
        )
        sub_ret = Subscription(
            chat_id=chat_id, direction='return', target_date=return_date_str, price_threshold=price_threshold
        )
        db.add(sub_out)
        db.add(sub_ret)
        db.commit()

        await update.message.reply_text(
            f"Принято! Буду искать билеты (±3 дня):\n"
            f"🛫 Из Москвы: {format_date(depart_date_str)}\n"
            f"🛬 Из Мин. Вод: {format_date(return_date_str)}\n"
            f"💰 Дешевле чем: {price_threshold} RUB"
        )

        # Немедленная проверка
        await check_prices(context.application)
    finally:
        db.close()

# --- ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ ЦЕН ---
async def check_prices(application: Application):
    logger.info("Начинаю проверку цен по датам...")
    db = SessionLocal()
    try:
        subscriptions = db.query(Subscription).all()
        logger.info(f"Найдено подписок: {len(subscriptions)}")
        for sub in subscriptions:
            if sub.direction == 'outbound':
                origin, destination = IATA_CODES["москва"], IATA_CODES["минеральные воды"]
                route_name = "Из Москвы в Мин. Воды"
            else:
                origin, destination = IATA_CODES["минеральные воды"], IATA_CODES["москва"]
                route_name = "Из Мин. Вод в Москву"

            # Сначала проверка на точную дату
            exact_flights = await find_flights_for_dates(
                origin, destination, sub.target_date, AVIASALES_API_TOKEN, sub.price_threshold, exact_only=True
            )
            
            if exact_flights:
                message_parts = [
                    f"🔥 Найдены выгодные предложения для {route_name}! 🔥\n\n"
                    f"Дата: {format_date(sub.target_date)}\n\n"
                    f"Варианты (до {len(exact_flights)} шт.):"
                ]
                for flight in exact_flights:
                    airline_name = AIRLINE_NAMES.get(flight['airline'], flight['airline'])
                    orig_airport = AIRPORT_NAMES.get(flight['origin_airport'], flight['origin_airport'])
                    dest_airport = AIRPORT_NAMES.get(flight['destination_airport'], flight['destination_airport'])
                    message_parts.append(
                        f"\n- {airline_name}: {flight['price']} RUB\n"
                        f"  Вылет: {orig_airport} в {flight['departure_time']}\n"
                        f"  Прилёт: {dest_airport}\n"
                        f"  [Купить]({flight['link']})"
                    )
                message = "\n".join(message_parts)
                await application.bot.send_message(
                    chat_id=sub.chat_id, text=message, parse_mode='Markdown'
                )

            # Затем альтернативы (±3 дня, исключая target)
            alt_flights = await find_flights_for_dates(
                origin, destination, sub.target_date, AVIASALES_API_TOKEN, sub.price_threshold, exact_only=False
            )
            
            if alt_flights:
                message_parts = [
                    f"🛫 Альтернативы в ближайшие дни для {route_name}:"
                ]
                for flight in alt_flights:
                    airline_name = AIRLINE_NAMES.get(flight['airline'], flight['airline'])
                    orig_airport = AIRPORT_NAMES.get(flight['origin_airport'], flight['origin_airport'])
                    dest_airport = AIRPORT_NAMES.get(flight['destination_airport'], flight['destination_airport'])
                    alt_note = f"{format_date(flight['departure_date'])}"
                    message_parts.append(
                        f"\n- {airline_name}: {flight['price']} RUB ({alt_note})\n"
                        f"  Вылет: {orig_airport} в {flight['departure_time']}\n"
                        f"  Прилёт: {dest_airport}\n"
                        f"  [Купить]({flight['link']})"
                    )
                message = "\n".join(message_parts)
                await application.bot.send_message(
                    chat_id=sub.chat_id, text=message, parse_mode='Markdown'
                )

            # Удаляем подписку, если найдены предложения (exact или alt)
            if exact_flights or alt_flights:
                db.delete(sub)
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка в задаче проверки цен: {e}")
    finally:
        db.close()
        logger.info("Проверка цен завершена.")

# --- ЗАПУСК БОТА ---
async def main():
    if not TELEGRAM_BOT_TOKEN or not AVIASALES_API_TOKEN:
        logger.error("Не найдены токены! Убедитесь, что у вас есть файл .env")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track)) 

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(check_prices, 'interval', minutes=5, args=[application])  # Для теста, потом hours=4
    scheduler.start()
    
    logger.info("Бот запущен и готов к работе...")
    
    try:
        await application.initialize()
        await application.updater.start_polling()
        await application.start()
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка бота...")
    finally:
        if scheduler.running: scheduler.shutdown()
        if application.updater.running: await application.updater.stop()
        if application.running: await application.stop()
        logger.info("Бот остановлен.")

if __name__ == '__main__':
    asyncio.run(main())