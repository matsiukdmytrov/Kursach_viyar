from personal_assistant.core.text import (
    EMPTY,
    UKRAINIAN_ALPHABET,
    collapse_whitespace,
    collation_key,
    display_width,
    format_table,
    join_or_dash,
    pluralise,
    value_or_dash,
)


class TestValueOrDash:
    def test_none_becomes_dash(self):
        assert value_or_dash(None) == EMPTY

    def test_blank_string_becomes_dash(self):
        assert value_or_dash("   ") == EMPTY

    def test_value_is_stringified_and_trimmed(self):
        assert value_or_dash("  Львів ") == "Львів"
        assert value_or_dash(42) == "42"


class TestJoinOrDash:
    def test_joins_values(self):
        assert join_or_dash(["a", "b"]) == "a, b"

    def test_empty_becomes_dash(self):
        assert join_or_dash([]) == EMPTY


class TestPluralise:
    def test_ukrainian_forms(self):
        forms = [pluralise(n, "день", "дні", "днів") for n in (1, 2, 5, 11, 21, 22, 25, 112, 114)]
        assert forms == ["день", "дні", "днів", "днів", "день", "дні", "днів", "днів", "днів"]


class TestFormatTable:
    def test_empty_input_gives_empty_string(self):
        assert format_table([]) == ""

    def test_columns_are_aligned(self):
        table = format_table([["a", "1"], ["bbb", "2"]])
        first, second = table.splitlines()
        assert first.index("1") == second.index("2")

    def test_headers_get_a_separator_line(self):
        lines = format_table([["a", "1"]], headers=["Літера", "Число"]).splitlines()
        assert lines[0].startswith("Літера")
        assert set(lines[1]) <= {"─", " "}

    def test_no_trailing_whitespace(self):
        table = format_table([["a", "1"], ["bbb", "2"]], headers=["x", "y"])
        assert all(line == line.rstrip() for line in table.splitlines())

    def test_short_rows_are_padded(self):
        table = format_table([["a", "1"], ["b"]], headers=["x", "y"])
        assert len(table.splitlines()) == 4


class TestCollationKey:
    def test_ukrainian_alphabet_sorts_in_order(self):
        letters = list(UKRAINIAN_ALPHABET)
        assert sorted(reversed(letters), key=collation_key) == letters

    def test_letters_outside_the_main_block_are_placed_correctly(self):
        # Саме ці чотири літери ламають сортування за кодами Unicode.
        names = ["Ярина", "Іван", "Єва", "Ґалина", "Марія", "Їжак"]
        assert sorted(names, key=collation_key) == [
            "Ґалина",
            "Єва",
            "Іван",
            "Їжак",
            "Марія",
            "Ярина",
        ]

    def test_plain_sorting_would_get_it_wrong(self):
        # Фіксуємо причину існування цієї функції.
        names = ["Іван", "Марія"]
        assert sorted(names, key=str.casefold) == ["Марія", "Іван"]
        assert sorted(names, key=collation_key) == ["Іван", "Марія"]

    def test_is_case_insensitive(self):
        assert collation_key("ІВАН") == collation_key("іван")

    def test_space_sorts_before_letters(self):
        assert sorted(["Іванна", "Іван Петренко"], key=collation_key) == [
            "Іван Петренко",
            "Іванна",
        ]

    def test_latin_names_go_after_cyrillic(self):
        assert sorted(["Adam", "Богдан"], key=collation_key) == ["Богдан", "Adam"]

    def test_digits_go_before_letters(self):
        assert sorted(["Андрій", "1-й відділ"], key=collation_key) == ["1-й відділ", "Андрій"]


class TestCollapseWhitespace:
    def test_newlines_and_tabs_become_spaces(self):
        assert collapse_whitespace("Іван\nПетренко") == "Іван Петренко"
        assert collapse_whitespace("Іван\tПетренко") == "Іван Петренко"

    def test_repeated_spaces_collapse(self):
        assert collapse_whitespace("Іван    Петренко") == "Іван Петренко"

    def test_edges_are_trimmed(self):
        assert collapse_whitespace("  Іван  ") == "Іван"

    def test_whitespace_only_becomes_empty(self):
        assert collapse_whitespace(" \n\t ") == ""


class TestDisplayWidth:
    def test_latin_and_cyrillic_are_one_position_each(self):
        assert display_width("Іван") == 4
        assert display_width("John") == 4

    def test_emoji_and_ideographs_take_two(self):
        assert display_width("🙂") == 2
        assert display_width("李雷") == 4

    def test_combining_marks_take_none(self):
        # 'é' у розкладеній формі — це 'e' плюс комбінований акут.
        assert display_width("e\u0301") == 1


class TestCollationWithLatin:
    def test_diacritics_sort_next_to_the_base_letter(self):
        names = ["Zoe", "Łukasz", "Lukasz", "José", "Jose", "Adam", "Ödön"]
        assert sorted(names, key=collation_key) == [
            "Adam",
            "Jose",
            "José",
            "Lukasz",
            "Łukasz",
            "Ödön",
            "Zoe",
        ]

    def test_accented_and_plain_are_not_equal(self):
        assert collation_key("José") != collation_key("Jose")

    def test_cyrillic_comes_before_latin(self):
        assert sorted(["Adam", "Ярина"], key=collation_key) == ["Ярина", "Adam"]

    def test_stroke_letters_have_a_base(self):
        assert sorted(["Łukasz", "Mario"], key=collation_key) == ["Łukasz", "Mario"]

    def test_non_alphabetic_scripts_go_last(self):
        assert sorted(["李雷", "Adam", "Ярина"], key=collation_key) == ["Ярина", "Adam", "李雷"]


def _column_of(line: str, marker: str) -> int:
    """Екранна колонка символу — `str.index` рахує кодові точки, а не позиції."""
    return display_width(line[: line.index(marker)])


class TestTableWithWideCharacters:
    def test_columns_stay_aligned_with_emoji(self):
        first, second = format_table([["🙂", "x"], ["ab", "y"]]).splitlines()
        assert _column_of(first, "x") == _column_of(second, "y")

    def test_ideographs_do_not_shift_the_next_column(self):
        first, second = format_table([["李雷", "x"], ["abcd", "y"]]).splitlines()
        assert _column_of(first, "x") == _column_of(second, "y")

    def test_plain_indexing_would_disagree(self):
        # Фіксуємо, чому тут потрібна саме екранна ширина.
        first, second = format_table([["李雷", "x"], ["abcd", "y"]]).splitlines()
        assert first.index("x") != second.index("y")
