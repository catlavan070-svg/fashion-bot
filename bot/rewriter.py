"""Gemini: выбор самой важной новости и переписывание на русский."""
import asyncio
import logging
import time

import httpx
from google import genai

from . import config, db
from .db import Candidate

log = logging.getLogger(__name__)

_clients: dict[str, genai.Client] = {}


def _get_client(key: str) -> genai.Client:
    if key not in _clients:
        _clients[key] = genai.Client(api_key=key)
    return _clients[key]


# Перебор моделей: 404 = модель недоступна этому ключу → сразу следующая.
# У разных ключей разный набор моделей (у ключей AI Studio может не быть 3.8).
_MODELS = [config.GEMINI_MODEL, "gemini-2.5-flash", "gemini-flash-latest"]

# Ключи: основной + необязательные запасные (квота суммируется)
_KEYS = [k for k in (config.GEMINI_API_KEY, config.GEMINI_API_KEY2, config.GEMINI_API_KEY3) if k]


class QuotaExhausted(Exception):
    """Дневная квота исчерпана на ВСЕХ ключах (429 повторился после паузы)."""


async def _generate_on_key(key: str, prompt: str) -> str | None:
    """Один ключ: перебор моделей. 404 → следующая модель без паузы;
    503 → ретрай через 20с; 429 → пауза 65с и вторая попытка (вдруг лимит
    поминутный), повторный 429 → QuotaExhausted (квота дня сгорела)."""
    saw_429 = False
    for model in _MODELS:
        for backoff in (0, 25, 50):  # 503-штормы длятся минуты — ждём дольше
            if backoff:
                await asyncio.sleep(backoff)
            try:
                resp = await asyncio.to_thread(
                    _get_client(key).models.generate_content,
                    model=model,
                    contents=prompt,
                )
                text = (resp.text or "").strip()
                if text:
                    return text
                log.warning("Gemini (%s): пустой ответ", model)
            except Exception as exc:
                err = str(exc)
                log.warning("Gemini (%s) failed: %.250s", model, err)
                if "404" in err or "NOT_FOUND" in err:
                    break  # модели нет у ключа — берём следующую без паузы
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    if saw_429:
                        raise QuotaExhausted(f"квота ключа ...{key[-4:]} исчерпана")
                    saw_429 = True
                    log.warning("Gemini 429 — пауза 65с и ещё попытка")
                    await asyncio.sleep(65)
    return None


async def _generate(prompt: str) -> str | None:
    """Перебор ключей: transient-сбой (None) → стоп; сгоревшая дневная квота →
    переключаемся на запасной ключ. Индекс живого ключа храним в БД, чтобы
    следующие прогоны не тратили вызовы на мёртвый ключ."""
    key_idx = int(db.get_meta("gemini_key_idx") or 0) % len(_KEYS)
    for offset in range(len(_KEYS)):
        idx = (key_idx + offset) % len(_KEYS)
        try:
            return await _generate_on_key(_KEYS[idx], prompt)
        except QuotaExhausted:
            log.warning("Дневная квота ключа #%d исчерпана", idx + 1)
            if offset == len(_KEYS) - 1:
                raise  # все ключи мертвы — включится предохранитель в main
            nxt = (idx + 1) % len(_KEYS)
            db.set_meta("gemini_key_idx", str(nxt))
            log.warning("Переключаюсь на запасной ключ Gemini (#%d)", nxt + 1)
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


async def _groq_generate(prompt: str) -> str | None:
    """Запасная нейросеть Groq (llama-3.3-70b): выручает, когда Gemini лежит
    в 503-шторме или сжёг квоту на обоих ключах. Отличный русский, бесплатный."""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
                if text:
                    log.info("Пост сгенерирован запасной нейросетью Groq")
                    return text
        except Exception as exc:
            log.warning("Groq attempt %d failed: %.200s", attempt + 1, exc)
            if attempt == 0:
                await asyncio.sleep(15)
    return None


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
    quota_dead = False
    try:
        text = await _generate(prompt)
    except QuotaExhausted:
        text, quota_dead = None, True
    if not text and config.GROQ_API_KEY:
        log.warning("Gemini не справился — пробую запасную нейросеть Groq")
        text = await _groq_generate(prompt)
    if not text and quota_dead:
        raise QuotaExhausted("квота Gemini исчерпана, запасная нейросеть недоступна")
    return text
