# AGENTS.md

## Проект
Автономный бот автопостинга fashion-новостей в Telegram-канал.
Python 3.13, async (asyncio), пакет `bot/`, запуск: `python -m bot.main`.

## Деплой: GitHub Actions (основной способ)
- Триггер №1 (надёжный): cron-job.org job ID 8659222 → POST workflow_dispatch каждые 15 мин 10:00–23:45 МСК (fine-grained PAT с Actions:write только на этот репо). GitHub cron ненадёжен для новых репо — пропускает слоты.
- Триггер №2 (запасной): `.github/workflows/bot.yml` cron `4,14,24,34,44,54 7-20 * * *` + workflow_dispatch
- Запускает `python -m bot.main --once` (один цикл и выход)
- Состояние = `data/bot.db` + `data/last_run.log` (лог последнего цикла для отладки), коммитятся обратно в репозиторий после каждого прогона
- `bot/main.py` publish: до 2 попыток с разными кандидатами за цикл (фолбэк-цепочка при битых фото/сбое Gemini)
- Секреты в GitHub Secrets: BOT_TOKEN, CHANNEL_ID, GEMINI_API_KEY
- Серверы в США → все источники и Gemini API доступны без VPN
- С российских IP недоступны: Hypebeast, Highsnobiety, Vogue, news.google.com, Gemini API — локальный запуск из РФ усечённый, это ожидаемо

## Архитектура
- `bot/config.py` — все настройки из `.env` с дефолтами; окно постинга POST_WINDOW_START/END_HOUR + TIMEZONE (Europe/Moscow)
- `bot/brands.py` — словарь бренд → алиасы, regex-матчинг с `\b`
- `bot/db.py` — SQLite (`data/bot.db`): `seen` (дедуп по url/title hash), `candidates` (очередь), `posts` (квота/интервал); «сегодня» считается по ZoneInfo(config.TIMEZONE)
- `bot/sources.py` — RSS (httpx → feedparser.parse(bytes)), Google News RSS, Reddit через `.rss` (НЕ .json — 403/429); reddit: stagger 5с + ретрай на 429; блоклист фит/продаж-постов; картинки из `<img>` контента и preview.redd.it→i.redd.it
- `bot/images.py` — og:image через stream первых 256 КБ; скачивание + конвертация в JPEG через Pillow
- `bot/rewriter.py` — Gemini (`google-genai`, модель gemini-3.8-flash): `pick_best` — эвристика БЕЗ LLM (медиа > Reddit, горячие слова, свежесть) для экономии квоты; `rewrite` (пост на русском, ≤700 симв) — 1 вызов Gemini на пост; ротация ключей GEMINI_API_KEY → GEMINI_API_KEY2 (индекс живого в meta `gemini_key_idx`), перебор моделей с пропуском 404 (у ключей разный набор), 503 → ретрай 20с, 429 → пауза 65с + 1 попытка, повторный 429 → следующий ключ или `QuotaExhausted`
- Предохранитель квоты: при `QuotaExhausted` в `meta` (db.py, key-value) пишется `gemini_dead_until` = +60 мин — прогоны в это время не трогают Gemini, но если есть GROQ_API_KEY — постинг продолжается через Groq (`skip_gemini`); снимается при успешном посте через Gemini. Квота free tier сбрасывается ~10:00 МСК (полночь Pacific)
- `bot/rewriter.py` Groq-фолбэк: когда Gemini в 503-шторме/квоте — пост пишет Groq (OpenAI-совместимый API), цепочка имён моделей `_GROQ_MODELS` с пропуском 404 (имена устаревают; живой на 10.2026 — openai/gpt-oss-120b). Groq и Gemini блочат российские IP — локально не проверить
- `bot/publisher.py` — aiogram: media group 1–3 фото, caption ≤1024; фолбэки: 1 фото → текст (если REQUIRE_IMAGE=false); пост без фото получает фирменную карточку-обложку (`bot/card.py`, 1280x800, тёмная плашка с заголовком), чтобы канал не выглядел голым
- `bot/main.py` — `cli()`: `--once` (cron) или демон-режим; publish гейты: окно 10–23 МСК → квота 5/день → gap 150 мин; «режим голода»: если без постов > gap+60 (210 мин) и нет кандидатов с фото — постим пост из резерва без фото с карточкой-обложкой (кандидаты без фото копятся в очереди, `starving = db.gap_ok(gap+60)`), приоритет всегда у постов с фото

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
