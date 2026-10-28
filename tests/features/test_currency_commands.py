"""Команди курсів валют через `dispatch` — без звернень до мережі."""

from datetime import date

import pytest

from personal_assistant.cli.app import dispatch
from personal_assistant.cli.bootstrap import build_registry
from personal_assistant.features.currency import commands
from personal_assistant.features.currency.service import CurrencyService, ExchangeServiceError

PAYLOAD = [
    {"txt": "Долар США", "rate": 41.5, "cc": "USD", "exchangedate": "27.10.2026"},
    {"txt": "Євро", "rate": 48.25, "cc": "EUR", "exchangedate": "27.10.2026"},
    {"txt": "Злотий", "rate": 11.3, "cc": "PLN", "exchangedate": "27.10.2026"},
    {"txt": "Ріал Катару", "rate": 11.4, "cc": "QAR", "exchangedate": "27.10.2026"},
]


@pytest.fixture
def requested(monkeypatch) -> list[date]:
    calls: list[date] = []

    def fake(on_date: date):
        calls.append(on_date)
        return PAYLOAD

    monkeypatch.setattr(commands, "service", CurrencyService(fake))
    return calls


@pytest.fixture
def run(ctx, requested):
    registry = build_registry()

    def _run(line: str) -> str:
        return dispatch(registry, ctx, line)

    return _run


class TestRates:
    def test_shows_popular(self, run):
        output = run("rates")
        assert "USD" in output
        assert "41.5000" in output

    def test_hides_rare_without_all(self, run):
        assert "QAR" not in run("rates")

    def test_all_shows_rare(self, run):
        assert "QAR" in run("rates all")

    def test_passes_date(self, run, requested):
        run("rates 01.09.2026")
        assert requested == [date(2026, 9, 1)]

    def test_bad_date(self, run):
        assert "DD.MM.YYYY" in run("rates вчора")

    def test_ukrainian_alias(self, run):
        assert "USD" in run("курси")


class TestRate:
    def test_both_directions(self, run):
        output = run("rate usd")
        assert "1 USD = 41.5000 UAH" in output
        assert "1 UAH = 0.0241 USD" in output

    def test_unknown(self, run):
        assert "не знайдено" in run("rate ZZZ")

    def test_missing_argument_shows_usage(self, run):
        assert "Використання: rate" in run("rate")


class TestConvert:
    def test_basic(self, run):
        assert "100.00 USD = 4 150.00 UAH" in run("convert 100 usd uah")

    def test_connector_word(self, run):
        assert "= 116.27 USD" in run("convert 100 EUR в USD")

    def test_comma_amount(self, run):
        assert "10.50 USD" in run("convert 10,50 долар грн")

    def test_bad_amount(self, run):
        assert "не схоже на суму" in run("convert сто usd uah")

    def test_extra_arguments(self, run):
        assert "Зайві аргументи" in run("convert 1 usd uah 01.09.2026 щось")


class TestNetworkFailure:
    def test_message_instead_of_traceback(self, ctx, monkeypatch):
        def broken(_on_date: date):
            raise ExchangeServiceError("Не вдалося підключитися до НБУ")

        monkeypatch.setattr(commands, "service", CurrencyService(broken))
        output = dispatch(build_registry(), ctx, "rates")
        assert output.startswith("Помилка: Не вдалося підключитися до НБУ")
