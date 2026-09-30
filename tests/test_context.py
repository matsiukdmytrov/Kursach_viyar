from datetime import date

import pytest

from personal_assistant.context import AppContext
from personal_assistant.core.errors import StorageError
from personal_assistant.features.contacts.models import Contact
from personal_assistant.features.notes.models import Note
from personal_assistant.features.tasks.models import Task, TaskStatus


class TestAppContext:
    def test_starts_empty_when_no_data_files(self, ctx):
        assert len(ctx.contacts) == 0
        assert len(ctx.notes) == 0
        assert len(ctx.tasks) == 0

    def test_save_all_writes_every_collection(self, ctx, settings):
        ctx.contacts.add(Contact(name="Іван"))
        ctx.notes.add(Note(title="Нотатка"))
        ctx.tasks.add(Task(title="Задача"))
        ctx.save_all()

        assert settings.contacts_file.exists()
        assert settings.notes_file.exists()
        assert settings.tasks_file.exists()

    def test_reloads_saved_state(self, ctx, settings):
        ctx.contacts.add(Contact(name="Іван", phones=["0671234567"]))
        ctx.save_all()

        reloaded = AppContext.create(settings)
        (contact,) = reloaded.contacts.all()
        assert contact.name == "Іван"
        assert contact.phones == ["+380671234567"]


class TestRoundTrip:
    """Кожне поле має пережити запис і читання.

    Ці тести з'явились після того, як застосунок падав при старті: дати
    зберігались в ISO, а валідатор чекав DD.MM.YYYY.
    """

    def test_contact_with_every_field(self, ctx, settings):
        ctx.contacts.add(
            Contact(
                name="Іван Петренко",
                phones=["0671234567", "+380501112233"],
                email="ivan@example.com",
                address="Львів",
                birthday="07.03.1990",
                favorite=True,
            )
        )
        ctx.save_all()

        (restored,) = AppContext.create(settings).contacts.all()
        assert restored.name == "Іван Петренко"
        assert restored.phones == ["+380671234567", "+380501112233"]
        assert restored.email == "ivan@example.com"
        assert restored.address == "Львів"
        assert restored.birthday == date(1990, 3, 7)
        assert restored.favorite is True

    def test_note_with_tags(self, ctx, settings):
        ctx.notes.add(Note(title="Зустріч", text="Обговорити реліз", tags=["#Work", "Дім"]))
        ctx.save_all()

        (restored,) = AppContext.create(settings).notes.all()
        assert restored.title == "Зустріч"
        assert restored.tags == ["work", "дім"]

    def test_task_with_status_and_due_date(self, ctx, settings):
        ctx.tasks.add(Task(title="Купити хліб", status="in_progress", due_date="01.09.2026"))
        ctx.save_all()

        (restored,) = AppContext.create(settings).tasks.all()
        assert restored.status is TaskStatus.IN_PROGRESS
        assert restored.due_date == date(2026, 9, 1)

    def test_identifiers_and_timestamps_survive(self, ctx, settings):
        contact = ctx.contacts.add(Contact(name="Іван", birthday="07.03.1990"))
        ctx.save_all()

        (restored,) = AppContext.create(settings).contacts.all()
        assert restored.id == contact.id
        assert restored.created_at == contact.created_at


class TestCorruptedData:
    def test_broken_file_gives_a_readable_error(self, ctx, settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.contacts_file.write_text('[{"name": 42}]', encoding="utf-8")

        with pytest.raises(StorageError, match="пошкоджено"):
            AppContext.create(settings)

    def test_unparseable_date_is_reported_as_storage_error(self, ctx, settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.contacts_file.write_text(
            '[{"name": "Іван", "birthday": "не-дата"}]', encoding="utf-8"
        )

        with pytest.raises(StorageError, match="не проходить перевірку"):
            AppContext.create(settings)

    def test_a_valid_file_with_a_now_forbidden_record_says_why(self, ctx, settings):
        # Файл цілий — суворішими стали правила. Повідомлення має це відрізняти.
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.contacts_file.write_text(
            '[{"name": "Іван", "email": "ivan@mail.ru"}]', encoding="utf-8"
        )

        with pytest.raises(StorageError, match="Агресорські домени") as exc_info:
            AppContext.create(settings)
        assert "пошкоджено" not in exc_info.value.message
