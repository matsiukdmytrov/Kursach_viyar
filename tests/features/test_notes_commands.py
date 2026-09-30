"""Команди нотаток перевіряємо через `dispatch`, як це робить REPL."""

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
def filled(run):
    run('add note "Зустріч з командою" "Обговорити реліз"')
    run('add note "Купити продукти" "хліб, молоко"')
    run("add tag Зустріч робота")
    run("add tag Купити дім")
    return run


class TestAddNote:
    def test_creates_note_and_shows_its_identifier(self, run):
        output = run('add note "Зустріч" "Текст"')
        assert "створено" in output
        assert "[" in output

    def test_text_without_quotes_is_joined(self, run, ctx):
        run("add note Зустріч обговорити реліз та плани")
        assert ctx.notes.all()[0].text == "обговорити реліз та плани"

    def test_note_without_text(self, run, ctx):
        run('add note "Тільки заголовок"')
        assert ctx.notes.all()[0].text == ""

    def test_missing_title_shows_usage(self, run):
        assert "Використання: add note" in run("add note")


class TestListing:
    def test_empty_gives_a_hint(self, run):
        assert "add note" in run("list notes")

    def test_alias_works(self, filled):
        assert "Зустріч з командою" in filled("notes")

    def test_recently_updated_comes_first(self, filled):
        filled('edit note Зустріч "новий текст"')
        output = filled("list notes")
        assert output.index("Зустріч з командою") < output.index("Купити продукти")

    def test_long_text_is_truncated_in_the_table(self, run):
        run(f'add note "Довга" "{"а" * 200}"')
        assert "…" in run("list notes")


class TestShowNote:
    def test_shows_title_tags_and_text(self, filled):
        output = filled("show note Зустріч")
        assert "Зустріч з командою" in output
        assert "#робота" in output
        assert "Обговорити реліз" in output

    def test_unknown_note(self, filled):
        assert "не знайдено" in filled("show note Немає")

    def test_by_identifier(self, filled, ctx):
        note = ctx.notes.all()[0]
        assert note.title in filled(f"show note {note.short_id}")

    def test_ambiguous_titles_are_listed_with_identifiers(self, run):
        run('add note "Зустріч"')
        run('add note "Зустріч"')
        output = run("show note Зустріч")
        assert "підходить кільком нотаткам" in output


class TestTags:
    def test_add_tag_normalises_it(self, filled):
        assert "#важливе" in filled('add tag Зустріч "#Важливе"')

    def test_add_existing_tag(self, filled):
        assert "вже має тег" in filled("add tag Зустріч робота")

    def test_remove_tag(self, filled):
        assert "прибрано тег #робота" in filled("remove tag Зустріч робота")

    def test_remove_missing_tag(self, filled):
        assert "не має тегу" in filled("remove tag Зустріч невідомий")

    def test_multiword_tag_becomes_hyphenated(self, filled):
        assert "#робочі-справи" in filled('add tag Зустріч "Робочі Справи"')

    def test_too_few_arguments(self, filled):
        assert "Використання: add tag" in filled("add tag Зустріч")


class TestTagQueries:
    def test_notes_by_tag(self, filled):
        output = filled("notes by tag робота")
        assert "Зустріч з командою" in output
        assert "Купити продукти" not in output

    def test_notes_by_tag_ignores_formatting(self, filled):
        assert "Зустріч з командою" in filled("notes by tag #РОБОТА")

    def test_notes_by_unknown_tag(self, filled):
        assert "немає" in filled("notes by tag невідомий")

    def test_list_tags_shows_counts(self, filled):
        output = filled("list tags")
        assert "#дім" in output
        assert "#робота" in output

    def test_list_tags_alias(self, filled):
        assert filled("tags") == filled("list tags")

    def test_list_tags_when_there_are_none(self, run):
        run('add note "Без тегів"')
        assert "Тегів ще немає" in run("list tags")

    def test_sort_notes_groups_by_tag(self, filled):
        output = filled("sort notes")
        assert output.index("Купити продукти") < output.index("Зустріч з командою")

    def test_sort_notes_when_empty(self, run):
        assert "Нотаток ще немає" in run("sort notes")


class TestEditRenameDelete:
    def test_edit_replaces_text(self, filled, ctx):
        filled('edit note Купити "новий список"')
        note = next(n for n in ctx.notes if n.title == "Купити продукти")
        assert note.text == "новий список"

    def test_rename(self, filled):
        assert "перейменовано" in filled('rename note Купити "Список покупок"')

    def test_delete(self, filled, ctx):
        assert "видалено" in filled("delete note Купити")
        assert len(ctx.notes) == 1

    def test_delete_unknown(self, filled):
        assert "не знайдено" in filled("delete note Немає")


class TestSearch:
    def test_finds_by_text(self, filled):
        assert "Зустріч з командою" in filled("find notes реліз")

    def test_finds_by_tag(self, filled):
        assert "Купити продукти" in filled("find notes дім")

    def test_nothing_found(self, filled):
        assert "нічого не знайдено" in filled("find notes zzzz")


class TestCommandCollisions:
    """Команди нотаток не мають перехоплювати команди контактів."""

    def test_find_alone_still_searches_contacts(self, run, ctx):
        run('add contact "Іван Петренко"')
        assert "Іван Петренко" in run("find Петренко")

    def test_find_notes_searches_notes(self, filled):
        assert "Зустріч з командою" in filled("find notes Зустріч")

    def test_notes_alias_and_notes_by_tag_coexist(self, filled):
        assert "Заголовок" in filled("notes")
        assert "Зустріч з командою" in filled("notes by tag робота")

    def test_add_tag_does_not_shadow_add_contact(self, run):
        assert "створено" in run('add contact "Іван"')

    def test_help_lists_both_groups(self, run):
        output = run("help")
        assert "Контакти" in output
        assert "Нотатки" in output
