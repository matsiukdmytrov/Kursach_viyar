"""Автодоповнення та підказки під час введення."""

from pathlib import Path

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from personal_assistant.cli.app import dispatch
from personal_assistant.cli.bootstrap import build_registry
from personal_assistant.cli.completion import (
    DEFAULT_HINT,
    AssistantCompleter,
    describe,
    quote_if_needed,
    split_at_cursor,
    unquote,
)
from personal_assistant.cli.registry import Registry


class TestSplitAtCursor:
    def test_empty_line(self):
        assert split_at_cursor("") == ("", "")

    def test_first_word(self):
        assert split_at_cursor("ad") == ("", "ad")

    def test_after_a_space_the_fragment_is_empty(self):
        assert split_at_cursor("add contact ") == ("add contact ", "")

    def test_second_word(self):
        assert split_at_cursor("add cont") == ("add ", "cont")

    def test_spaces_inside_quotes_do_not_split(self):
        assert split_at_cursor('add contact "Іван Пет') == ("add contact ", '"Іван Пет')

    def test_closed_quote_then_new_word(self):
        completed, fragment = split_at_cursor('add contact "Іван Петренко" 067')
        assert completed == 'add contact "Іван Петренко" '
        assert fragment == "067"

    def test_single_quotes_behave_the_same(self):
        assert split_at_cursor("add note 'Моя нот") == ("add note ", "'Моя нот")


class TestQuoting:
    def test_unquote_strips_the_opening_quote(self):
        assert unquote('"Іван') == "Іван"
        assert unquote("'Іван") == "Іван"
        assert unquote("Іван") == "Іван"

    def test_values_with_spaces_are_quoted(self):
        assert quote_if_needed("Іван Петренко") == '"Іван Петренко"'

    def test_plain_values_are_left_alone(self):
        assert quote_if_needed("Іван") == "Іван"


@pytest.fixture
def registry() -> Registry:
    return build_registry()


@pytest.fixture
def filled(registry, ctx):
    for line in (
        'add contact "Іван Петренко" 0671234567',
        'add contact "Марія Коваль" 0501112233',
        "add phone Іван 0631112233",
        'add note "Зустріч з командою"',
        'add tag Зустріч "Робочі Справи"',
        "add tag Зустріч важливе",
        'add task "Здати проєкт"',
    ):
        dispatch(registry, ctx, line)
    return ctx


@pytest.fixture
def complete(registry, filled):
    completer = AssistantCompleter(registry, filled)
    event = CompleteEvent()

    def _complete(text: str) -> list[str]:
        document = Document(text, len(text))
        return [item.text for item in completer.get_completions(document, event)]

    return _complete


class TestCommandCompletion:
    def test_completes_a_partial_command(self, complete):
        assert "add contact" in complete("add c")

    def test_offers_every_continuation(self, complete):
        assert {"add contact", "add note", "add tag", "add task", "add phone"} <= set(
            complete("add ")
        )

    def test_longer_command_is_offered_even_when_a_shorter_one_matched(self, complete):
        # `find` — це аліас команди контактів, але `find notes` теж має бути видно.
        assert "find notes" in complete("find no")

    def test_case_is_ignored(self, complete):
        assert "add contact" in complete("ADD C")

    def test_aliases_are_offered(self, complete):
        assert "contacts" in complete("cont")

    def test_unknown_prefix_gives_nothing(self, complete):
        assert complete("zzzz") == []

    def test_leading_spaces_do_not_break_it(self, complete):
        assert "add contact" in complete("   add c")


class TestArgumentCompletion:
    def test_contact_names(self, complete):
        assert '"Іван Петренко"' in complete("show contact ")

    def test_names_with_spaces_are_quoted(self, complete):
        assert all(item.startswith('"') for item in complete("show contact "))

    def test_filtering_by_what_is_typed(self, complete):
        assert complete("show contact Мар") == ['"Марія Коваль"']

    def test_filtering_matches_inside_the_value(self, complete):
        assert '"Іван Петренко"' in complete("show contact Петренко")

    def test_phones_of_the_named_contact(self, complete):
        assert set(complete("remove phone Іван ")) == {"+380671234567", "+380631112233"}

    def test_phones_of_an_unknown_contact_give_nothing(self, complete):
        assert complete("remove phone Ніхто ") == []

    def test_note_titles(self, complete):
        assert '"Зустріч з командою"' in complete("show note ")

    def test_all_tags_when_adding(self, complete):
        assert set(complete("add tag Зустріч ")) == {"важливе", "робочі-справи"}

    def test_only_the_notes_own_tags_when_removing(self, complete):
        assert set(complete("remove tag Зустріч ")) == {"важливе", "робочі-справи"}

    def test_task_statuses(self, complete):
        assert complete("set status Здати ") == ["new", "in_progress", "done", "cancelled"]

    def test_status_filter_of_the_listing(self, complete):
        assert "cancelled" in complete("list tasks ")

    def test_import_modes(self, complete):
        assert complete("import contacts data.json ") == ["skip", "replace", "merge"]

    def test_help_completes_command_names(self, complete):
        assert "exit" in complete("help ex")

    def test_free_text_argument_has_no_values(self, complete):
        assert complete("find contacts ") == []

    def test_nothing_beyond_the_last_described_argument(self, complete):
        assert complete("show contact Іван зайве ") == []


class TestPathCompletion:
    def test_offers_entries_of_an_existing_directory(self, registry, filled, tmp_path: Path):
        (tmp_path / "звіти").mkdir()
        (tmp_path / "нотатки.txt").write_text("x", encoding="utf-8")

        completer = AssistantCompleter(registry, filled)
        text = f"sort files {tmp_path}/"
        document = Document(text, len(text))
        items = list(completer.get_completions(document, CompleteEvent()))

        assert {item.text for item in items} == {"звіти", "нотатки.txt"}
        # Теки показуються зі скісною рискою — так робить сам PathCompleter.
        assert "звіти/" in {item.display_text for item in items}

    def test_export_completes_paths_too(self, registry, filled, tmp_path: Path):
        (tmp_path / "backup.json").write_text("[]", encoding="utf-8")
        completer = AssistantCompleter(registry, filled)
        text = f"export contacts {tmp_path}/back"
        document = Document(text, len(text))
        (item,) = completer.get_completions(document, CompleteEvent())

        # PathCompleter дописує лише хвіст імені, тому вставка йде від курсора.
        assert item.display_text == "backup.json"
        assert item.text == "up.json"
        assert item.start_position == 0


class TestDescribe:
    def test_no_command_gives_no_hint(self, registry):
        assert describe(registry, "add c") == ""

    def test_shows_signature_and_summary(self, registry):
        hint = describe(registry, "add contact ")
        assert "add contact <ім'я> [телефон]" in hint
        assert "Створити контакт" in hint

    def test_points_at_the_current_argument(self, registry):
        assert "▸ зараз: <ім'я>" in describe(registry, "add contact ")

    def test_moves_to_the_next_argument(self, registry):
        assert "▸ зараз: [телефон]" in describe(registry, 'add contact "Іван Петренко" ')

    def test_no_arrow_past_the_last_argument(self, registry):
        assert "▸" not in describe(registry, 'add contact "Іван" 067 зайве ')

    def test_command_without_arguments(self, registry):
        assert describe(registry, "list contacts") == ("list contacts — Показати всі контакти")

    def test_default_hint_is_not_empty(self):
        assert DEFAULT_HINT
