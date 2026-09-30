import pytest

from personal_assistant.features.files.naming import (
    normalize_filename,
    normalize_stem,
    split_name,
    transliterate,
)


class TestTransliterate:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("привіт", "pryvit"),
            ("Ґудзик", "Gudzyk"),
            ("їжак", "yizhak"),
            ("щука", "shchuka"),
            ("день", "den"),
            ("Юлія", "Iuliia"),
        ],
    )
    def test_ukrainian_letters(self, source, expected):
        assert transliterate(source) == expected

    def test_latin_is_untouched(self):
        assert transliterate("photo2024") == "photo2024"

    def test_uppercase_is_capitalised_not_shouted(self):
        assert transliterate("Щука") == "Shchuka"


class TestNormalizeStem:
    def test_spaces_and_punctuation_become_underscores(self):
        assert normalize_stem("Мій звіт (1)") == "Mii_zvit_1"

    def test_repeated_separators_collapse(self):
        # Саме тут поведінка відрізняється від навчальної версії.
        assert normalize_stem("файл   ---   2") == "fail_2"

    def test_edges_are_trimmed(self):
        assert normalize_stem("  звіт  ") == "zvit"

    def test_name_of_only_symbols_gets_a_fallback(self):
        assert normalize_stem("!!!") == "file"
        assert normalize_stem("") == "file"

    def test_digits_survive(self):
        assert normalize_stem("2026_звіт") == "2026_zvit"


class TestSplitName:
    def test_simple_extension(self):
        assert split_name("photo.JPG") == ("photo", ".JPG")

    def test_compound_archive_extension(self):
        assert split_name("архів.tar.gz") == ("архів", ".tar.gz")

    def test_no_extension(self):
        assert split_name("README") == ("README", "")

    def test_dotfile_is_not_split_into_an_empty_stem(self):
        assert split_name(".gitignore") == (".gitignore", "")


class TestNormalizeFilename:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("Мій звіт (1).PDF", "Mii_zvit_1.pdf"),
            ("Ґудзик.JPEG", "Gudzyk.jpeg"),
            ("архів.tar.gz", "arkhiv.tar.gz"),
            ("already_normal.txt", "already_normal.txt"),
            ("no_extension", "no_extension"),
        ],
    )
    def test_cases(self, source, expected):
        assert normalize_filename(source) == expected

    def test_extension_is_lowercased(self):
        assert normalize_filename("photo.JPEG").endswith(".jpeg")

    def test_normalized_name_is_stable(self):
        once = normalize_filename("Мій звіт (1).PDF")
        assert normalize_filename(once) == once
