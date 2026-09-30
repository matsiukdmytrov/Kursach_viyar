"""Заборонені поштові домени держав-агресорів: РФ та Білорусі.

Список свідомо працює за суфіксами: одне правило `ru` закриває і `mail.ru`,
і `bk.ru`, і будь-який майбутній домен у цій зоні. Окремо перелічені лише
сервіси РФ, які сидять у чужих зонах, — їх за суфіксом зони не впіймати.

Вичерпного списку не існує в принципі: зареєструвати пошту на власному
домені в будь-якій зоні може будь-хто. Тут закрито все, що ловиться за
доменом, — від національних зон до великих провайдерів.
"""

#: Текст, який бачить користувач. Узгоджений і навмисно короткий.
BLOCKED_MESSAGE = "Агресорські домени йдуть лісом"

#: Доменні зони РФ. Кириличні зони вказані у двох формах, бо адреса могла
#: приїхати як `пошта.рф`, так і як `xn--80a1acny.xn--p1ai`.
RUSSIAN_ZONES = frozenset(
    {
        "ru",
        "su",  # зона СРСР, адмініструється з РФ
        "moscow",
        "tatar",
        "рф",
        "xn--p1ai",
        "москва",
        "xn--80adxhks",
        "рус",
        "xn--p1acf",
        "дети",
        "xn--d1acj3b",
        "татар",
        "xn--80aa2cfb",
    }
)

#: Доменні зони Білорусі. Зони достатньо: `tut.by`, `mail.by` та `open.by`
#: закриваються нею автоматично.
BELARUSIAN_ZONES = frozenset(
    {
        "by",
        "бел",
        "xn--90ais",
    }
)

BLOCKED_ZONES = RUSSIAN_ZONES | BELARUSIAN_ZONES

#: Сервіси РФ і Білорусі поза власними зонами. Тут кожен рядок — окрема
#: перевірка, тому додавати сюди щось на кшталт `mail.com` не можна: це
#: німецький провайдер.
BLOCKED_DOMAINS = frozenset(
    {
        # Яндекс
        "yandex.com",
        "yandex.net",
        "yandex.by",
        "yandex.kz",
        "yandex.uz",
        "yandex.com.tr",
        "yandex.com.ge",
        "yandex.eu",
        "yandex.fr",
        "ya.cc",
        # VK / Mail.ru Group
        "vk.com",
        "vkontakte.com",
        "fromru.com",
        "mail15.com",
        "pisem.net",
        # Rambler
        "rambler.co",
    }
)

_BLOCKED = BLOCKED_ZONES | BLOCKED_DOMAINS


def is_blocked(domain: str) -> bool:
    """Чи належить домен (або його батьківська зона) до заборонених.

    Перевірка йде по суфіксах, тому `mail.yandex.com` блокується разом із
    `yandex.com`, а `notyandex.com` — ні: збіг має бути або повний, або по
    межі крапки.
    """
    candidate = domain.strip().rstrip(".").casefold()
    if not candidate:
        return False

    return any(candidate == blocked or candidate.endswith(f".{blocked}") for blocked in _BLOCKED)
