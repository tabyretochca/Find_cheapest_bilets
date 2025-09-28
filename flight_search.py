import requests
from datetime import datetime
from config import FLIGHT_API_KEY, FLIGHT_API_ENDPOINT

def find_cheapest_flight(origin_city, destination_city, date_from, date_to):
    """
    Ищет самый дешевый билет по заданному маршруту и датам.
    """
    headers = {
        "apikey": FLIGHT_API_KEY
    }
    
    params = {
        "fly_from": origin_city,
        "fly_to": destination_city,
        "date_from": date_from,
        "date_to": date_from, # Ищем на конкретную дату вылета
        "return_from": date_to,
        "return_to": date_to, # И на конкретную дату возвращения
        "partner_market": "ru",
        "curr": "RUB",
        "max_stopovers": 2, # Максимум 2 пересадки
        "one_for_city": 1,
        "limit": 1 # Ищем только один, самый дешевый
    }

    try:
        response = requests.get(FLIGHT_API_ENDPOINT, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if data["_results"] > 0:
            flight_data = data["data"][0]
            return {
                "price": flight_data["price"],
                "link": flight_data["deep_link"],
                "departure_city": flight_data["cityFrom"],
                "arrival_city": flight_data["cityTo"],
                "departure_date": flight_data["route"][0]["local_departure"].split("T")[0],
                "return_date": flight_data["route"][1]["local_departure"].split("T")[0]
            }
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API авиабилетов: {e}")
        return None

    return None
