"""Публикация поста в Telegram-канал: 1–3 фото сверху, текст снизу."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, InputMediaPhoto

from . import config
from .images import download_images

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # лимит Telegram для подписи к медиа


def _fit_caption(text: str) -> str:
    """Обрезает подпись под лимит Telegram, стараясь резать по абзацу/предложению."""
    if len(text) <= CAPTION_LIMIT:
        return text
    cut = text[: CAPTION_LIMIT - 1]
    for sep in ("\n\n", "\n", ". "):
        pos = cut.rfind(sep)
        if pos > CAPTION_LIMIT // 2:
            return cut[: pos + len(sep)].rstrip()
    return cut.rstrip() + "…"


async def post(bot: Bot, caption: str, image_urls: list[str]) -> bool:
    """Постит медиагруппу (1–3 фото) с подписью. True при успехе."""
    caption = _fit_caption(caption)
    images = await download_images(image_urls, max_n=3)

    if images:
        # Основной путь: медиагруппа с подписью на первом фото
        try:
            media = [
                InputMediaPhoto(
                    media=BufferedInputFile(raw, filename=f"photo{i}.jpg"),
                    caption=caption if i == 0 else None,
                )
                for i, raw in enumerate(images)
            ]
            await bot.send_media_group(chat_id=config.CHANNEL_ID, media=media)
            return True
        except TelegramAPIError as exc:
            log.warning("Media group failed (%s), trying single photo", exc)
            try:
                await bot.send_photo(
                    chat_id=config.CHANNEL_ID,
                    photo=BufferedInputFile(images[0], filename="photo0.jpg"),
                    caption=caption,
                )
                return True
            except TelegramAPIError as exc2:
                log.warning("Single photo failed: %s", exc2)

    if config.REQUIRE_IMAGE:
        log.warning("No usable images and REQUIRE_IMAGE=true — post skipped")
        return False

    try:
        await bot.send_message(chat_id=config.CHANNEL_ID, text=caption)
        return True
    except TelegramAPIError as exc:
        log.error("Failed to send even text message: %s", exc)
        return False
