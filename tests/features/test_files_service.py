"""Тести аналізу тек.

Головна перевірка тут — що фіча нічого не змінює на диску: після кожного
плану склад теки має лишатись байт у байт таким самим.
"""

from pathlib import Path

import pytest

from personal_assistant.core.errors import NotFoundError, ValidationError
from personal_assistant.features.files import service


def snapshot(root: Path) -> set[str]:
    """Повний перелік шляхів усередині теки."""
    return {str(path.relative_to(root)) for path in root.rglob("*")}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "тека" / "вкладена").mkdir(parents=True)
    (root / "images").mkdir()

    (root / "Мій звіт (1).PDF").write_text("однаковий", encoding="utf-8")
    (root / "kopiia.pdf").write_text("однаковий", encoding="utf-8")
    (root / "тека" / "дубль.pdf").write_text("однаковий", encoding="utf-8")
    (root / "Ґудзик.JPEG").write_text("фото", encoding="utf-8")
    (root / "Відео.MP4").write_text("відео", encoding="utf-8")
    (root / "архів.tar.gz").write_text("архів", encoding="utf-8")
    (root / "no_extension").write_text("щось", encoding="utf-8")
    (root / "already_normal.txt").write_text("норм", encoding="utf-8")
    (root / ".hidden").write_text("приховане", encoding="utf-8")
    (root / "images" / "existing.jpg").write_text("розкладене", encoding="utf-8")
    (root / "тека" / "вкладена" / "Пісня.mp3").write_text("пісня", encoding="utf-8")
    return root


class TestResolveDirectory:
    def test_returns_absolute_path(self, tree):
        assert service.resolve_directory(str(tree)).is_absolute()

    def test_missing_directory(self, tmp_path):
        with pytest.raises(NotFoundError):
            service.resolve_directory(str(tmp_path / "немає"))

    def test_file_instead_of_directory(self, tree):
        with pytest.raises(ValidationError, match="файл"):
            service.resolve_directory(str(tree / "kopiia.pdf"))

    def test_blank_input(self):
        with pytest.raises(ValidationError):
            service.resolve_directory("   ")


class TestScan:
    def test_finds_files_recursively(self, tree):
        names = {path.name for path in service.scan(tree).files}
        assert "Пісня.mp3" in names
        assert "дубль.pdf" in names

    def test_hidden_files_are_skipped_and_counted(self, tree):
        result = service.scan(tree)
        assert all(not path.name.startswith(".") for path in result.files)
        assert result.hidden_count == 1

    def test_already_sorted_directories_at_root_are_skipped(self, tree):
        result = service.scan(tree)
        assert "existing.jpg" not in {path.name for path in result.files}
        assert result.skipped_sorted == 1

    def test_a_category_named_directory_deeper_down_is_not_skipped(self, tree):
        nested = tree / "тека" / "images"
        nested.mkdir()
        (nested / "deep.png").write_text("x", encoding="utf-8")
        assert "deep.png" in {path.name for path in service.scan(tree).files}

    def test_symlinked_directories_are_not_followed(self, tree):
        link = tree / "loop"
        try:
            link.symlink_to(tree, target_is_directory=True)
        except OSError:  # pragma: no cover - системи без символьних посилань
            pytest.skip("символьні посилання недоступні")
        assert len(service.scan(tree).files) == len(service.scan(tree).files)
        assert all("loop" not in str(path) for path in service.scan(tree).files)

    def test_files_are_in_ukrainian_alphabetical_order(self, tree):
        names = [path.name for path in service.scan(tree).files if path.parent == tree]
        assert names.index("Ґудзик.JPEG") < names.index("Мій звіт (1).PDF")


class TestCategoryOf:
    @pytest.mark.parametrize(
        ("filename", "category"),
        [
            ("photo.jpg", "images"),
            ("clip.MP4", "videos"),
            ("report.pdf", "documents"),
            ("archive.zip", "archives"),
            ("архів.tar.gz", "archives"),
            ("song.mp3", "audio"),
            ("no_extension", "others"),
            ("script.xyz", "others"),
        ],
    )
    def test_cases(self, filename, category):
        assert service.category_of(filename) == category

    def test_all_categories_from_the_spec_exist(self):
        assert set(service.iter_categories()) == {
            "images",
            "videos",
            "documents",
            "archives",
            "audio",
            "others",
        }


class TestPlanSort:
    def test_nothing_is_moved(self, tree):
        before = snapshot(tree)
        service.plan_sort(tree)
        assert snapshot(tree) == before

    def test_every_scanned_file_gets_a_move(self, tree):
        moves, scanned = service.plan_sort(tree)
        assert len(moves) == len(scanned.files)

    def test_targets_live_under_their_category(self, tree):
        moves, _ = service.plan_sort(tree)
        assert all(move.target.parent == tree / move.category for move in moves)

    def test_renamed_flag_is_accurate(self, tree):
        moves, _ = service.plan_sort(tree)
        by_name = {move.source.name: move for move in moves}
        assert by_name["Ґудзик.JPEG"].renamed is True
        assert by_name["already_normal.txt"].renamed is False

    def test_collisions_get_a_numeric_suffix(self, tmp_path):
        root = tmp_path / "data"
        (root / "a").mkdir(parents=True)
        (root / "b").mkdir()
        (root / "a" / "звіт.txt").write_text("1", encoding="utf-8")
        (root / "b" / "звіт.txt").write_text("2", encoding="utf-8")

        moves, _ = service.plan_sort(root)
        names = sorted(move.target.name for move in moves)
        assert names == ["zvit.txt", "zvit_2.txt"]
        assert sum(move.collision for move in moves) == 1

    def test_case_only_differences_still_collide(self, tmp_path):
        # На macOS і Windows `Fail.txt` та `fail.txt` — один файл.
        root = tmp_path / "data"
        (root / "a").mkdir(parents=True)
        (root / "b").mkdir()
        (root / "a" / "Файл.txt").write_text("1", encoding="utf-8")
        (root / "b" / "файл.txt").write_text("2", encoding="utf-8")

        moves, _ = service.plan_sort(root)
        assert sum(move.collision for move in moves) == 1

    def test_existing_file_in_the_target_directory_is_respected(self, tmp_path):
        root = tmp_path / "data"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "zvit.txt").write_text("вже там", encoding="utf-8")
        (root / "звіт.txt").write_text("новий", encoding="utf-8")

        moves, _ = service.plan_sort(root)
        assert moves[0].target.name == "zvit_2.txt"
        assert moves[0].collision is True

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        moves, _ = service.plan_sort(empty)
        assert moves == []


class TestPlanNormalize:
    def test_nothing_is_renamed(self, tree):
        before = snapshot(tree)
        service.plan_normalize(tree)
        assert snapshot(tree) == before

    def test_already_normal_names_are_not_listed(self, tree):
        renames, _ = service.plan_normalize(tree)
        listed = {rename.source.name for rename in renames}
        assert "already_normal.txt" not in listed
        assert "no_extension" not in listed

    def test_a_file_is_not_treated_as_its_own_collision(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "normal.txt").write_text("x", encoding="utf-8")
        assert service.plan_normalize(root)[0] == []

    def test_renames_stay_in_the_same_directory(self, tree):
        renames, _ = service.plan_normalize(tree)
        assert all(r.source.parent == r.target.parent for r in renames)

    def test_same_directory_collision(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "звіт.txt").write_text("1", encoding="utf-8")
        (root / "звіт!.txt").write_text("2", encoding="utf-8")

        renames, _ = service.plan_normalize(root)
        assert sorted(r.target.name for r in renames) == ["zvit.txt", "zvit_2.txt"]

    def test_names_in_different_directories_do_not_collide(self, tmp_path):
        root = tmp_path / "data"
        (root / "a").mkdir(parents=True)
        (root / "b").mkdir()
        (root / "a" / "звіт.txt").write_text("1", encoding="utf-8")
        (root / "b" / "звіт.txt").write_text("2", encoding="utf-8")

        renames, _ = service.plan_normalize(root)
        assert all(not rename.collision for rename in renames)


class TestFindDuplicates:
    def test_nothing_is_deleted(self, tree):
        before = snapshot(tree)
        service.find_duplicates(tree)
        assert snapshot(tree) == before

    def test_identical_files_are_grouped(self, tree):
        groups, _ = service.find_duplicates(tree)
        assert len(groups) == 1
        assert {path.name for path in groups[0].files} == {
            "Мій звіт (1).PDF",
            "kopiia.pdf",
            "дубль.pdf",
        }

    def test_wasted_space_counts_extra_copies_only(self, tree):
        (group,) = service.find_duplicates(tree)[0]
        assert group.wasted_bytes == group.size * 2

    def test_same_size_but_different_content_is_not_a_duplicate(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "a.txt").write_text("aaaa", encoding="utf-8")
        (root / "b.txt").write_text("bbbb", encoding="utf-8")
        assert service.find_duplicates(root)[0] == []

    def test_unique_files_give_no_groups(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "a.txt").write_text("a", encoding="utf-8")
        (root / "b.txt").write_text("bb", encoding="utf-8")
        assert service.find_duplicates(root)[0] == []

    def test_empty_files_are_duplicates_of_each_other(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "a.txt").touch()
        (root / "b.txt").touch()
        groups, _ = service.find_duplicates(root)
        assert len(groups) == 1
        assert groups[0].wasted_bytes == 0

    def test_groups_are_sorted_by_wasted_space(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        for name in ("small1.txt", "small2.txt"):
            (root / name).write_text("x", encoding="utf-8")
        for name in ("big1.txt", "big2.txt"):
            (root / name).write_text("x" * 500, encoding="utf-8")

        groups, _ = service.find_duplicates(root)
        assert groups[0].wasted_bytes > groups[1].wasted_bytes

    def test_large_file_is_hashed_in_chunks(self, tmp_path):
        # Файл більший за розмір буфера має хешуватись правильно.
        root = tmp_path / "data"
        root.mkdir()
        payload = b"x" * (service.HASH_CHUNK_SIZE * 2 + 17)
        (root / "a.bin").write_bytes(payload)
        (root / "b.bin").write_bytes(payload)
        assert len(service.find_duplicates(root)[0]) == 1
