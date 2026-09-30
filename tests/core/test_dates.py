from datetime import date

import pytest

from personal_assistant.core.dates import format_date, next_occurrence, parse_date
from personal_assistant.core.errors import ValidationError


class TestParseDate:
    def test_reads_dd_mm_yyyy(self):
        assert parse_date("07.03.1990") == date(1990, 3, 7)

    def test_tolerates_surrounding_spaces(self):
        assert parse_date("  07.03.1990  ") == date(1990, 3, 7)

    @pytest.mark.parametrize("value", ["1990-03-07", "32.01.2000", "", "сьогодні"])
    def test_rejects_other_formats(self, value):
        with pytest.raises(ValidationError):
            parse_date(value)

    def test_round_trip(self):
        assert format_date(parse_date("29.02.2024")) == "29.02.2024"


class TestNextOccurrence:
    def test_later_this_year(self):
        assert next_occurrence(date(1990, 12, 25), date(2026, 1, 1)) == date(2026, 12, 25)

    def test_today_counts_as_upcoming(self):
        assert next_occurrence(date(1990, 5, 10), date(2026, 5, 10)) == date(2026, 5, 10)

    def test_rolls_into_next_year(self):
        assert next_occurrence(date(1990, 1, 5), date(2026, 6, 1)) == date(2027, 1, 5)

    def test_leap_day_falls_back_to_first_of_march(self):
        assert next_occurrence(date(2000, 2, 29), date(2026, 1, 1)) == date(2026, 3, 1)

    def test_leap_day_kept_in_leap_year(self):
        assert next_occurrence(date(2000, 2, 29), date(2028, 1, 1)) == date(2028, 2, 29)
