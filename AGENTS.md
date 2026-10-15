# AGENTS.md

## Проект
Автономный бот автопостинга fashion-новостей в Telegram-канал.
Python 3.13, async (asyncio), пакет `bot/`, запуск: `python -m bot.main`.

## Деплой: GitHub Actions (основной способ)
- `.github/workflows/bot.yml`: cron `*/30 7-20 * * *` (10:00–23:30 МСК) + workflow_dispatch
- Запускает `python -m bot.main --once` (один цикл и выход)
- Состояние = `data/bot.db`, коммитится обратно в репозиторий после каждого прогона
- Секреты в GitHub Secrets: BOT_TOKEN, CHANNEL_ID, GEMINI_API_KEY
- Серверы в США → все источники и Gemini API доступны без VPN
- С российских IP недоступны: Hypebeast, Highsnobiety, Vogue, news.google.com, Gemini API — локальный запуск из РФ усечённый, это ожидаемо

## Архитектура
- `bot/config.py` — все настройки из `.env` с дефолтами; окно постинга POST_WINDOW_START/END_HOUR + TIMEZONE (Europe/Moscow)
- `bot/brands.py` — словарь бренд → алиасы, regex-матчинг с `\b`
- `bot/db.py` — SQLite (`data/bot.db`): `seen` (дедуп по url/title hash), `candidates` (очередь), `posts` (квота/интервал); «сегодня» считается по ZoneInfo(config.TIMEZONE)
- `bot/sources.py` — RSS (httpx → feedparser.parse(bytes)), Google News RSS, Reddit через `.rss` (НЕ .json — 403/429); reddit: stagger 5с + ретрай на 429; блоклист фит/продаж-постов; картинки из `<img>` контента и preview.redd.it→i.redd.it
- `bot/images.py` — og:image через stream первых 256 КБ; скачивание + конвертация в JPEG через Pillow
- `bot/rewriter.py` — Gemini (`google-genai`): `pick_best` (ранжирование) + `rewrite` (пост на русском, ≤700 симв)
- `bot/publisher.py` — aiogram: media group 1–3 фото, caption ≤1024; фолбэки: 1 фото → текст (если REQUIRE_IMAGE=false)
- `bot/main.py` — `cli()`: `--once` (cron) или демон-режим; publish гейты: окно 10–23 МСК → квота 5/день → gap 150 мин

## Особенности окружения
- Локально на Windows: импорт aiogram ~30 сек (антивирус) — не зависание; нужен пакет `tzdata` для zoneinfo
- Reddit без ключа: только `.rss` endpoints, строгий рейт-лимит

## Команды (Windows)
- Установка: `py -3 -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
- Запуск: `.venv\Scripts\python.exe -m bot.main` | `--once`

## Правила
- Секреты только в `.env` / GitHub Secrets (не коммитить)
- Новые бренды — в `bot/brands.py`, новые ленты — в `RSS_FEEDS` в `bot/sources.py`
- Логи на русском, код комментировать на русском
