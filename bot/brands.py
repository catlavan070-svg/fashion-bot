"""Список отслеживаемых брендов и матчинг текста по ним."""
import re

# Ключ — каноническое имя, значения — варианты написания (нижний регистр).
# Сюда легко добавлять новые бренды.
BRANDS: dict[str, list[str]] = {
    "Gucci": ["gucci"],
    "Louis Vuitton": ["louis vuitton", "louisvuitton"],
    "BAPE": ["bape", "a bathing ape", "bathing ape"],
    "Raf Simons": ["raf simons"],
    "Balenciaga": ["balenciaga"],
    "Prada": ["prada"],
    "Dior": ["dior"],
    "Supreme": ["supreme"],
    "Off-White": ["off-white", "off white"],
    "Stone Island": ["stone island"],
    "Chrome Hearts": ["chrome hearts"],
    "Rick Owens": ["rick owens"],
    "Vetements": ["vetements"],
    "Maison Margiela": ["maison margiela", "margiela"],
    "Loewe": ["loewe"],
    "Burberry": ["burberry"],
    "Versace": ["versace"],
}

# Заранее компилируем regex'ы с границами слов, чтобы "bape" не матчилось внутри других слов
_PATTERNS: list[tuple[str, re.Pattern]] = [
    (brand, re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE))
    for brand, aliases in BRANDS.items()
    for alias in aliases
]

# Ложные контексты: "Supreme Court" — суд, "supreme leader" — политика, а не бренд.
# Вырезаем до матчинга.
_CONTEXT_TRAPS = re.compile(r"supreme\s+(?:court|leader|leaders)", re.IGNORECASE)


def match_brands(text: str) -> list[str]:
    """Возвращает список канонических имён брендов, найденных в тексте."""
    text = _CONTEXT_TRAPS.sub(" ", text)
    found = []
    for brand, pattern in _PATTERNS:
        if pattern.search(text) and brand not in found:
            found.append(brand)
    return found
