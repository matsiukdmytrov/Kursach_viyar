"""Розбір і форматування дат у тому вигляді, у якому їх вводить користувач."""

from datetime import date, datetime

from personal_assistant.core.errors import ValidationError

#: Формат дат у CLI — той самий, що в технічному завданні.
DATE_FORMAT = "%d.%m.%Y"
DATE_FORMAT_HINT = "DD.MM.YYYY"


def parse_date(value: str) -> date:
    """Перетворює рядок `DD.MM.YYYY` на дату."""
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise ValidationError(
            f"Не вдалося прочитати дату '{value}'. Очікуваний формат: {DATE_FORMAT_HINT}."
        ) from exc


def coerce_date(value: str) -> date:
    """Приймає і те, що вводить користувач, і те, що лежить у сховищі.

    У JSON дати зберігаються в ISO (`1990-08-25`), а користувач вводить їх як
    `25.08.1990`. Валідатор моделі бачить обидва варіанти, тому мусить
    розуміти обидва — інакше застосунок падає при читанні власного файлу.
    """
    raw = value.strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return parse_date(raw)


def format_date(value: date) -> str:
    """Перетворює дату на рядок `DD.MM.YYYY`."""
    return value.strftime(DATE_FORMAT)


def next_occurrence(day: date, today: date) -> date:
    """Найближчі роковини `day` починаючи з `today` (сам `today` враховується).

    29 лютого у невисокосний рік відзначається 1 березня — інакше такий контакт
    просто зникав би зі списку іменинників у три роки з чотирьох.
    """
    year = today.year
    for candidate_year in (year, year + 1):
        candidate = _on_year(day, candidate_year)
        if candidate >= today:
            return candidate
    raise AssertionError("unreachable")  # pragma: no cover


def _on_year(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:
        # 29 лютого у невисокосному році
        return date(year, 3, 1)
