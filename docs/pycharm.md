# Як запустити бот у PyCharm

## 1. Відкрити проєкт

**File → Open** і вибрати теку `personal_assistant` — саме її, а не батьківську
`Project_Work_Python`. Усередині має лежати `pyproject.toml`; якщо PyCharm його
бачить, він сам запропонує налаштувати інтерпретатор.

## 2. Підключити інтерпретатор

Віртуальне середовище вже створене й усі залежності встановлені, тож нове
робити не треба.

**Settings → Project: personal_assistant → Python Interpreter →**
шестерня → **Add Local Interpreter… → Select existing** →

```
/Users/user/Applications/MC_Petya/Project_Work_Python/personal_assistant/.venv/bin/python
```

Перевірка: у списку пакетів мають бути `pydantic`, `prompt_toolkit`,
`email-validator`, `pytest`.

> Якщо PyCharm підкреслює `from personal_assistant...` червоним — правою
> кнопкою на теці `src` → **Mark Directory as → Sources Root**.

## 3. Створити конфігурацію запуску

**Run → Edit Configurations… → + → Python**

| Поле | Значення |
|---|---|
| Name | `Personal Assistant` |
| Виконувати | перемкнути на **module** і вписати `personal_assistant` |
| Working directory | корінь проєкту (`.../personal_assistant`) |
| Python interpreter | той, що з кроку 2 |
| **Emulate terminal in output console** | **✅ обов'язково увімкнути** |

### Про «Emulate terminal in output console»

Це найважливіший пункт. Звичайна консоль PyCharm не є терміналом, і
застосунок це помічає: `prompt_toolkit` вимикається, а бот переходить у
спрощений режим через `input()`.

| Прапорець | Що працює |
|---|---|
| ✅ увімкнено | `Tab`-доповнення, підказка внизу, історія `↑`/`↓`, кольори |
| ❌ вимкнено | лише введення команд; доповнення й підказок немає |

Це не помилка — запасний режим зроблено навмисно, щоб бот працював у пайпах і
в CI. Але для ручного тестування інтерфейсу прапорець потрібен.

## 4. Запустити

Кнопка ▶ (`Ctrl+R` / `⌃R`). У консолі має з'явитись:

```
Персональний помічник. Введи 'help' для переліку команд, 'exit' — щоб вийти.
pa>
```

Вихід — команда `exit` або `Ctrl+D`.

## Альтернатива: вкладка Terminal

Якщо з конфігурацією щось не складається, у вкладці **Terminal** унизу PyCharm
працює одразу й повноцінно:

```bash
.venv/bin/pa
```

## Окрема тека даних для тестів

Щоб не змішувати тестові дані зі своїми, додай у конфігурацію змінну
оточення (**Environment variables**):

```
PA_DATA_DIR=/tmp/pa-test
```

Тоді `contacts.json`, `notes.json` і `tasks.json` створяться саме там, а щоб
почати з чистого аркуша — просто видали цю теку.

## Конфігурація для тестів

**Run → Edit Configurations… → + → Python tests → pytest**

| Поле | Значення |
|---|---|
| Target | **Custom** (або `Script path` → тека `tests`) |
| Working directory | корінь проєкту |

Очікуваний результат: усі тести зелені (`718 passed`).

## Якщо щось не запускається

| Симптом | Причина й що робити |
|---|---|
| `ModuleNotFoundError: personal_assistant` | Обрано не той інтерпретатор, або пакет не встановлено. У вкладці Terminal: `.venv/bin/python -m pip install -e ".[dev]"` |
| Немає `Tab`-доповнення | Не увімкнено «Emulate terminal in output console» |
| Кожна введена команда друкується двічі | Те саме: запасний режим сам друкує відлуння введення |
| Кирилиця виводиться як `????` | Актуально для Windows: у конфігурації виставити `PYTHONIOENCODING=utf-8` |
| `Не вдалося прочитати збережені дані` при старті | У теці даних лежить зіпсований або несумісний файл. Видали `PA_DATA_DIR` і запусти знову |
