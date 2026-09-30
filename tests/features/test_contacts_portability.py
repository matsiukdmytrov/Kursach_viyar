"""Імпорт та експорт контактів."""

from datetime import date
from pathlib import Path

import pytest

from personal_assistant.core.errors import NotFoundError, StorageError, ValidationError
from personal_assistant.core.repository import Repository
from personal_assistant.core.storage import JsonStore
from personal_assistant.features.contacts import portability
from personal_assistant.features.contacts.models import Contact
from personal_assistant.features.contacts.portability import ImportMode


@pytest.fixture
def repo(tmp_path: Path) -> Repository[Contact]:
    return Repository(JsonStore(tmp_path / "contacts.json", Contact))


@pytest.fixture
def contacts() -> list[Contact]:
    return [
        Contact(
            name="Іван Петренко",
            phones=["0671234567", "0501112233"],
            email="ivan@ukr.net",
            address="Львів, вул. Січових Стрільців 1",
            birthday="07.03.1990",
            favorite=True,
        ),
        Contact(name="Марія Коваль"),
    ]


class TestExport:
    def test_json_contains_every_field(self, contacts, tmp_path):
        path = tmp_path / "out.json"
        assert portability.export_contacts(contacts, path) == 2

        text = path.read_text(encoding="utf-8")
        assert "Іван Петренко" in text
        assert "+380671234567;+380501112233" in text
        assert "07.03.1990" in text

    def test_csv_has_a_bom_for_excel(self, contacts, tmp_path):
        path = tmp_path / "out.csv"
        portability.export_contacts(contacts, path)
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_csv_uses_crlf(self, contacts, tmp_path):
        path = tmp_path / "out.csv"
        portability.export_contacts(contacts, path)
        assert b"\r\n" in path.read_bytes()

    def test_csv_quotes_fields_containing_the_delimiter(self, contacts, tmp_path):
        path = tmp_path / "out.csv"
        portability.export_contacts(contacts, path)
        assert '"Львів, вул. Січових Стрільців 1"' in path.read_text(encoding="utf-8-sig")

    def test_header_order_is_fixed(self, contacts, tmp_path):
        path = tmp_path / "out.csv"
        portability.export_contacts(contacts, path)
        first_line = path.read_text(encoding="utf-8-sig").splitlines()[0]
        assert first_line == ",".join(portability.EXPORT_FIELDS)

    def test_existing_file_is_not_overwritten(self, contacts, tmp_path):
        path = tmp_path / "out.csv"
        path.write_text("не чіпати", encoding="utf-8")

        with pytest.raises(ValidationError, match="вже існує"):
            portability.export_contacts(contacts, path)
        assert path.read_text(encoding="utf-8") == "не чіпати"

    def test_force_allows_overwriting(self, contacts, tmp_path):
        path = tmp_path / "out.csv"
        path.write_text("старе", encoding="utf-8")
        portability.export_contacts(contacts, path, force=True)
        assert "Іван Петренко" in path.read_text(encoding="utf-8-sig")

    def test_unknown_extension(self, contacts, tmp_path):
        with pytest.raises(ValidationError, match=r"\.json"):
            portability.export_contacts(contacts, tmp_path / "out.xml")

    def test_missing_directories_are_created(self, contacts, tmp_path):
        path = tmp_path / "нова" / "тека" / "out.json"
        portability.export_contacts(contacts, path)
        assert path.exists()

    def test_empty_optional_fields_become_empty_strings(self, contacts, tmp_path):
        row = portability.to_row(contacts[1])
        assert row["email"] == ""
        assert row["birthday"] == ""
        assert row["favorite"] == "ні"


class TestReadRows:
    def test_missing_file(self, tmp_path):
        with pytest.raises(NotFoundError):
            portability.read_rows(tmp_path / "немає.csv")

    def test_directory_instead_of_file(self, tmp_path):
        with pytest.raises(ValidationError, match="тека"):
            portability.read_rows(tmp_path)

    def test_unknown_extension(self, tmp_path):
        path = tmp_path / "data.xml"
        path.write_text("<x/>", encoding="utf-8")
        with pytest.raises(ValidationError):
            portability.read_rows(path)

    def test_broken_json(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text("{зламано", encoding="utf-8")
        with pytest.raises(StorageError):
            portability.read_rows(path)

    def test_json_must_be_a_list(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text('{"name": "Іван"}', encoding="utf-8")
        with pytest.raises(ValidationError, match="список"):
            portability.read_rows(path)

    def test_semicolon_delimiter_is_detected(self, tmp_path):
        # Український Excel зберігає CSV саме так.
        path = tmp_path / "excel.csv"
        path.write_text("name;phones;email\nІван;0671234567;ivan@ukr.net\n", encoding="utf-8-sig")
        rows = portability.read_rows(path)
        assert rows[0]["name"] == "Іван"
        assert rows[0]["phones"] == "0671234567"

    def test_comma_delimiter_still_works(self, tmp_path):
        path = tmp_path / "plain.csv"
        path.write_text("name,phones\nІван,0671234567\n", encoding="utf-8")
        assert portability.read_rows(path)[0]["phones"] == "0671234567"

    def test_csv_without_bom(self, tmp_path):
        path = tmp_path / "plain.csv"
        path.write_text("name\nІван\n", encoding="utf-8")
        assert portability.read_rows(path)[0]["name"] == "Іван"


class TestImport:
    def test_adds_new_contacts(self, repo):
        rows = [{"name": "Іван", "phones": "0671234567"}]
        result = portability.import_contacts(repo, rows)
        assert result.added == 1
        assert repo.all()[0].phones == ["+380671234567"]

    def test_phones_split_on_semicolon(self, repo):
        portability.import_contacts(repo, [{"name": "Іван", "phones": "0671234567;0501112233"}])
        assert len(repo.all()[0].phones) == 2

    def test_phones_may_arrive_as_a_json_list(self, repo):
        portability.import_contacts(repo, [{"name": "Іван", "phones": ["0671234567"]}])
        assert repo.all()[0].phones == ["+380671234567"]

    def test_birthday_in_both_formats(self, repo):
        portability.import_contacts(
            repo,
            [
                {"name": "Іван", "birthday": "07.03.1990"},
                {"name": "Марія", "birthday": "1990-03-07"},
            ],
        )
        assert all(c.birthday == date(1990, 3, 7) for c in repo.all())

    @pytest.mark.parametrize("value", ["так", "yes", "true", "1", "+", "Так"])
    def test_favourite_accepts_many_spellings(self, repo, value):
        portability.import_contacts(repo, [{"name": "Іван", "favorite": value}])
        assert repo.all()[0].favorite is True

    @pytest.mark.parametrize("value", ["ні", "no", "", None, "хтозна"])
    def test_anything_else_is_not_favourite(self, repo, value):
        portability.import_contacts(repo, [{"name": "Іван", "favorite": value}])
        assert repo.all()[0].favorite is False


class TestImportErrors:
    def test_a_bad_row_does_not_stop_the_import(self, repo):
        rows = [
            {"name": "Іван", "phones": "0671234567"},
            {"name": "Кривий", "phones": "не-номер"},
            {"name": "Марія"},
        ]
        result = portability.import_contacts(repo, rows)
        assert result.added == 2
        assert len(result.errors) == 1

    def test_row_numbers_match_the_spreadsheet(self, repo):
        # Заголовок — рядок 1, тож перший запис даних це рядок 2.
        rows = [{"name": "Іван"}, {"name": ""}]
        ((row, _),) = portability.import_contacts(repo, rows).errors
        assert row == 3

    def test_blank_name_is_reported(self, repo):
        result = portability.import_contacts(repo, [{"name": "   "}])
        assert "порожнє ім'я" in result.errors[0][1]

    def test_blocked_domain_is_reported_on_import(self, repo):
        result = portability.import_contacts(repo, [{"name": "Іван", "email": "ivan@mail.ru"}])
        assert result.errors[0][1] == "Агресорські домени йдуть лісом"
        assert len(repo) == 0

    def test_invalid_email_is_reported(self, repo):
        result = portability.import_contacts(repo, [{"name": "Іван", "email": "не-пошта"}])
        assert "email" in result.errors[0][1]


class TestImportModes:
    @pytest.fixture
    def existing(self, repo):
        repo.add(Contact(name="Іван Петренко", phones=["0501112233"], email="old@ukr.net"))
        return repo

    @pytest.fixture
    def incoming(self):
        return [
            {
                "name": "Іван Петренко",
                "phones": "0671234567",
                "email": "new@ukr.net",
                "address": "Львів",
            }
        ]

    def test_skip_changes_nothing(self, existing, incoming):
        result = portability.import_contacts(existing, incoming, ImportMode.SKIP)
        contact = existing.all()[0]
        assert result.skipped == 1
        assert contact.email == "old@ukr.net"
        assert contact.phones == ["+380501112233"]

    def test_replace_overwrites_every_field(self, existing, incoming):
        result = portability.import_contacts(existing, incoming, ImportMode.REPLACE)
        contact = existing.all()[0]
        assert result.replaced == 1
        assert contact.email == "new@ukr.net"
        assert contact.phones == ["+380671234567"]
        assert contact.address == "Львів"

    def test_replace_keeps_the_identifier(self, existing, incoming):
        original_id = existing.all()[0].id
        portability.import_contacts(existing, incoming, ImportMode.REPLACE)
        assert existing.all()[0].id == original_id

    def test_merge_unions_phones_and_fills_gaps(self, existing, incoming):
        result = portability.import_contacts(existing, incoming, ImportMode.MERGE)
        contact = existing.all()[0]
        assert result.merged == 1
        assert contact.phones == ["+380501112233", "+380671234567"]
        assert contact.email == "old@ukr.net"  # наявне не затирається
        assert contact.address == "Львів"  # порожнє заповнюється

    def test_merge_does_not_duplicate_the_same_phone(self, existing):
        portability.import_contacts(
            existing, [{"name": "Іван Петренко", "phones": "050 111 22 33"}], ImportMode.MERGE
        )
        assert existing.all()[0].phones == ["+380501112233"]

    def test_matching_by_name_ignores_case(self, existing, incoming):
        incoming[0]["name"] = "іван петренко"
        result = portability.import_contacts(existing, incoming, ImportMode.SKIP)
        assert result.skipped == 1

    def test_never_creates_a_duplicate_name(self, existing, incoming):
        for mode in ImportMode:
            portability.import_contacts(existing, incoming, mode)
        assert len(existing) == 1


class TestModeParsing:
    @pytest.mark.parametrize("value", ["skip", "SKIP", " replace ", "merge"])
    def test_accepted(self, value):
        assert ImportMode.parse(value) in set(ImportMode)

    def test_unknown_lists_the_options(self):
        with pytest.raises(ValidationError, match="merge"):
            ImportMode.parse("казна-що")


class TestRoundTrip:
    @pytest.mark.parametrize("suffix", [".json", ".csv"])
    def test_export_then_import_reproduces_the_book(self, contacts, repo, tmp_path, suffix):
        path = tmp_path / f"out{suffix}"
        portability.export_contacts(contacts, path)
        portability.import_contacts(repo, portability.read_rows(path))

        restored = {contact.name: contact for contact in repo.all()}
        assert set(restored) == {"Іван Петренко", "Марія Коваль"}

        ivan = restored["Іван Петренко"]
        assert ivan.phones == ["+380671234567", "+380501112233"]
        assert ivan.email == "ivan@ukr.net"
        assert ivan.address == "Львів, вул. Січових Стрільців 1"
        assert ivan.birthday == date(1990, 3, 7)
        assert ivan.favorite is True

    @pytest.mark.parametrize("suffix", [".json", ".csv"])
    def test_contacts_without_optional_fields_survive(self, contacts, repo, tmp_path, suffix):
        path = tmp_path / f"out{suffix}"
        portability.export_contacts(contacts, path)
        portability.import_contacts(repo, portability.read_rows(path))

        maria = next(c for c in repo.all() if c.name == "Марія Коваль")
        assert maria.phones == []
        assert maria.email is None
        assert maria.birthday is None
        assert maria.favorite is False
