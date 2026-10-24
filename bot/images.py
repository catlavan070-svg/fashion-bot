"""Добыча и подготовка картинок: og:image со страницы статьи, скачивание, конвертация."""
import asyncio
import io
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from PIL import Image

from . import config

log = logging.getLogger(__name__)

MIN_BYTES = 10 * 1024        # меньше 10 КБ — скорее всего иконка/заглушка
MAX_BYTES = 20 * 1024 * 1024  # лимит Telegram на фото
MAX_SIDE = 1600


# og:image живёт в <head> — читаем только начало страницы, этого достаточно
HEAD_READ_LIMIT = 256 * 1024


async def extract_from_page(url: str, limit: int = 3) -> list[str]:
    """Тянем og:image / twitter:image со страницы статьи (первые 256 КБ)."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": config.USER_AGENT}, follow_redirects=True, timeout=25
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                if "html" not in resp.headers.get("content-type", ""):
                    return []
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes(16384):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= HEAD_READ_LIMIT:
                        break
        soup = BeautifulSoup(b"".join(chunks).decode("utf-8", errors="ignore"), "html.parser")
    except Exception as exc:
        log.warning("Failed to fetch page for images (%s): %s: %s", url, type(exc).__name__, exc)
        return []

    images = []
    for attrs in (
        {"property": "og:image"},
        {"name": "twitter:image"},
        {"name": "twitter:image:src"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            images.append(urljoin(url, tag["content"]))
    # запас: hero-фото прямо из тела страницы (если og:image нет/скрыт за JS)
    for img in soup.find_all("img", src=True)[:4]:
        src = img["src"]
        if src.startswith("data:") or "logo" in src.lower() or "icon" in src.lower():
            continue
        images.append(urljoin(url, src))
    return list(dict.fromkeys(images))[:limit]


def _to_jpeg(raw: bytes) -> bytes | None:
    """Конвертирует любую картинку в JPEG приемлемого для Telegram размера."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        if img.width < 200 or img.height < 200:
            return None  # слишком мелкая — не для поста
        img = img.convert("RGB")
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception:
        return None


async def download_images(urls: list[str], max_n: int = 3) -> list[bytes]:
    """Скачивает и готовит до max_n картинок. Невалидные пропускаются."""
    result: list[bytes] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": config.USER_AGENT}, follow_redirects=True, timeout=30
    ) as client:
        for url in urls:
            if len(result) >= max_n:
                break
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                raw = resp.content
                if not (MIN_BYTES <= len(raw) <= MAX_BYTES):
                    continue
                jpeg = await asyncio.to_thread(_to_jpeg, raw)
                if jpeg:
                    result.append(jpeg)
            except Exception as exc:
                log.debug("Image download failed (%s): %s", url, exc)
    return result


async def ensure_images(link: str, existing: list[str], limit: int = 3) -> list[str]:
    """Если у новости нет картинок из RSS — пробуем вытащить со страницы статьи."""
    if existing:
        return existing[:limit]
    return await extract_from_page(link, limit)
