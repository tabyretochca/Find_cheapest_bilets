import requests
import time
from datetime import datetime
from config import FLIGHT_API_KEY, FLIGHT_API_ENDPOINT, TRAVELPAYOUTS_MARKER

def get_iata_code(city_name):
    """
    Получает IATA-код города по названию через Travelpayouts API.
    """
    url = "https://api.travelpayouts.com/data/en/cities.json"
    params = {"query": city_name, "limit": 1, "marker": TRAVELPAYOUTS_MARKER}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("data") and len(data["data"]) > 0:
            return data["data"][0].get("code")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при поиске IATA для {city_name}: {e}")
        return None

def find_cheapest_via_aviasales(origin_city, destination_city, date_from, date_to):
    """
    Ищет самый дешевый билет через Aviasales API (Travelpayouts).
    """
    origin_iata = get_iata_code(origin_city)
    dest_iata = get_iata_code(destination_city)
    if not origin_iata or not dest_iata:
        print(f"Не удалось найти IATA для {origin_city} или {destination_city}")
        return None

    # Инициация поиска (POST)
    init_url = "https://api.travelpayouts.com/v1/flight_search"
    headers = {"Content-Type": "application/json"}
    payload = {
        "marker": TRAVELPAYOUTS_MARKER,
        "host": "your-bot-host",  # Замени на твой домен или "telegram-bot"
        "user_ip": "127.0.0.1",  # Для теста; в проде — реальный IP пользователя
        "locale": "ru",
        "trip_class": "Y",  # Economy
        "passengers": {"adults": 1, "children": 0, "infants": 0},
        "segments": [
            {"origin": origin_iata, "destination": dest_iata, "date": date_from},
            {"origin": dest_iata, "destination": origin_iata, "date": date_to}
        ]
    }
    try:
        response = requests.post(init_url, json=payload, headers=headers)
        response.raise_for_status()
        init_data = response.json()
        search_id = init_data.get("search_id")
        if not search_id:
            return None

        # Получение результатов (GET, с паузой для обработки)
        time.sleep(2)  # Ждем, пока поиск завершится (обычно 1-5 сек)
        results_url = f"https://api.travelpayouts.com/v1/flight_search_results?uuid={search_id}"
        response = requests.get(results_url)
        response.raise_for_status()
        data = response.json()

        if data.get("data") and len(data["data"]) > 0:
            cheapest = min(data["data"], key=lambda x: x["price"])
            return {
                "price": cheapest["price"],
                "link": cheapest["gate_locator"],  # Ссылка на бронирование
                "departure_city": origin_city,
                "arrival_city": destination_city,
                "departure_date": date_from,
                "return_date": date_to,
                "source": "Aviasales"
            }
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к Aviasales API: {e}")
        return None

    return None

def find_cheapest_via_kiwi(origin_city, destination_city, date_from, date_to):
    """
    Ищет через Kiwi API (оригинальная функция, слегка доработана).
    """
    headers = {"apikey": FLIGHT_API_KEY}
    params = {
        "fly_from": origin_city,  # Можно передать IATA, но Kiwi работает с названиями
        "fly_to": destination_city,
        "date_from": date_from,
        "date_to": date_from,
        "return_from": date_to,
        "return_to": date_to,
        "partner_market": "ru",
        "curr": "RUB",
        "max_stopovers": 2,
        "one_for_city": 1,
        "limit": 1
    }
    try:
        response = requests.get(FLIGHT_API_ENDPOINT, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("_results", 0) > 0:
            flight_data = data["data"][0]
            return {
                "price": flight_data["price"],
                "link": flight_data["deep_link"],
                "departure_city": flight_data["cityFrom"],
                "arrival_city": flight_data["cityTo"],
                "departure_date": flight_data["route"][0]["local_departure"].split("T")[0],
                "return_date": flight_data["route"][-1]["local_departure"].split("T")[0],  # Для return
                "source": "Kiwi"
            }
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к Kiwi API: {e}")
        return None

    return None

def find_cheapest_flight(origin_city, destination_city, date_from, date_to):
    """
    Ищет по всем API и возвращает самый дешевый.
    """
    # Параллельный поиск (в реале можно async, но для простоты последовательный)
    kiwi_flight = find_cheapest_via_kiwi(origin_city, destination_city, date_from, date_to)
    aviasales_flight = find_cheapest_via_aviasales(origin_city, destination_city, date_from, date_to)

    candidates = [f for f in [kiwi_flight, aviasales_flight] if f]
    if not candidates:
        return None

    cheapest = min(candidates, key=lambda x: x["price"])
    print(f"Найден cheapest из {cheapest['source']}: {cheapest['price']} RUB")
    return cheapest