"""Команди роботи з файлами через `dispatch`."""

from pathlib import Path

import pytest

from personal_assistant.cli.app import dispatch
from personal_assistant.cli.bootstrap import build_registry
from personal_assistant.cli.registry import Registry


@pytest.fixture
def registry() -> Registry:
    return build_registry()


@pytest.fixture
def run(registry, ctx):
    def _run(line: str) -> str:
        return dispatch(registry, ctx, line)

    return _run


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "тека").mkdir(parents=True)
    (root / "Мій звіт.PDF").write_text("однаковий", encoding="utf-8")
    (root / "kopiia.pdf").write_text("однаковий", encoding="utf-8")
    (root / "Ґудзик.JPEG").write_text("фото", encoding="utf-8")
    (root / "тека" / "Пісня.mp3").write_text("пісня", encoding="utf-8")
    (root / ".hidden").write_text("x", encoding="utf-8")
    return root


class TestSortFiles:
    def test_groups_by_category(self, run, tree):
        output = run(f'sort files "{tree}"')
        assert "images/" in output
        assert "documents/" in output
        assert "audio/" in output

    def test_shows_the_new_names(self, run, tree):
        assert "Gudzyk.jpeg" in run(f'sort files "{tree}"')

    def test_states_that_nothing_changed(self, run, tree):
        assert "на диску нічого не змінено" in run(f'sort files "{tree}"')

    def test_really_changes_nothing(self, run, tree):
        before = {str(p) for p in tree.rglob("*")}
        run(f'sort files "{tree}"')
        assert {str(p) for p in tree.rglob("*")} == before

    def test_reports_hidden_files(self, run, tree):
        assert "приховані пропущено: 1" in run(f'sort files "{tree}"')

    def test_empty_directory(self, run, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert "немає файлів" in run(f'sort files "{empty}"')

    def test_missing_directory(self, run):
        assert "не існує" in run("sort files /немає/такої/теки")

    def test_path_instead_of_directory(self, run, tree):
        assert "це файл, а не тека" in run(f'sort files "{tree / "kopiia.pdf"}"')

    def test_missing_argument_shows_usage(self, run):
        assert "Використання: sort files" in run("sort files")

    def test_path_with_spaces_needs_quotes_only(self, run, tmp_path):
        spaced = tmp_path / "тека з пробілами"
        spaced.mkdir()
        (spaced / "файл.txt").write_text("x", encoding="utf-8")
        assert "documents/" in run(f'sort files "{spaced}"')


class TestNormalizeNames:
    def test_lists_the_renames(self, run, tree):
        output = run(f'normalize names "{tree}"')
        assert "Mii_zvit.pdf" in output
        assert "Gudzyk.jpeg" in output

    def test_already_normal_names_are_absent(self, run, tree):
        assert "kopiia.pdf" not in run(f'normalize names "{tree}"')

    def test_states_that_nothing_changed(self, run, tree):
        assert "на диску нічого не змінено" in run(f'normalize names "{tree}"')

    def test_really_changes_nothing(self, run, tree):
        before = {str(p) for p in tree.rglob("*")}
        run(f'normalize names "{tree}"')
        assert {str(p) for p in tree.rglob("*")} == before

    def test_nothing_to_do(self, run, tmp_path):
        root = tmp_path / "clean"
        root.mkdir()
        (root / "normal.txt").write_text("x", encoding="utf-8")
        assert "вже нормалізовані" in run(f'normalize names "{root}"')


class TestFindDuplicates:
    def test_reports_the_group(self, run, tree):
        output = run(f'find duplicates "{tree}"')
        assert "kopiia.pdf" in output
        assert "Мій звіт.PDF" in output

    def test_reports_wasted_space(self, run, tree):
        assert "місця займають" in run(f'find duplicates "{tree}"')

    def test_states_that_nothing_was_deleted(self, run, tree):
        assert "Нічого не видалено" in run(f'find duplicates "{tree}"')

    def test_really_deletes_nothing(self, run, tree):
        before = {str(p) for p in tree.rglob("*")}
        run(f'find duplicates "{tree}"')
        assert {str(p) for p in tree.rglob("*")} == before

    def test_no_duplicates(self, run, tmp_path):
        root = tmp_path / "unique"
        root.mkdir()
        (root / "a.txt").write_text("a", encoding="utf-8")
        assert "не знайдено" in run(f'find duplicates "{root}"')


class TestCommandCollisions:
    def test_find_duplicates_does_not_shadow_other_find_commands(self, run, tree):
        run('add contact "Іван Петренко"')
        run('add note "Нотатка"')
        run('add task "Задача"')

        assert "Іван Петренко" in run("find Петренко")
        assert "Нотатка" in run("find notes Нотатка")
        assert "Задача" in run("find tasks Задача")
        assert "kopiia.pdf" in run(f'find duplicates "{tree}"')

    def test_sort_files_does_not_shadow_sort_notes(self, run):
        run('add note "Нотатка" "текст"')
        assert "Нотатка" in run("sort notes")

    def test_files_group_appears_in_help(self, run):
        assert "Файли" in run("help")
