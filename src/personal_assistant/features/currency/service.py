"""Завантаження офіційних курсів НБУ та конвертація валют.

Джерело — відкритий API Національного банку України: ключ не потрібен,
курси публікуються на кожен робочий день (на вихідні діє курс п'ятниці, але
API однаково повертає дані за будь-яку дату).
"""

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from personal_assistant.core.errors import NotFoundError, PersonalAssistantError, ValidationError
from personal_assistant.features.currency.models import BASE_CODE, Rate

NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
TIMEOUT_SECONDS = 10

#: Валюти, які показує `rates` без `all`, — у порядку показу.
POPULAR_CODES = ("USD", "EUR", "PLN", "GBP", "CHF", "CZK", "CAD", "JPY", "CNY")

#: Як користувачі називають валюти замість ISO-кодів.
ALIASES: dict[str, str] = {
    "$": "USD",
    "долар": "USD",
    "долари": "USD",
    "доларів": "USD",
    "дол": "USD",
    "€": "EUR",
    "євро": "EUR",
    "£": "GBP",
    "фунт": "GBP",
    "фунти": "GBP",
    "злотий": "PLN",
    "злоті": "PLN",
    "злотих": "PLN",
    "франк": "CHF",
    "франки": "CHF",
    "крона": "CZK",
    "крони": "CZK",
    "єна": "JPY",
    "юань": "CNY",
    "₴": BASE_CODE,
    "грн": BASE_CODE,
    "гривня": BASE_CODE,
    "гривні": BASE_CODE,
    "гривень": BASE_CODE,
}

#: Отримує сирий JSON для дати. Підміняється в тестах, щоб не ходити в мережу.
type Fetcher = Callable[[date], Any]


class ExchangeServiceError(PersonalAssistantError):
    """НБУ недоступний або повернув щось незрозуміле."""


def fetch_from_nbu(on_date: date) -> Any:
    """Запитує в НБУ курси всіх валют на дату."""
    query = urlencode({"date": on_date.strftime("%Y%m%d"), "json": ""})
    request = Request(f"{NBU_URL}?{query}", headers={"User-Agent": "personal-assistant"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ExchangeServiceError(
            f"Не вдалося підключитися до НБУ: {reason}. Перевір з'єднання з інтернетом."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExchangeServiceError("НБУ повернув відповідь у незрозумілому форматі.") from exc


def parse_rates(payload: Any, on_date: date) -> dict[str, Rate]:
    """Перетворює відповідь НБУ на словник `код -> Rate`.

    Окремі биті записи пропускаємо, а не валимо весь запит: одна дивна валюта
    в довіднику не повинна ховати курс долара.
    """
    if not isinstance(payload, list):
        raise ExchangeServiceError("НБУ повернув відповідь у незрозумілому форматі.")

    rates: dict[str, Rate] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get("cc", "")).strip().upper()
        raw_rate = item.get("rate")
        if not code or raw_rate is None:
            continue
        try:
            value = Decimal(str(raw_rate))
        except InvalidOperation:
            continue
        if value <= 0:
            continue
        rates[code] = Rate(
            code=code,
            name=str(item.get("txt", code)).strip() or code,
            rate=value,
            on_date=_published_date(item, on_date),
        )
    return rates


def _published_date(item: dict[str, Any], fallback: date) -> date:
    raw = item.get("exchangedate")
    if isinstance(raw, str):
        try:
            return datetime.strptime(raw, "%d.%m.%Y").date()
        except ValueError:
            pass
    return fallback


def parse_amount(text: str) -> Decimal:
    """Сума так, як її вводять люди: `100`, `99,90`, `1_000`, `1000.5`."""
    cleaned = text.strip().replace(",", ".").replace("_", "").replace(" ", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValidationError(f"'{text}' не схоже на суму. Приклад: 100 або 99,90.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValidationError("Сума має бути невід'ємним числом.")
    return amount


def normalize_code(text: str) -> str:
    """Код валюти з того, що ввів користувач: `usd`, `долар`, `$` -> `USD`."""
    key = text.strip().casefold()
    return ALIASES.get(key, key.upper())


class CurrencyService:
    """Курси НБУ з кешем на час роботи застосунку.

    Курс за минулу дату вже не зміниться, тому кешуємо кожну дату, яку
    запитували. Так `convert` після `rates` не робить другий запит у мережу.
    """

    def __init__(self, fetcher: Fetcher = fetch_from_nbu) -> None:
        self._fetcher = fetcher
        self._cache: dict[date, dict[str, Rate]] = {}

    def rates(self, on_date: date | None = None) -> dict[str, Rate]:
        """Усі курси на дату (за замовчуванням — сьогодні)."""
        day = self._check_date(on_date)
        if day not in self._cache:
            rates = parse_rates(self._fetcher(day), day)
            if not rates:
                raise NotFoundError(
                    f"НБУ не має курсів на {day.strftime('%d.%m.%Y')}. Спробуй іншу дату."
                )
            self._cache[day] = rates
        return self._cache[day]

    def rate(self, code: str, on_date: date | None = None) -> Rate:
        """Курс однієї валюти; гривня повертається як 1:1."""
        normalized = normalize_code(code)
        day = self._check_date(on_date)
        if normalized == BASE_CODE:
            return Rate.base(day)
        rates = self.rates(day)
        found = rates.get(normalized)
        if found is None:
            raise NotFoundError(
                f"Валюту '{code}' не знайдено в довіднику НБУ. Повний перелік кодів — `rates all`."
            )
        return found

    def convert(
        self, amount: Decimal, source: str, target: str, on_date: date | None = None
    ) -> tuple[Decimal, Rate, Rate]:
        """Перераховує суму через гривню: НБУ дає лише крос-курси до UAH."""
        from_rate = self.rate(source, on_date)
        to_rate = self.rate(target, on_date)
        result = amount * from_rate.rate / to_rate.rate
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), from_rate, to_rate

    @staticmethod
    def _check_date(on_date: date | None) -> date:
        today = date.today()
        day = on_date or today
        # НБУ встановлює курс на завтра вже сьогодні по обіді, далі — порожньо.
        if day > today + timedelta(days=1):
            raise ValidationError("Курс на майбутні дати ще не встановлено.")
        return day
