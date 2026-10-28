"""CLI-команди роботи з погодою."""

from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import json

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.features.weather.service import Weather

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Погода"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def register(registry: Registry) -> None:
    """Реєструє CLI-команди роботи з погодою."""
    registry.add(
        "weather",
        _get_weather,
        summary="Показати поточну погоду в будь-якому місті світу",
        group=GROUP,
        usage="<місто>",
        min_args=1,
        arguments=(Argument("<місто>"),),
    )


def _find_city(city: str) -> dict | None:
    """Шукає місто та повертає його координати."""
    params = urlencode({
        "name": city,
        "count": 10,
        "language": "uk",
        "format": "json",
    })
    url = f"{GEOCODING_URL}?{params}"

    with urlopen(url, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))

    cities = result.get("results", [])
    if not cities:
        return None

    # Спочатку надаємо перевагу точному збігу назви.
    normalized = city.strip().casefold()
    cities.sort(
        key=lambda item: (
            item.get("name", "").casefold() != normalized,
            item.get("country", ""),
        )
    )

    return cities[0]


def _get_weather(_ctx: "AppContext", args: list[str]) -> str:
    """Показує поточну погоду в будь-якому місті."""
    city = " ".join(args).strip()

    if not city:
        return "Вкажіть назву міста. Наприклад: weather Київ"

    try:
        location = _find_city(city)

        if location is None:
            return (
                f"Місто «{city}» не знайдено. "
                "Перевірте назву або спробуйте написати її англійською."
            )

        latitude = location["latitude"]
        longitude = location["longitude"]
        city_name = location["name"]
        country = location.get("country", "")

        weather = Weather(city_name, latitude, longitude)
        data = weather.get_weather()

        place = f"{city_name}, {country}" if country else city_name

        return (
            f"Погода в місті {place}\n"
            f"Температура: {data['temperature_2m']} °C\n"
            f"Вологість: {data['relative_humidity_2m']}%\n"
            f"Швидкість вітру: {data['wind_speed_10m']} км/год"
        )

    except (TimeoutError, URLError, OSError) as error:
        return f"Не вдалося підключитися до сервісу погоди: {error}"
    except (ValueError, KeyError, TypeError) as error:
        return f"Не вдалося обробити погодні дані: {error}"
    except Exception as error:
        return f"Помилка: {type(error).__name__}: {error}"