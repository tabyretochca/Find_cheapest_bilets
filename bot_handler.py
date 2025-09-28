from telegram import Update
from telegram.ext import ContextTypes
from database import SessionLocal, User, TrackedFlight
from flight_search import find_cheapest_flight

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для отслеживания цен на авиабилеты.\n"
        "Используй команду /track, чтобы начать отслеживание.\n\n"
        "Формат команды:\n"
        "/track [Город вылета] [Город прилета] [ДД.ММ.ГГГГ вылета] [ДД.ММ.ГГГГ возврата] [Макс. цена]"
    )

async def track_flight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    args = context.args

    if len(args) != 5:
        await update.message.reply_text(
            "Неверный формат. Используйте:\n"
            "/track [Город вылета] [Город прилета] [Дата вылета] [Дата возврата] [Цена]"
        )
        return

    origin, destination, dep_date_str, ret_date_str, price_str = args
    
    try:
        price_threshold = float(price_str)
    except ValueError:
        await update.message.reply_text("Цена должна быть числом.")
        return

    # TODO: Добавить валидацию дат

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.chat_id == chat_id).first()
        if not user:
            user = User(chat_id=chat_id)
            db.add(user)
            db.commit()
            db.refresh(user)

        new_tracking = TrackedFlight(
            user_id=user.id,
            origin=origin,
            destination=destination,
            departure_date=dep_date_str,
            return_date=ret_date_str,
            price_threshold=price_threshold
        )
        db.add(new_tracking)
        db.commit()

        await update.message.reply_text(
            f"Отлично! Начинаю отслеживать рейс из {origin} в {destination} "
            f"с вылетом {dep_date_str} и возвратом {ret_date_str} "
            f"при цене ниже {price_threshold} RUB."
        )
    finally:
        db.close()


async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    """
    Периодическая задача для проверки цен на отслеживаемые рейсы.
    """
    db = SessionLocal()
    try:
        flights_to_check = db.query(TrackedFlight).filter(TrackedFlight.notified == False).all()
        for flight in flights_to_check:
            found_flight = find_cheapest_flight(
                flight.origin, flight.destination, flight.departure_date, flight.return_date
            )

            if found_flight and found_flight["price"] <= flight.price_threshold:
                user = db.query(User).filter(User.id == flight.user_id).first()
                if user:
                    message = (
                        f"🔥 Найдена выгодная цена! 🔥\n\n"
                        f"Источник: {found_flight.get('source', 'Unknown')}\n"
                        f"Рейс: {found_flight['departure_city']} -> {found_flight['arrival_city']}\n"
                        f"Даты: {found_flight['departure_date']} - {found_flight['return_date']}\n"
                        f"Цена: {found_flight['price']} RUB\n\n"
                        f"Купить билет: {found_flight['link']}"
                    )
                    await context.bot.send_message(chat_id=user.chat_id, text=message)
                    
                    flight.notified = True
                    db.commit()
    finally:
        db.close()