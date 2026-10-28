"""CLI-команди курсів валют."""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from personal_assistant.cli.registry import Argument, Registry
from personal_assistant.core.dates import format_date, parse_date
from personal_assistant.core.errors import ValidationError
from personal_assistant.core.text import format_table
from personal_assistant.features.currency.models import BASE_CODE
from personal_assistant.features.currency.service import (
    POPULAR_CODES,
    CurrencyService,
    parse_amount,
)

if TYPE_CHECKING:
    from personal_assistant.context import AppContext

GROUP = "Курси валют"

#: Один сервіс на процес, щоб кеш курсів жив усю сесію REPL.
#: Тести підміняють його на сервіс із фейковим завантажувачем.
service = CurrencyService()

#: Слова, які можна вставити між валютами: `convert 100 usd в eur`.
_CONNECTORS = frozenset({"to", "в", "у", "->", "=>"})
_ALL_WORDS = frozenset({"all", "усі", "всі"})


def register(registry: Registry) -> None:
    """Реєструє CLI-команди курсів валют."""
    registry.add(
        "rates",
        _rates,
        summary="Курси НБУ основних валют (all — усіх) на сьогодні або дату",
        group=GROUP,
        usage="[all] [DD.MM.YYYY]",
        aliases=("курси",),
        arguments=(Argument("[all]", _all_word), Argument("[дата]")),
    )
    registry.add(
        "rate",
        _rate,
        summary="Курс однієї валюти до гривні",
        group=GROUP,
        usage="<валюта> [DD.MM.YYYY]",
        aliases=("курс",),
        min_args=1,
        arguments=(Argument("<валюта>", _currency_codes), Argument("[дата]")),
    )
    registry.add(
        "convert",
        _convert,
        summary="Перерахувати суму з однієї валюти в іншу за курсом НБУ",
        group=GROUP,
        usage="<сума> <з валюти> <у валюту> [DD.MM.YYYY]",
        aliases=("конвертувати",),
        min_args=3,
        arguments=(
            Argument("<сума>"),
            Argument("<з валюти>", _currency_codes),
            Argument("<у валюту>", _currency_codes),
            Argument("[дата]"),
        ),
    )


# ---------------------------------------------------------------- обробники


def _rates(_ctx: "AppContext", args: list[str]) -> str:
    show_all = False
    on_date: date | None = None
    for arg in args:
        if arg.casefold() in _ALL_WORDS:
            show_all = True
        else:
            on_date = parse_date(arg)

    rates = service.rates(on_date)
    if show_all:
        selected = sorted(rates.values(), key=lambda rate: rate.code)
    else:
        selected = [rates[code] for code in POPULAR_CODES if code in rates]

    day = next(iter(rates.values())).on_date
    table = format_table(
        [(rate.code, _format_rate(rate.rate), rate.name) for rate in selected],
        headers=("Код", "Курс, грн", "Валюта"),
    )
    footer = "" if show_all else f"\n\nУсі {len(rates)} валют: rates all"
    return f"Офіційний курс НБУ на {format_date(day)}\n\n{table}{footer}"


def _rate(_ctx: "AppContext", args: list[str]) -> str:
    on_date = _optional_date(args[1:], expected=1)
    rate = service.rate(args[0], on_date)
    if rate.code == BASE_CODE:
        return "Гривня — базова валюта НБУ: 1 UAH = 1 UAH."
    return (
        f"{rate.name} ({rate.code}) на {format_date(rate.on_date)}:\n"
        f"1 {rate.code} = {_format_rate(rate.rate)} UAH\n"
        f"1 UAH = {_format_rate(Decimal(1) / rate.rate)} {rate.code}"
    )


def _convert(_ctx: "AppContext", args: list[str]) -> str:
    words = [arg for arg in args if arg.casefold() not in _CONNECTORS]
    if len(words) < 3:
        raise ValidationError("Вкажи суму і дві валюти. Приклад: convert 100 USD EUR")

    amount = parse_amount(words[0])
    on_date = _optional_date(words[3:], expected=1)
    result, source, target = service.convert(amount, words[1], words[2], on_date)

    day = source.on_date if source.code != BASE_CODE else target.on_date
    lines = [
        f"{_format_money(amount)} {source.code} = {_format_money(result)} {target.code}",
        f"Курс НБУ на {format_date(day)}: "
        + ", ".join(
            f"1 {rate.code} = {_format_rate(rate.rate)} UAH"
            for rate in (source, target)
            if rate.code != BASE_CODE
        ),
    ]
    if source.code == target.code:
        lines = lines[:1]
    return "\n".join(lines)


# ---------------------------------------------------------------- допоміжне


def _optional_date(rest: list[str], *, expected: int) -> date | None:
    if len(rest) > expected:
        raise ValidationError(f"Зайві аргументи: {' '.join(rest[expected:])}")
    return parse_date(rest[0]) if rest else None


def _format_rate(value: Decimal) -> str:
    return f"{value:.4f}"


def _format_money(value: Decimal) -> str:
    # Пробіл як роздільник тисяч — звично для українського запису сум.
    return f"{value:,.2f}".replace(",", " ")


def _currency_codes(_ctx: "AppContext", _args: list[str]) -> Iterable[str]:
    # Без мережі: Tab не повинен чекати на НБУ.
    return (*POPULAR_CODES, BASE_CODE)


def _all_word(_ctx: "AppContext", _args: list[str]) -> Iterable[str]:
    return ("all",)
