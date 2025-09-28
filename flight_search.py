import os
import logging
from datetime import datetime
import requests
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
# Используем новый, более подходящий эндпоинт API
AVIASALES_API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

# Словарь для IATA-кодов
IATA_CODES = {
    "москва": "MOW",
    "минеральные воды": "MRV"
}

# --- НАСТРОЙКА БАЗЫ ДАННЫХ (с новой структурой) ---
DATABASE_FILE = "subscriptions.db"
engine = create_engine(f"sqlite:///{DATABASE_FILE}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, index=True)
    origin = Column(String, index=True)
    destination = Column(String, index=True)
    departure_date = Column(String) # Дата вылета
    return_date = Column(String)    # Дата возврата
    price_threshold = Column(Float)

Base.metadata.create_all(bind=engine)

# --- ОБНОВЛЕННАЯ ЛОГИКА ПОИСКА БИЛЕТОВ ---
def find_flight_for_dates(origin, destination, depart_date, return_date, token):
    """Ищет самый дешевый билет на конкретные даты."""
    params = {
        'origin': origin,
        'destination': destination,
        'departure_at': depart_date, # YYYY-MM-DD
        'return_at': return_date,     # YYYY-MM-DD
        'token': token,
        'currency': 'rub',
        'limit': 5, # Ищем несколько вариантов, чтобы найти самый дешевый
        'sorting': 'price'
    }
    try:
        response = requests.get(AVIASALES_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get('success') and data.get('data'):
            flight_info = data['data'][0] # Берем самый первый (он же самый дешевый из-за сортировки)
            return {
                "price": flight_info['price'],
                "link": flight_info['link']
            }
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к API Aviasales: {e}")
    except (IndexError, KeyError) as e:
        logger.info(f"Билеты на даты {depart_date} - {return_date} не найдены. Ошибка: {e}")
    return None

# --- ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ КОМАНД БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для отслеживания дешевых билетов между Москвой и Минеральными Водами на **конкретные даты**.\n\n"
        "Используйте команду /track для подписки на уведомления.\n\n"
        "**Формат:**\n`/track [Дата вылета] [Дата возврата] [Макс. цена]`\n\n"
        "**Пример:**\n`/track 2025-01-07 2025-01-14 15000`\n\n"
        "Даты указывайте в формате `ГГГГ-ММ-ДД`."
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    args = context.args

    if len(args) != 3:
        await update.message.reply_text(
            "Неверный формат. Пример:\n`/track 2025-01-07 2025-01-14 15000`"
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
        # Добавляем подписку в обе стороны
        sub1 = Subscription(
            chat_id=chat_id, origin=IATA_CODES["москва"], destination=IATA_CODES["минеральные воды"],
            departure_date=depart_date_str, return_date=return_date_str, price_threshold=price_threshold
        )
        sub2 = Subscription(
            chat_id=chat_id, origin=IATA_CODES["минеральные воды"], destination=IATA_CODES["москва"],
            departure_date=depart_date_str, return_date=return_date_str, price_threshold=price_threshold
        )
        db.add(sub1)
        db.add(sub2)
        db.commit()

        await update.message.reply_text(
            f"Принято! Буду искать билеты:\n"
            f"🛫 Вылет: {depart_date_str}\n"
            f"🛬 Возврат: {return_date_str}\n"
            f"💰 Дешевле чем: {price_threshold} RUB"
        )
    finally:
        db.close()

# --- ОБНОВЛЕННАЯ ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ ЦЕН ---
async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Начинаю плановую проверку цен по датам...")
    db = SessionLocal()
    try:
        subscriptions = db.query(Subscription).all()
        for sub in subscriptions:
            flight = find_flight_for_dates(
                sub.origin, sub.destination, sub.departure_date, sub.return_date, AVIASALES_API_TOKEN
            )
            
            if flight and flight['price'] <= sub.price_threshold:
                message = (
                    f"🔥 Найдена выгодная цена на ваши даты! 🔥\n\n"
                    f"✈️ **Маршрут:** {sub.origin} → {sub.destination}\n"
                    f"🛫 **Вылет:** {sub.departure_date}\n"
                    f"🛬 **Возврат:** {sub.return_date}\n"
                    f"💰 **Цена:** {flight['price']} RUB\n\n"
                    f"➡️ [Купить билет]({flight['link']})"
                )
                await context.bot.send_message(
                    chat_id=sub.chat_id, text=message, parse_mode='Markdown'
                )
                # Удаляем подписку после уведомления, чтобы не спамить
                db.delete(sub)
        db.commit()
    except Exception as e:
        logger.error(f"Ошибка в задаче проверки цен: {e}")
    finally:
        db.close()
        logger.info("Проверка цен по датам завершена.")

# --- ЗАПУСК БОТА (код остался таким же) ---
async def main():
    if not TELEGRAM_BOT_TOKEN or not AVIASALES_API_TOKEN:
        logger.error("Не найдены токены! Убедитесь, что у вас есть файл .env")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track)) 

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(check_prices, 'interval', hours=4, args=[application])
    scheduler.start()
    await check_prices(application) 
    
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
