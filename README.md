# qqRP Bot

Telegram Business Bot на **aiogram 3.x** для RP-действий через точку (`.муа`, `.обнять`, `.цветы` и т.д.) — работает от имени владельца аккаунта через **Telegram Business Connection**.

## Возможности

- Dot-команды (`.муа`, `.обнять`, `.прижать`, `.цветы`, `.кольцо`, `.подарок`, `.сердце`, `.погладить`, `.печенье`, `.кофе`, `.торт`, `.дай5`, `.шлеп`, `.пнуть`, `.удар`, `.тык`, `.буп`, `.укус`, `.снежок`, `.бан`), автоматически определяющие цель (reply / `@username`).
- Правильные HTML-независимые упоминания через `MessageEntity(type=text_mention)` — не зависят от того, есть ли у пользователя username.
- Склонение по полу (`/start` → выбор пола → `Иван поцеловал` / `Анна поцеловала`).
- Пользовательские RP-действия: мастер `/addrp` в личном чате с ботом (триггер → эмодзи, включая **премиум-эмодзи** → шаблон текста).
- `/profile`, `/stats`, `/settings` (случайные анимации, компактный режим, случайные шаблоны, язык).
- Удаление исходной команды пользователя после обработки (если есть права).
- Полностью асинхронный стек: aiogram 3.x + SQLAlchemy Async + PostgreSQL.

## Структура проекта

```
app/
  handlers/         # /start, /profile, /stats, /settings, /addrp
    business/        # business_message и business_connection
  database/          # engine, session maker
  models/            # User, ActionLog, CustomTrigger
  middlewares/        # DatabaseMiddleware, UserMiddleware
  services/           # ActionService (рендер действий), UserService
  utils/              # парсинг команд, построение MessageEntity, UTF-16 офсеты
  keyboards/          # inline-клавиатуры
  data/actions.json   # встроенные действия — расширяются без изменения кода
  config.py
main.py
```

## Запуск

```bash
cp .env.example .env       # заполнить BOT_TOKEN и DATABASE_URL
pip install -r requirements.txt
python main.py
```

Бот сам создаст таблицы в PostgreSQL при первом запуске (`init_models()`).
Для продакшена рекомендуется завести Alembic-миграции вместо `create_all`.

## Деплой на Railway

В репозитории уже есть всё нужное:

- Автоопределение Nixpacks по `requirements.txt` (Python + venv + pip настраиваются автоматически — свой `nixpacks.toml` тут не нужен и может всё сломать, если переопределить `nixPkgs` без `pip`).
- `Procfile` — `worker: python main.py` (это воркер, не веб-сервис — публичный домен не нужен).
- `railway.json` — билдер NIXPACKS, `startCommand`, restart policy `ON_FAILURE`.
- `.python-version` — подсказка Nixpacks по версии Python (3.12).

Шаги:

1. Создай проект на Railway → **Deploy from GitHub repo**.
2. Добавь плагин **PostgreSQL** — Railway сам создаст переменную `DATABASE_URL`.
   Важно: Railway отдаёт её как `postgres://` или `postgresql://` — `app/config.py` **автоматически** переписывает схему в `postgresql+asyncpg://`, ничего вручную менять не нужно.
3. В Variables добавь `BOT_TOKEN` (токен из @BotFather).
4. Убедись, что сервис создан как **Worker**, а не Web (Railway иногда пытается назначить `PORT` и ждать HTTP-ответ — polling-боту это не нужно; в `railway.json` явно задан `startCommand`, так что Railway не будет ждать открытия порта).
5. Deploy — при первом запуске бот сам создаст таблицы в подключённой PostgreSQL.

## Добавление нового встроенного действия

Просто добавь новый ключ в `app/data/actions.json` — код менять не нужно:

```json
"обливание": {
  "emojis": ["🌊"],
  "templates": [
    {"emoji": "🌊", "text": "{user} {verb} {target} водой", "verb": {"male": "облил", "female": "облила"}}
  ]
}
```

## Технические детали, на которые стоит обратить внимание

- Telegram Bot API не позволяет одновременно использовать `parse_mode` и `entities` в одном сообщении, поэтому упоминания и премиум-эмодзи собираются вручную через `EntityTextBuilder` (`app/utils/entity_builder.py`) с точным подсчётом смещений в UTF-16 code units (`utf16_len`) — это важно, т.к. Python `len()` считает кодовые точки и даёт неверные офсеты для эмодзи вне BMP (например 😘, 🤗).
- `ActionService` — единая точка входа для рендера и встроенных, и пользовательских действий (принцип открытости/закрытости: новые встроенные действия добавляются только через JSON).
