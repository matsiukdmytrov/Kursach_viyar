"""Команди контактів перевіряємо через `dispatch` — тим самим шляхом, яким іде REPL."""

from datetime import date, timedelta

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
    run('add contact "Іван Петренко" 0671234567')
    run('add contact "Марія Коваль"')
    return run


class TestAddContact:
    def test_creates_contact(self, run):
        assert "створено" in run('add contact "Іван Петренко"')

    def test_quoted_name_stays_whole(self, run, ctx):
        run('add contact "Іван Петренко"')
        assert ctx.contacts.all()[0].name == "Іван Петренко"

    def test_phone_typed_without_quotes_is_accepted(self, run, ctx):
        run('add contact "Іван" 067 123 45 67')
        assert ctx.contacts.all()[0].phones == ["+380671234567"]

    def test_missing_name_shows_usage(self, run):
        assert "Використання: add contact" in run("add contact")

    def test_invalid_phone_reports_an_error(self, run):
        assert "Помилка" in run('add contact "Іван" абв')

    def test_duplicate_name_reports_an_error(self, filled):
        assert "уже існує" in filled('add contact "Іван Петренко"')


class TestListing:
    def test_empty_book_explains_what_to_do(self, run):
        assert "add contact" in run("list contacts")

    def test_table_contains_every_contact(self, filled):
        output = filled("list contacts")
        assert "Іван Петренко" in output
        assert "Марія Коваль" in output

    def test_favorites_come_first(self, filled):
        filled("favorite Марія")
        output = filled("list contacts")
        assert output.index("Марія Коваль") < output.index("Іван Петренко")

    def test_alias_works(self, filled):
        assert "Іван Петренко" in filled("contacts")


class TestShowContact:
    def test_shows_every_field(self, filled):
        filled("set email Іван ivan@example.com")
        filled('set address Іван "Львів"')
        filled("set birthday Іван 07.03.1990")

        output = filled("show contact Іван")
        assert "+380671234567" in output
        assert "ivan@example.com" in output
        assert "Львів" in output
        assert "07.03.1990" in output

    def test_unknown_contact(self, filled):
        assert "не знайдено" in filled("show contact Ніхто")

    def test_ambiguous_reference_lists_candidates(self, run):
        run('add contact "Іван Петренко"')
        run('add contact "Іванна Шевченко"')
        assert "підходить кільком" in run("show contact ван")


class TestPhones:
    def test_add_phone(self, filled):
        assert "+380501112233" in filled("add phone Марія 0501112233")

    def test_add_duplicate_phone(self, filled):
        assert "вже записаний" in filled("add phone Іван 067 123 45 67")

    def test_remove_phone(self, filled):
        assert "прибрано" in filled("remove phone Іван 0671234567")

    def test_remove_missing_phone(self, filled):
        assert "немає номера" in filled("remove phone Марія 0501112233")

    def test_too_few_arguments_shows_usage(self, filled):
        assert "Використання: add phone" in filled("add phone Іван")


class TestSetFields:
    def test_email(self, filled):
        assert "ivan@example.com" in filled("set email Іван ivan@example.com")

    def test_invalid_email(self, filled):
        assert "не схоже на email" in filled("set email Іван не-пошта")

    def test_address_with_spaces(self, filled, ctx):
        filled('set address Іван "Львів, вул. Січових Стрільців 1"')
        assert ctx.contacts.all()[0].address == "Львів, вул. Січових Стрільців 1"

    def test_address_without_quotes_is_joined(self, filled, ctx):
        filled("set address Іван Львів вул Шевченка")
        assert ctx.contacts.all()[0].address == "Львів вул Шевченка"

    def test_birthday_is_echoed_in_the_input_format(self, filled):
        assert "07.03.1990" in filled("set birthday Іван 07.03.1990")

    def test_invalid_birthday(self, filled):
        assert "Помилка" in filled("set birthday Іван 32.13.1990")

    def test_iso_date_is_also_accepted(self, filled):
        # Формат зі сховища теж приймаємо на вводі — це не заважає, а рятує
        # користувача, який скопіював дату з JSON-файлу.
        assert "07.03.1990" in filled("set birthday Іван 1990-03-07")

    def test_future_birthday_rejected(self, filled):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
        assert "Помилка" in filled(f"set birthday Іван {tomorrow}")

    def test_clearing_a_field(self, filled):
        filled("set email Іван ivan@example.com")
        assert "очищено" in filled("set email Іван")


class TestRenameAndDelete:
    def test_rename(self, filled):
        assert "перейменовано" in filled('rename contact Іван "Іван Коваленко"')

    def test_rename_collision(self, filled):
        assert "уже існує" in filled('rename contact Іван "Марія Коваль"')

    def test_delete(self, filled, ctx):
        assert "видалено" in filled("delete contact Іван")
        assert len(ctx.contacts) == 1

    def test_delete_unknown(self, filled):
        assert "не знайдено" in filled("delete contact Ніхто")


class TestFavorites:
    def test_marking(self, filled):
        assert "додано до обраних" in filled("favorite Іван")

    def test_marking_twice(self, filled):
        filled("favorite Іван")
        assert "уже в обраних" in filled("favorite Іван")

    def test_unmarking(self, filled):
        filled("favorite Іван")
        assert "прибрано з обраних" in filled("unfavorite Іван")

    def test_empty_list_explains_what_to_do(self, filled):
        assert "favorite" in filled("list favorites")

    def test_only_favorites_are_listed(self, filled):
        filled("favorite Іван")
        output = filled("list favorites")
        assert "Іван Петренко" in output
        assert "Марія Коваль" not in output


class TestSearch:
    def test_finds_by_phone_in_another_format(self, filled):
        assert "Іван Петренко" in filled("find 067 123 45 67")

    def test_reports_nothing_found(self, filled):
        assert "нічого не знайдено" in filled("find zzzz")

    def test_alias_and_full_name_agree(self, filled):
        assert filled("find Коваль") == filled("find contacts Коваль")


class TestBirthdays:
    def test_default_window_is_a_week(self, registry):
        command, _ = registry.resolve("birthdays")
        assert "7" in command.signature

    def test_lists_upcoming(self, filled):
        soon = (date.today() + timedelta(days=3)).replace(year=1990).strftime("%d.%m.%Y")
        filled(f"set birthday Іван {soon}")
        assert "Іван Петренко" in filled("birthdays 10")

    def test_says_when_there_are_none(self, filled):
        assert "іменинників немає" in filled("birthdays")

    def test_rejects_non_numeric_argument(self, filled):
        assert "це не кількість днів" in filled("birthdays багато")

    def test_rejects_oversized_window(self, filled):
        assert "Помилка" in filled("birthdays 1000")


class TestHelpIntegration:
    def test_contacts_group_appears_in_help(self, run):
        assert "Контакти" in run("help")

    def test_every_contact_command_is_documented(self, registry, run):
        output = run("help")
        contact_commands = [c for c in registry.commands if c.group == "Контакти"]
        assert contact_commands
        assert all(command.name in output for command in contact_commands)

    def test_typo_in_a_contact_command_is_suggested(self, run):
        assert "add contact" in run("add contct Іван")


class TestNonUkrainianNames:
    """Імена не зобов'язані бути українськими — перевіряємо весь шлях."""

    def test_latin_name_round_trip(self, run, ctx):
        assert "створено" in run('add contact "John Smith" +1 202 555 0123')
        assert "John Smith" in run("show contact John")
        assert ctx.contacts.all()[0].phones == ["+12025550123"]

    def test_hex_looking_name_is_not_taken_for_an_identifier(self, run):
        run("add contact cafe")
        assert "cafe" in run("show contact cafe")

    def test_name_of_digits(self, run):
        run("add contact 12345")
        assert "12345" in run("show contact 12345")

    def test_mixed_scripts_sort_predictably(self, run):
        for name in ("Zoe", "Ярина", "Adam", "José"):
            run(f'add contact "{name}"')
        output = run("list contacts")
        order = [output.index(name) for name in ("Ярина", "Adam", "José", "Zoe")]
        assert order == sorted(order)

    def test_search_finds_a_latin_name(self, run):
        run('add contact "John Smith"')
        assert "John Smith" in run("find smith")

    def test_overlong_name_reports_the_limit(self, run):
        assert "максимум 100" in run(f'add contact "{"Я" * 101}"')


class TestBlockedEmailDomains:
    def test_set_email_reports_the_agreed_message(self, filled):
        assert "Агресорські домени йдуть лісом" in filled("set email Іван ivan@mail.ru")

    def test_email_is_not_stored(self, filled, ctx):
        filled("set email Іван ivan@mail.ru")
        assert ctx.contacts.all()[0].email is None

    def test_cyrillic_zone_is_blocked_too(self, filled):
        assert "йдуть лісом" in filled("set email Іван ivan@пошта.рф")

    def test_allowed_domain_still_works(self, filled):
        assert "ivan@ukr.net" in filled("set email Іван ivan@ukr.net")


class TestPortabilityCommands:
    """Експорт та імпорт через CLI."""

    def test_export_csv(self, filled, tmp_path):
        path = tmp_path / "out.csv"
        assert "Збережено 2 контакти" in filled(f'export contacts "{path}"')
        assert path.exists()

    def test_export_json(self, filled, tmp_path):
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')
        assert "Іван Петренко" in path.read_text(encoding="utf-8")

    def test_export_refuses_to_overwrite(self, filled, tmp_path):
        path = tmp_path / "out.csv"
        filled(f'export contacts "{path}"')
        assert "вже існує" in filled(f'export contacts "{path}"')

    def test_force_overwrites(self, filled, tmp_path):
        path = tmp_path / "out.csv"
        filled(f'export contacts "{path}"')
        assert "Збережено" in filled(f'export contacts "{path}" force')

    def test_export_of_an_empty_book(self, run, tmp_path):
        assert "порожня" in run(f'export contacts "{tmp_path / "out.csv"}"')

    def test_unknown_format(self, filled, tmp_path):
        assert "Підтримуються" in filled(f'export contacts "{tmp_path / "out.xml"}"')

    def test_missing_argument_shows_usage(self, run):
        assert "Використання: export contacts" in run("export contacts")

    def test_round_trip_through_the_cli(self, filled, run, tmp_path, ctx):
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')

        for contact in list(ctx.contacts):
            ctx.contacts.delete(contact.id)

        assert "додано 2" in run(f'import contacts "{path}"')
        assert len(ctx.contacts) == 2

    def test_import_reports_skipped_and_suggests_modes(self, filled, tmp_path):
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')
        output = filled(f'import contacts "{path}"')
        assert "пропущено 2" in output
        assert "replace" in output

    def test_import_with_replace_mode(self, filled, tmp_path):
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')
        assert "замінено 2" in filled(f'import contacts "{path}" replace')

    def test_import_with_merge_mode(self, filled, tmp_path):
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')
        assert "доповнено 2" in filled(f'import contacts "{path}" merge')

    def test_unknown_mode(self, filled, tmp_path):
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')
        assert "Невідомий режим" in filled(f'import contacts "{path}" казна-що')

    def test_import_missing_file(self, run, tmp_path):
        assert "не існує" in run(f'import contacts "{tmp_path / "немає.csv"}"')

    def test_import_reports_bad_rows_with_line_numbers(self, run, tmp_path):
        path = tmp_path / "in.csv"
        path.write_text("name,email\nОлена,olena@ukr.net\nАгресор,bad@mail.ru\n", encoding="utf-8")
        output = run(f'import contacts "{path}"')
        assert "додано 1" in output
        assert "рядок 3: Агресорські домени йдуть лісом" in output

    def test_path_with_spaces(self, filled, tmp_path):
        directory = tmp_path / "тека з пробілами"
        directory.mkdir()
        path = directory / "out.csv"
        assert "Збережено" in filled(f'export contacts "{path}"')

    def test_portability_group_in_help(self, run):
        assert "Імпорт та експорт" in run("help")


class TestPathAndModeParsing:
    """Розбір `<файл> [режим]`, коли шлях може містити пробіли."""

    def test_typo_in_the_mode_is_reported_as_such(self, filled, tmp_path):
        # А не як «файлу ... казна-що не існує».
        path = tmp_path / "out.json"
        filled(f'export contacts "{path}"')
        assert "Невідомий режим" in filled(f'import contacts "{path}" мerge')

    def test_unquoted_path_with_spaces_still_works(self, filled, tmp_path):
        directory = tmp_path / "тека з пробілами"
        directory.mkdir()
        path = directory / "out.json"
        filled(f'export contacts "{path}"')
        assert "пропущено" in filled(f"import contacts {path}")

    def test_unquoted_path_with_spaces_plus_mode(self, filled, tmp_path):
        directory = tmp_path / "тека з пробілами"
        directory.mkdir()
        path = directory / "out.json"
        filled(f'export contacts "{path}"')
        assert "замінено" in filled(f"import contacts {path} replace")

    def test_an_existing_path_wins_over_a_trailing_mode_word(self, filled, tmp_path):
        # Файл справді називається «contacts replace.json» — останнє слово
        # шляху не має тлумачитись як режим.
        weird = tmp_path / "contacts replace.json"
        filled(f'export contacts "{weird}"')
        assert weird.exists()
        assert "пропущено" in filled(f"import contacts {weird}")

    def test_missing_file_reports_the_full_path(self, run, tmp_path):
        missing = tmp_path / "немає.json"
        assert "немає.json" in run(f'import contacts "{missing}"')
