# Fashion News Autoposter

Автономный бот для Telegram-канала о высокой моде: сам находит свежие новости
(Gucci, Louis Vuitton, BAPE, Raf Simons, Balenciaga и др.), переписывает их
нейросетью Gemini на русский и постит в канал с 1–3 фото.

**Постинг:** 3–5 постов в день, только с 10:00 до 23:00 по Москве,
с интервалом ~2,5 часа. Работает полностью без VPN и бесплатно —
на серверах GitHub Actions (США), поэтому все зарубежные источники доступны.

## Как это работает

1. GitHub Actions запускает бота каждые 30 минут (10:00–23:30 МСК).
2. Бот собирает новости из RSS (Hypebeast, Highsnobiety, Vogue, GQ,
   Sneaker News и др.), Google News и Reddit.
3. Фильтрует по списку брендов (`bot/brands.py` — легко дополнять).
4. Новые новости кладутся в очередь (SQLite прямо в репозитории, дубли отсекаются).
5. Если сейчас в окне 10:00–23:00, не выбрана дневная квота (5) и прошло ≥2,5 ч
   с прошлого поста — Gemini выбирает самую важную новость из очереди,
   переписывает её на русском, и бот постит медиагруппу с фото в канал.

## Настройка (один раз, ~10 минут)

1. **Токен бота:** @BotFather → `/newbot` → скопируй токен.
   Добавь бота в канал как **администратора с правом публикации постов**.
2. **Ключ Gemini:** https://aistudio.google.com → «Get API key» (бесплатно;
   из РФ сайт может потребовать VPN — нужен один раз, дальше всё работает без него).
3. **Залей код на GitHub** (публичный репозиторий — тогда Actions безлимитно бесплатен;
   секреты всё равно никто не видит):
   ```bash
   git init && git add . && git commit -m "init"
   git remote add origin https://github.com/<твой_логин>/<репо>.git
   git push -u origin main
   ```
4. **Добавь секреты:** репозиторий → Settings → Secrets and variables → Actions →
   New repository secret — создай три: `BOT_TOKEN`, `CHANNEL_ID` (например `@mychannel`),
   `GEMINI_API_KEY`.
5. **Включи Actions:** вкладка Actions → «I understand my workflows, enable them».
   Для проверки запусти вручную: Actions → Fashion Autoposter → Run workflow.

Всё. Бот работает сам, состояние сохраняется коммитом `chore: bot state` в репозиторий.

## Запуск локально (необязательно, для отладки)

```bash
# Windows
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # заполнить ключи
.venv\Scripts\python.exe -m bot.main          # демон-режим 24/7
.venv\Scripts\python.exe -m bot.main --once   # один цикл и выход
```

> Локально из РФ часть источников и Gemini недоступны — это нормально,
> на GitHub Actions (США) работает всё. Первый запуск может идти ~30 сек
> из-за антивируса — не зависание.

## Настройки (.env локально / Secrets не нужны — дефолты в коде)

| Переменная | Дефолт | Описание |
|---|---|---|
| `DAILY_QUOTA` | 5 | максимум постов в день |
| `MIN_POST_GAP_MINUTES` | 150 | минимальный перерыв между постами |
| `POST_WINDOW_START_HOUR` | 10 | начало окна постинга |
| `POST_WINDOW_END_HOUR` | 23 | конец окна постинга |
| `TIMEZONE` | Europe/Moscow | часовой пояс окна и квоты |
| `CHECK_INTERVAL_MINUTES` | 30 | период обхода источников (демон-режим) |
| `REQUIRE_IMAGE` | true | не постить новости без фото |
| `MAX_CANDIDATE_AGE_HOURS` | 48 | старше этого — новость «протухла» |
| `GOOGLE_NEWS_ENABLED` | true | Google News как источник |

## Структура

```
bot/
├── config.py      # настройки из .env
├── brands.py      # список отслеживаемых брендов
├── db.py          # SQLite: дедупликация, очередь, квота (по таймзоне канала)
├── sources.py     # RSS + Google News + Reddit
├── images.py      # og:image, скачивание, конвертация в JPEG
├── rewriter.py    # Gemini: выбор новости + перевод/переписывание
├── publisher.py   # отправка медиагруппы в канал
└── main.py        # цикл; --once для cron/GitHub Actions
.github/workflows/bot.yml  # расписание GitHub Actions
```

Логи: `data/bot.log`, база: `data/bot.db`.
