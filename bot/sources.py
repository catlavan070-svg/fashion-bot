"""Источники новостей: RSS модных медиа, Google News, Reddit (через RSS).

Все запросы идут через httpx с явными таймаутами — зависания исключены.
"""
import asyncio
import html
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field

import feedparser
import httpx

from . import config

log = logging.getLogger(__name__)

# RSS-ленты модных медиа. Если лента недоступна (например, сайт блочит
# российские IP — с зарубежного VPS будет работать), бот просто залогирует
# и пойдёт дальше. Список можно свободно дополнять.
RSS_FEEDS = [
    ("Hypebeast", "https://hypebeast.com/feed"),
    ("Highsnobiety", "https://www.highsnobiety.com/feed/"),
    ("Sneaker News", "https://sneakernews.com/feed/"),
    ("Vogue", "https://www.vogue.com/feed/rss"),
    ("GQ", "https://www.gq.com/feed/rss"),
    ("The Fashionisto", "https://www.thefashionisto.com/feed/"),
    ("Fashion Week Daily", "https://fashionweekdaily.com/feed/"),
]

# Группированные запросы для Google News (OR, чтобы не дёргать по каждому бренду).
# NB: news.google.com недоступен с российских IP — с зарубежного VPS работает.
GOOGLE_NEWS_QUERIES = [
    'gucci OR "louis vuitton" OR balenciaga OR prada OR dior',
    'bape OR "a bathing ape" OR supreme OR "off-white" OR vetements',
    '"raf simons" OR "rick owens" OR margiela OR loewe OR "stone island" OR "chrome hearts" OR burberry OR versace',
]

REDDIT_SUBS = [
    "streetwear",
    "fashion",
    "supremeclothing",
    "rafsimons",
    "balenciaga",
    "bapeheads",
]

_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
_IMG_LINK_RE = re.compile(r'href="([^"]+(?:' + "|".join(_IMG_EXT) + r')[^"]*)"', re.IGNORECASE)
# Превью preview.redd.it/<id>.<ext> конвертируется в полноразмер i.redd.it/<id>.<ext>
_REDDIT_THUMB_RE = re.compile(r"https://preview\.redd\.it/([a-z0-9]+)\.(jpg|png)\?", re.IGNORECASE)
# Не новости, а служебные/фит/продаж-посты — пропускаем по заголовку.
# Resale-объявления палятся по: iso/looking for (куплю), shipped/BIN/$N/размер (продам).
_REDDIT_TITLE_BLOCKLIST = re.compile(
    r"wdywt|megathread|simple questions|general discussion|daily (discussion|thread)|"
    r"weekly (thread|discussion)|what are you wearing|fit check|outfit|\bfit\b|"
    r"(?:my|today'?s)\s+look|\bpickup|"
    r"\bwts\b|\bwtt\b|\bwtb\b|\bfs\b|legit check|\blc\b|for sale|\bwearing\b|\bwore\b|"
    r"\biso\b|looking for|\bshipped\b|\bbin\b|\bgrail\b|\$\s?\d+|"
    r"\bsize\s?(us|uk|eu|xs|s|m|l|xl|xxl|\d)|\b\d{2,3}\s?usd\b",
    re.IGNORECASE,
)


@dataclass
class Article:
    title: str
    summary: str
    link: str
    source: str
    images: list[str] = field(default_factory=list)
    published: float = 0.0


def _strip_html(text: str, limit: int = 600) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]


def _entry_images(entry) -> list[str]:
    """Картинки из RSS-энтри: media:content, media:thumbnail, enclosures, <img> в теле."""
    urls = []
    for media in entry.get("media_content", []):
        u = media.get("url")
        if u:
            urls.append(u)
    for thumb in entry.get("media_thumbnail", []):
        u = thumb.get("url")
        if u:
            urls.append(u)
    for enc in entry.get("enclosures", []):
        u = enc.get("href") or enc.get("url")
        if u and str(enc.get("type", "")).startswith("image"):
            urls.append(u)
    # запасной вариант: <img> прямо в summary/content (WordPress-ленты так отдают фото)
    body = " ".join(
        filter(None, [entry.get("summary") or "", *[c.get("value", "") for c in entry.get("content", [])]])
    )
    urls += [html.unescape(u) for u in re.findall(r'<img[^>]+src="([^"]+)"', body)]
    return urls


def _reddit_images(entry) -> list[str]:
    """Полноразмерные картинки из HTML-контента reddit RSS."""
    content = (entry.get("content") or [{}])[0].get("value", "")
    images = [html.unescape(u) for u in _IMG_LINK_RE.findall(content)]
    for m in _REDDIT_THUMB_RE.finditer(content):
        images.append(f"https://i.redd.it/{m.group(1)}.{m.group(2)}")
    return images


def _entry_timestamp(entry) -> float:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return time.mktime(parsed)
        except (OverflowError, ValueError):
            pass
    return time.time()


def _to_articles(data: bytes, source: str, reddit: bool = False) -> list[Article]:
    feed = feedparser.parse(data)
    articles = []
    for e in feed.entries[:30]:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if not title or not link:
            continue
        if reddit and _REDDIT_TITLE_BLOCKLIST.search(title):
            continue
        raw_summary = e.get("summary") or e.get("description") or ""
        if reddit:
            # отрезаем служебный хвост "submitted by /u/..."
            raw_summary = raw_summary.split("submitted by")[0]
        images = _reddit_images(e) if reddit else _entry_images(e)
        articles.append(
            Article(
                title=html.unescape(title),
                summary=_strip_html(raw_summary),
                link=link,
                source=source,
                images=list(dict.fromkeys(images)),
                published=_entry_timestamp(e),
            )
        )
    return articles


async def _get(client: httpx.AsyncClient, url: str) -> bytes:
    resp = await client.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


async def _fetch_feed(client: httpx.AsyncClient, name: str, url: str) -> list[Article]:
    try:
        return _to_articles(await _get(client, url), name)
    except Exception as exc:
        log.warning("RSS %s failed: %s", name, exc)
        return []


async def _fetch_google_news(client: httpx.AsyncClient, query: str) -> list[Article]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        return _to_articles(await _get(client, url), "Google News")
    except Exception as exc:
        log.warning("Google News query failed: %s", exc)
        return []


async def _fetch_reddit(client: httpx.AsyncClient, sub: str, delay: float) -> list[Article]:
    # Reddit жёстко рейт-лимитит: сабреддиты запрашиваем с паузой, на 429 — один ретрай
    if delay:
        await asyncio.sleep(delay)
    url = f"https://www.reddit.com/r/{sub}/hot.rss?limit=25"
    for attempt in range(2):
        try:
            return _to_articles(await _get(client, url), f"r/{sub}", reddit=True)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt == 0:
                await asyncio.sleep(25)
                continue
            log.warning("Reddit r/%s failed: %s", sub, exc)
            return []
        except Exception as exc:
            log.warning("Reddit r/%s failed: %s", sub, exc)
            return []
    return []


async def fetch_all() -> list[Article]:
    """Собирает статьи изо всех источников параллельно."""
    async with httpx.AsyncClient(
        headers={"User-Agent": config.USER_AGENT}, follow_redirects=True
    ) as client:
        tasks = [_fetch_feed(client, name, url) for name, url in RSS_FEEDS]
        if config.GOOGLE_NEWS_ENABLED:
            tasks += [_fetch_google_news(client, q) for q in GOOGLE_NEWS_QUERIES]
        # с паузой 5с между сабреддитами, чтобы не словить 429
        tasks += [_fetch_reddit(client, s, i * 5.0) for i, s in enumerate(REDDIT_SUBS)]
        results = await asyncio.gather(*tasks)

    articles = [a for batch in results for a in batch]
    log.info("Fetched %d articles from all sources", len(articles))
    return articles
