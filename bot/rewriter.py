"""Gemini: выбор самой важной новости и переписывание на русский."""
import asyncio
import logging
import time

from google import genai

from . import config
from .db import Candidate

log = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


# При 503 (high demand на free tier) пробуем запасной алиас модели
_FALLBACK_MODEL = "gemini-flash-latest"


async def _generate(prompt: str) -> str | None:
    """Запрос к Gemini с ретраями: до 3 попыток, со 2-й — запасная модель."""
    for attempt in range(3):
        model = config.GEMINI_MODEL if attempt == 0 else _FALLBACK_MODEL
        try:
            resp = await asyncio.to_thread(
                _get_client().models.generate_content,
                model=model,
                contents=prompt,
            )
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception as exc:
            log.warning("Gemini attempt %d (%s) failed: %.200s", attempt + 1, model, exc)
        if attempt < 2:
            await asyncio.sleep(15 * (attempt + 1))
    return None


def _fallback_pick(candidates: list[Candidate]) -> int:
    """Без Gemini: приоритет новостям из модных медиа, Reddit — в конце."""
    for i, c in enumerate(candidates):
        if not c.source.startswith("r/"):
            return i
    return 0


async def pick_best(candidates: list[Candidate]) -> int:
    """Возвращает индекс самой значимой новости. При ошибке — фолбэк на медиа-источники."""
    if len(candidates) == 1:
        return 0

    lines = []
    for i, c in enumerate(candidates, 1):
        age_h = round((time.time() - c.fetched_at) / 3600, 1)
        lines.append(f"{i}. [{c.source}, {age_h}ч назад] {c.title}")
    listing = "\n".join(lines)

    prompt = (
        "Ты — редактор Telegram-канала о высокой моде и стритвире "
        "(Gucci, Louis Vuitton, BAPE, Raf Simons, Balenciaga и др.).\n"
        "Из списка новостей выбери ОДНУ самую важную и интересную для аудитории.\n"
        "Приоритет: дропы, релизы, рестоки, коллаборации, показы, назначения "
        "креативных директоров, громкие скандалы. Свежие новости важнее старых.\n"
        "Новости-перепечатки и слабые поводы пропускай.\n\n"
        f"{listing}\n\n"
        "Ответь ТОЛЬКО номером выбранной новости, без пояснений."
    )
    answer = await _generate(prompt)
    if answer:
        try:
            idx = int("".join(ch for ch in answer.split()[0] if ch.isdigit())) - 1
            if 0 <= idx < len(candidates):
                return idx
        except (ValueError, IndexError):
            pass
        log.warning("Gemini returned unexpected pick: %r, fallback to media sources", answer)
    return _fallback_pick(candidates)


async def rewrite(candidate: Candidate) -> str | None:
    """Переписывает новость в пост на русском. None при ошибке."""
    prompt = (
        "Ты — автор популярного Telegram-канала о высокой моде и стритвире.\n"
        "Перепиши эту новость на русский язык для поста в канал.\n\n"
        "Правила:\n"
        "- Первая строка — короткий цепляющий заголовок (можно 1–2 эмодзи).\n"
        "- Дальше 2–4 предложения сути: что случилось, детали (даты, цены, места), почему это важно.\n"
        "- Тон: живой, как у модного инсайдера, без канцелярита и без воды.\n"
        "- Не выдумывай факты, которых нет в новости.\n"
        "- В конце 2–4 хэштега брендов (например #balenciaga).\n"
        "- Общий объём — до 700 символов.\n"
        "- Выведи ТОЛЬКО готовый текст поста, без пояснений и без markdown-разметки.\n\n"
        f"Заголовок: {candidate.title}\n"
        f"Источник: {candidate.source}\n"
        f"Текст новости: {candidate.summary or '(только заголовок)'}"
    )
    return await _generate(prompt)
