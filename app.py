from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TELEGRAM_BOT_TOKEN
from bot_handler import start, track_flight, check_prices
from database import init_db

def main():
    # Инициализация базы данных
    init_db()

    # Создание приложения бота
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track_flight))

    # Настройка и запуск планировщика для периодической проверки цен
    scheduler = AsyncIOScheduler()
    # Проверять цены каждые 4 часа
    scheduler.add_job(check_prices, 'interval', hours=4, args=[application])
    scheduler.start()
    
    print("Бот запущен и готов к работе...")
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
