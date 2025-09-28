import os
from dotenv import load_dotenv

load_dotenv()

# Токен вашего Telegram-бота (получается у @BotFather)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# Ключ API для поиска авиабилетов (например, от Kiwi.com или SerpApi)
FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY", "YOUR_FLIGHT_API_KEY")

# URL API для поиска
FLIGHT_API_ENDPOINT = "https://tequila-api.kiwi.com/v2/search" # Пример для Kiwi.com

# Travelpayouts marker для Aviasales API
TRAVELPAYOUTS_MARKER = os.getenv("TRAVELPAYOUTS_MARKER", "YOUR_TRAVELPAYOUTS_MARKER")

# Название файла базы данных
DATABASE_FILE = "flights.db"
