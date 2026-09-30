"""Команди задач перевіряємо через `dispatch`, як це робить REPL."""

from datetime import date, timedelta

import pytest

from personal_assistant.cli.app import dispatch
from personal_assistant.cli.bootstrap import build_registry
from personal_assistant.cli.registry import Registry

#: Дедлайн задачі з фікстури — завжди в майбутньому відносно дня запуску.
#: Раніше тут стояло `01.09.2026`: поки дата була попереду, тести проходили,
#: а щойно вона минула — задача законно ставала простроченою і `overdue`
#: переставав бути порожнім.
FUTURE_DUE = (date.today() + timedelta(days=30)).strftime("%d.%m.%Y")


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
    run('add task "Здати проєкт" "Фінальна версія"')
    run('add task "Купити молоко"')
    run(f"set due Здати {FUTURE_DUE}")
    return run


class TestAddTask:
    def test_creates_task_with_identifier(self, run):
        output = run('add task "Задача" "Опис"')
        assert "створено" in output
        assert "[" in output

    def test_description_without_quotes_is_joined(self, run, ctx):
        run("add task Задача це довгий опис")
        assert ctx.tasks.all()[0].description == "це довгий опис"

    def test_starts_as_new(self, run, ctx):
        run('add task "Задача"')
        assert ctx.tasks.all()[0].status.value == "new"

    def test_missing_title_shows_usage(self, run):
        assert "Використання: add task" in run("add task")


class TestStatusCommands:
    def test_start(self, filled):
        assert "in_progress" in filled("start Купити")

    def test_done(self, filled):
        assert "done" in filled("done Купити")

    def test_cancel(self, filled):
        assert "cancelled" in filled("cancel Купити")

    def test_set_status_with_canonical_value(self, filled):
        assert "in_progress" in filled("set status Купити in_progress")

    def test_set_status_with_ukrainian_synonym(self, filled):
        assert "in_progress" in filled('set status Купити "в роботі"')

    def test_repeated_status_is_reported(self, filled):
        filled("done Купити")
        assert "уже має статус" in filled("done Купити")

    def test_unknown_status_lists_the_allowed_ones(self, filled):
        output = filled("set status Купити майже")
        assert "cancelled" in output

    def test_shown_status_keeps_the_canonical_value(self, filled):
        # У таблиці — українська назва, але канонічне значення має бути видно.
        assert "in_progress" in filled("start Купити")
        assert "in_progress" in filled("show task Купити")


class TestListing:
    def test_empty_gives_a_hint(self, run):
        assert "add task" in run("list tasks")

    def test_alias(self, filled):
        assert "Здати проєкт" in filled("tasks")

    def test_summary_line_is_shown(self, filled):
        assert "Усього 2 задачі" in filled("list tasks")

    def test_filtering_by_status(self, filled):
        filled("done Купити")
        output = filled("list tasks done")
        assert "Купити молоко" in output
        assert "Здати проєкт" not in output

    def test_filtered_listing_has_no_global_summary(self, filled):
        # Підсумок про всі задачі під вибіркою читався б як опис вибірки.
        assert "Усього" not in filled("list tasks new")

    def test_filtering_with_no_matches(self, filled):
        assert "немає" in filled("list tasks cancelled")

    def test_invalid_status_filter(self, filled):
        assert "Невідомий статус" in filled("list tasks казна-що")

    def test_open_tasks_come_before_closed(self, filled):
        filled("done Здати")
        output = filled("list tasks")
        assert output.index("Купити молоко") < output.index("Здати проєкт")


class TestDueDates:
    def test_set_due(self, filled):
        assert "01.09.2026" in filled("set due Купити 01.09.2026")

    def test_overdue_is_flagged_when_set(self, filled):
        assert "прострочено" in filled("set due Купити 01.01.2020")

    def test_clearing(self, filled):
        assert "очищено" in filled("set due Здати")

    def test_invalid_date(self, filled):
        assert "Помилка" in filled("set due Купити колись")

    def test_overdue_command_lists_them(self, filled):
        past = (date.today() - timedelta(days=5)).strftime("%d.%m.%Y")
        filled(f"set due Купити {past}")
        assert "Купити молоко" in filled("overdue")

    def test_overdue_command_when_there_are_none(self, filled):
        assert "Прострочених задач немає" in filled("overdue")

    def test_closed_tasks_are_not_overdue(self, filled):
        past = (date.today() - timedelta(days=5)).strftime("%d.%m.%Y")
        filled(f"set due Купити {past}")
        filled("done Купити")
        assert "немає" in filled("overdue")


class TestShowEditDelete:
    def test_show_task(self, filled):
        output = filled("show task Здати")
        assert "Фінальна версія" in output
        assert FUTURE_DUE in output

    def test_show_unknown(self, filled):
        assert "не знайдено" in filled("show task Немає")

    def test_edit_description(self, filled, ctx):
        filled('edit task Купити "2 літри"')
        task = next(t for t in ctx.tasks if t.title == "Купити молоко")
        assert task.description == "2 літри"

    def test_rename(self, filled):
        assert "перейменовано" in filled('rename task Купити "Купити кефір"')

    def test_delete(self, filled, ctx):
        assert "видалено" in filled("delete task Купити")
        assert len(ctx.tasks) == 1

    def test_find(self, filled):
        assert "Здати проєкт" in filled("find tasks фінальна")

    def test_find_nothing(self, filled):
        assert "нічого не знайдено" in filled("find tasks zzzz")


class TestCommandCollisions:
    """Команди задач не мають перехоплювати команди контактів і нотаток."""

    def test_set_status_and_set_email_coexist(self, run, filled):
        run('add contact "Іван"')
        assert "ivan@ukr.net" in run("set email Іван ivan@ukr.net")
        assert "in_progress" in run("start Купити")

    def test_set_due_and_set_birthday_coexist(self, run, filled):
        run('add contact "Іван"')
        assert "07.03.1990" in run("set birthday Іван 07.03.1990")
        assert "01.09.2026" in run("set due Купити 01.09.2026")

    def test_add_task_does_not_shadow_add_tag(self, run, filled):
        run('add note "Нотатка"')
        assert "#робота" in run("add tag Нотатка робота")

    def test_all_three_groups_in_help(self, run):
        output = run("help")
        assert "Контакти" in output
        assert "Нотатки" in output
        assert "Задачі" in output

    def test_find_variants_are_distinct(self, run):
        run('add contact "Іван Петренко"')
        run('add note "Нотатка про Івана"')
        run('add task "Задача про Івана"')

        assert "Іван Петренко" in run("find Петренко")
        assert "Нотатка про Івана" in run("find notes Івана")
        assert "Задача про Івана" in run("find tasks Івана")
