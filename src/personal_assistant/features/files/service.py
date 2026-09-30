"""Аналіз теки: сортування за категоріями, дублікати, нормалізація імен.

Ця фіча нічого не змінює на диску. Кожна операція будує **план** і повертає
його — застосування буде окремим кроком, і рішення «застосувати» має
ухвалювати людина, яка спершу побачила, що саме станеться.

Через це в модулі немає жодного виклику, який пише, перейменовує чи видаляє.
Ця межа навмисна: доки її дотримано, помилка в логіці не може зіпсувати
чужу теку.
"""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from personal_assistant.core.errors import NotFoundError, ValidationError
from personal_assistant.core.text import collation_key
from personal_assistant.features.files.naming import normalize_filename, split_name

#: Категорії з технічного завдання. Порядок визначає порядок у звіті.
CATEGORY_MAP: dict[str, frozenset[str]] = {
    "images": frozenset({"jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "heic", "tiff", "ico"}),
    "videos": frozenset({"avi", "mp4", "mov", "mkv", "wmv", "flv", "webm", "m4v", "mpg", "mpeg"}),
    "documents": frozenset(
        {
            "doc",
            "docx",
            "txt",
            "pdf",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "odt",
            "ods",
            "rtf",
            "csv",
            "md",
        }
    ),
    "archives": frozenset({"zip", "gz", "tar", "rar", "7z", "bz2", "xz", "zst", "iso"}),
    "audio": frozenset({"mp3", "ogg", "wav", "amr", "flac", "aac", "m4a", "wma", "opus"}),
}

#: Куди потрапляє все, що не підпало під жодну категорію.
OTHER_CATEGORY = "others"

#: Усі теки, які створює сортування.
CATEGORY_DIRECTORIES = frozenset({*CATEGORY_MAP, OTHER_CATEGORY})

#: Читаємо файл частинами — інакше великий файл цілком опиняється в пам'яті.
HASH_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class PlannedMove:
    """Один файл і те, куди він потрапив би при сортуванні."""

    source: Path
    target: Path
    category: str
    renamed: bool
    collision: bool


@dataclass(frozen=True, slots=True)
class PlannedRename:
    """Файл, ім'я якого змінилося б при нормалізації."""

    source: Path
    target: Path
    collision: bool


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Файли з однаковим вмістом."""

    digest: str
    size: int
    files: list[Path]

    @property
    def wasted_bytes(self) -> int:
        """Скільки місця звільнилось би, якби лишити одну копію."""
        return self.size * (len(self.files) - 1)


@dataclass(slots=True)
class ScanResult:
    """Що знайшлось у теці та що довелося пропустити."""

    root: Path
    files: list[Path] = field(default_factory=list)
    unreadable: list[Path] = field(default_factory=list)
    hidden_count: int = 0
    skipped_sorted: int = 0


# ------------------------------------------------------------------- вхідні дані


def resolve_directory(raw: str) -> Path:
    """Перетворює введений шлях на існуючу теку."""
    text = raw.strip()
    if not text:
        raise ValidationError("Не вказано теку.")

    path = Path(text).expanduser()
    if not path.exists():
        raise NotFoundError(f"Теки '{text}' не існує.")
    if not path.is_dir():
        raise ValidationError(f"'{text}' — це файл, а не тека.")

    return path.resolve()


def scan(root: Path) -> ScanResult:
    """Збирає файли теки рекурсивно.

    Пропускаємо три речі: приховані файли (їх сортувати ніхто не просив),
    символьні посилання на теки (інакше цикл посилань зациклює обхід) і теки
    категорій у корені — це результат попереднього сортування, і заходити в
    них означає перекладати вже розкладене.
    """
    result = ScanResult(root=root)
    _walk(root, root, result)
    # Та сама українська колація, що й у списках контактів: інакше `Ґудзик`
    # опиняється в кінці переліку, бо `Ґ` лежить поза основним блоком Unicode.
    result.files.sort(key=lambda path: collation_key(str(path)))
    return result


def _walk(directory: Path, root: Path, result: ScanResult) -> None:
    try:
        entries = sorted(directory.iterdir(), key=lambda path: collation_key(path.name))
    except OSError:
        result.unreadable.append(directory)
        return

    for entry in entries:
        if entry.name.startswith("."):
            result.hidden_count += 1
            continue

        if entry.is_dir():
            if entry.is_symlink():
                continue
            if directory == root and entry.name in CATEGORY_DIRECTORIES:
                result.skipped_sorted += 1
                continue
            _walk(entry, root, result)
        elif entry.is_file():
            result.files.append(entry)


# --------------------------------------------------------------------- категорії


def category_of(filename: str) -> str:
    """Категорія файлу за його розширенням."""
    _, suffix = split_name(filename)
    extension = suffix.lstrip(".").lower()
    # Для `.tar.gz` беремо останню частину: `gz` вже є в архівах.
    extension = extension.rsplit(".", maxsplit=1)[-1]

    for category, extensions in CATEGORY_MAP.items():
        if extension in extensions:
            return category
    return OTHER_CATEGORY


# ------------------------------------------------------------------------ плани


def plan_sort(root: Path) -> tuple[list[PlannedMove], ScanResult]:
    """Складає план сортування, нічого не переміщуючи."""
    result = scan(root)
    claimed: set[tuple[str, str]] = set()
    moves: list[PlannedMove] = []

    for source in result.files:
        category = category_of(source.name)
        directory = root / category
        new_name, collision = _claim(directory, normalize_filename(source.name), claimed)

        moves.append(
            PlannedMove(
                source=source,
                target=directory / new_name,
                category=category,
                renamed=new_name != source.name,
                collision=collision,
            )
        )

    return moves, result


def plan_normalize(root: Path) -> tuple[list[PlannedRename], ScanResult]:
    """Складає план перейменування файлів на місці."""
    result = scan(root)
    claimed: set[tuple[str, str]] = set()
    renames: list[PlannedRename] = []

    for source in result.files:
        new_name, collision = _claim(
            source.parent, normalize_filename(source.name), claimed, ignore=source
        )
        if new_name == source.name:
            continue
        renames.append(
            PlannedRename(source=source, target=source.parent / new_name, collision=collision)
        )

    return renames, result


def find_duplicates(root: Path) -> tuple[list[DuplicateGroup], ScanResult]:
    """Знаходить файли з однаковим вмістом.

    Спершу групуємо за розміром і хешуємо лише ті групи, де більше одного
    файлу: файли різного розміру однаковими бути не можуть, тож читати їх
    немає сенсу.
    """
    result = scan(root)

    by_size: dict[int, list[Path]] = {}
    for path in result.files:
        try:
            by_size.setdefault(path.stat().st_size, []).append(path)
        except OSError:
            result.unreadable.append(path)

    groups: list[DuplicateGroup] = []
    for size, candidates in by_size.items():
        if len(candidates) < 2:
            continue

        by_digest: dict[str, list[Path]] = {}
        for path in candidates:
            digest = _digest(path)
            if digest is None:
                result.unreadable.append(path)
                continue
            by_digest.setdefault(digest, []).append(path)

        groups.extend(
            DuplicateGroup(digest=digest, size=size, files=sorted(paths))
            for digest, paths in by_digest.items()
            if len(paths) > 1
        )

    groups.sort(key=lambda group: (-group.wasted_bytes, group.files[0]))
    return groups, result


# ------------------------------------------------------------------ службове


def _claim(
    directory: Path,
    filename: str,
    claimed: set[tuple[str, str]],
    ignore: Path | None = None,
) -> tuple[str, bool]:
    """Резервує ім'я в теці, за потреби додаючи числовий суфікс.

    Порівняння регістронезалежне навмисно: на macOS і Windows `Fail.txt` та
    `fail.txt` — це один файл, тож `Файл.txt` і `файл.txt` після
    транслітерації зіткнулися б, а на Linux — ні. Поводимось за суворішим
    правилом, щоб план не залежав від системи.

    `ignore` — це сам файл, який перейменовують: при нормалізації на місці він
    лежить у тій самій теці, і без цього винятку кожне вже нормальне ім'я
    вважалося б зайнятим самим собою.
    """
    stem, suffix = split_name(filename)
    key = str(directory).casefold()

    candidate = filename
    counter = 1
    collision = False

    while (key, candidate.casefold()) in claimed or _is_taken(directory / candidate, ignore):
        counter += 1
        candidate = f"{stem}_{counter}{suffix}"
        collision = True

    claimed.add((key, candidate.casefold()))
    return candidate, collision


def _is_taken(path: Path, ignore: Path | None) -> bool:
    """Чи зайняте ім'я на диску кимось, окрім самого файлу-джерела."""
    if ignore is not None and path == ignore:
        return False
    return path.exists()


def _digest(path: Path) -> str | None:
    """SHA-256 вмісту або None, якщо файл не вдалося прочитати."""
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def iter_categories() -> Iterator[str]:
    """Категорії в порядку звіту, `others` останньою."""
    yield from CATEGORY_MAP
    yield OTHER_CATEGORY
