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


# При 503 (high demand на free tier) чередуем модели и ретраим с нарастающей паузой
_MODELS = [config.GEMINI_MODEL, "gemini-flash-latest"]
_BACKOFF = [20, 40, 60]  # секунды между попытками


async def _generate(prompt: str) -> str | None:
    """Запрос к Gemini: до 4 попыток, чередование моделей, пауза 20/40/60с.
    На 429 (квота исчерпана) — сразу стоп, ретрай бесполезен."""
    last_err = ""
    for attempt in range(4):
        model = _MODELS[attempt % len(_MODELS)]
        try:
            resp = await asyncio.to_thread(
                _get_client().models.generate_content,
                model=model,
                contents=prompt,
            )
            text = (resp.text or "").strip()
            if text:
                return text
            last_err = "empty response"
        except Exception as exc:
            last_err = str(exc)
            log.warning("Gemini attempt %d (%s) failed: %.300s", attempt + 1, model, last_err)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                log.warning("Gemini quota exhausted — no retry until reset")
                return None
        if attempt < 3:
            await asyncio.sleep(_BACKOFF[attempt])
    log.warning("Gemini exhausted all retries: %.200s", last_err)
    return None


# Горячие слова в заголовке = вероятно важная новость (дроп/релиз/коллаб)
_HOT_WORDS = (
    "drop", "release", "restock", "collab", "collaboration", "unveil", "announce",
    "first look", "launch", "debut", "collection", "campaign", "creative director",
    "x ",  # коллабы вида "BAPE x Adidas"
)


def pick_best(candidates: list[Candidate]) -> int:
    """Эвристика без LLM (экономим квоту Gemini): медиа > Reddit,
    горячие слова в заголовке, свежесть."""
    now = time.time()

    def score(c: Candidate) -> float:
        s = 0.0
        if c.source.startswith("r/"):
            s -= 10  # Reddit — только если больше ничего нет
        title = c.title.lower()
        s += sum(2.0 for w in _HOT_WORDS if w in title)
        s -= (now - c.fetched_at) / 3600 * 0.05  # чем свежее, тем лучше
        return s

    return max(range(len(candidates)), key=lambda i: score(candidates[i]))


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
