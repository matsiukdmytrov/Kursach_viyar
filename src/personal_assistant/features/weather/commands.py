"""CLI-команди роботи з погодою."""

from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.features.weather.service import Weather

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Погода"

CITIES = {
    "київ": (50.4501, 30.5234),
    "львів": (49.8397, 24.0297),
    "одеса": (46.4825, 30.7233),
    "харків": (49.9935, 36.2304),
    "дніпро": (48.4647, 35.0462),
}


def register(registry: Registry) -> None:
    """Реєструє CLI-команди роботи з погодою."""
    registry.add(
        "weather",
        _get_weather,
        summary="Показати поточну погоду в місті",
        group=GROUP,
        usage="<місто>",
        min_args=1,
        arguments=(Argument("<місто>"),),
    )


def _get_weather(_ctx: "AppContext", args: list[str]) -> str:
    """Показує поточну погоду."""
    city = " ".join(args).strip()
    coordinates = CITIES.get(city.casefold())

    if coordinates is None:
        available = ", ".join(name.title() for name in CITIES)
        return (
            f"Місто «{city}» не знайдено.\n"
            f"Доступні міста: {available}."
        )

    latitude, longitude = coordinates
    weather = Weather(city, latitude, longitude)

    try:
        data = weather.get_weather()
    except (ValueError, KeyError, OSError, TimeoutError) as error:
        return f"Не вдалося отримати погоду: {error}"
    except Exception:
        return "Помилка під час отримання погодних даних."

    return (
        f"Погода в місті {city.title()}\n"
        f"Температура: {data['temperature_2m']} °C\n"
        f"Вологість: {data['relative_humidity_2m']}%\n"
        f"Швидкість вітру: {data['wind_speed_10m']} км/год"
    )