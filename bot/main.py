"""Главный цикл бота: сбор → фильтр → очередь → публикация по квоте."""
import argparse
import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from . import config, db, rewriter, sources
from .brands import match_brands
from .images import ensure_images
from .publisher import post

# Windows-консоль по умолчанию в cp1252 и падает на кириллице/эмодзи
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


async def collect_candidates() -> int:
    """Собирает новости, фильтрует по брендам, кладёт новые в очередь."""
    articles = await sources.fetch_all()
    added = 0
    for a in articles:
        text = f"{a.title} {a.summary}"
        if not match_brands(text):
            continue
        if db.is_seen(a.link, a.title):
            continue
        db.mark_seen(a.link, a.title)

        images = await ensure_images(a.link, a.images)
        if config.REQUIRE_IMAGE and not images:
            log.info("Skipped (no images): %s", a.title)
            continue

        db.add_candidate(a.link, a.title, a.summary, a.source, images)
        added += 1
        log.info("Candidate queued: [%s] %s", a.source, a.title)
    return added


def _window_ok() -> bool:
    """Постим только в окне 10:00–23:00 по местному времени канала (config.TIMEZONE)."""
    hour = datetime.now(ZoneInfo(config.TIMEZONE)).hour
    return config.POST_WINDOW_START_HOUR <= hour < config.POST_WINDOW_END_HOUR


async def publish_cycle(bot: Bot) -> None:
    """Публикует один лучший кандидат, если позволяют окно, квота и интервал."""
    if not _window_ok():
        log.info(
            "Вне окна постинга (%02d:00–%02d:00 %s) — только собираем новости",
            config.POST_WINDOW_START_HOUR, config.POST_WINDOW_END_HOUR, config.TIMEZONE,
        )
        return
    if db.posts_today() >= config.DAILY_QUOTA:
        log.info("Daily quota (%d) reached — only collecting news", config.DAILY_QUOTA)
        return
    if not db.gap_ok(config.MIN_POST_GAP_MINUTES):
        log.info("Too soon since last post — waiting")
        return

    candidates = db.get_fresh_candidates(config.MAX_CANDIDATE_AGE_HOURS)
    if not candidates:
        log.info("No fresh candidates to post")
        return

    idx = await rewriter.pick_best(candidates)
    best = candidates[idx]
    log.info("Picked for posting: %s", best.title)

    text = await rewriter.rewrite(best)
    if not text:
        log.warning("Rewrite failed, candidate stays in queue: %s", best.title)
        return

    if await post(bot, text, best.images):
        db.mark_candidate_used(best.id)
        db.record_post(best.title, best.link)
        log.info("POSTED (%d/%d today): %s", db.posts_today(), config.DAILY_QUOTA, best.title)


def _check_config() -> None:
    missing = config.validate()
    if missing:
        log.error("Заполни в .env: %s", ", ".join(missing))
        sys.exit(1)


async def _cycle(bot: Bot) -> None:
    """Один рабочий цикл: собрать новости, опубликовать пост (если можно)."""
    added = await collect_candidates()
    log.info("New candidates this cycle: %d", added)
    await publish_cycle(bot)
    db.cleanup_old()


async def run_once() -> None:
    """Один цикл и выход — режим для cron / GitHub Actions."""
    _check_config()
    db.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    try:
        await _cycle(bot)
    finally:
        await bot.session.close()
    log.info("Cycle done, exiting")


async def main() -> None:
    """Демон-режим: бесконечный цикл для запуска на своём ПК/VPS."""
    _check_config()
    db.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    log.info(
        "Bot started. Interval: %d min, quota: %d/day, gap: %d min, window: %02d:00–%02d:00 %s",
        config.CHECK_INTERVAL_MINUTES, config.DAILY_QUOTA, config.MIN_POST_GAP_MINUTES,
        config.POST_WINDOW_START_HOUR, config.POST_WINDOW_END_HOUR, config.TIMEZONE,
    )

    while True:
        try:
            await _cycle(bot)
        except Exception:
            log.exception("Unexpected error in cycle — continuing")
        log.info("Sleeping %d minutes...", config.CHECK_INTERVAL_MINUTES)
        await asyncio.sleep(config.CHECK_INTERVAL_MINUTES * 60)


def cli() -> None:
    parser = argparse.ArgumentParser(description="Fashion news autoposter")
    parser.add_argument(
        "--once", action="store_true",
        help="один цикл и выход (режим для cron / GitHub Actions)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run_once() if args.once else main())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")


if __name__ == "__main__":
    cli()
