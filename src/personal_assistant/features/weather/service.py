"""Сервіс отримання погодних даних."""

import requests


class Weather:
    """Отримує поточну погоду за координатами міста."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(
        self,
        city: str,
        latitude: float,
        longitude: float,
    ) -> None:
        self.city = city
        self.latitude = latitude
        self.longitude = longitude

    def get_weather(self) -> dict:
        """Повертає поточні погодні дані."""
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "wind_speed_10m"
            ),
        }

        response = requests.get(
            self.BASE_URL,
            params=params,
            timeout=10,
        )
        response.raise_for_status()

        return response.json()["current"]