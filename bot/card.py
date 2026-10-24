"""Карточка-обложка для постов, у которых нет фото (голодные дни).

Пост в канале всегда должен выглядеть оформленным: если у новости нет
картинки, рисуем тёмную плашку с заголовком вместо фото.
"""
import io
import logging

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

W, H = 1280, 800
_ACCENT = (233, 30, 99)

# DejaVu есть на ubuntu-latest (раннер), arial — на локальной Windows; обе с кириллицей
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_FONT_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _font(size: int, bold: bool = True):
    for path in (_FONT_CANDIDATES if bold else _FONT_REGULAR):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_card(headline: str) -> bytes | None:
    """JPEG-карточка 1280x800 с заголовком. None если совсем не удалось."""
    try:
        img = Image.new("RGB", (W, H), (18, 18, 22))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 10], fill=_ACCENT)
        d.text((64, 64), "FASHION NEWS | НОВОСТИ МОДЫ", font=_font(34), fill=_ACCENT)

        font = _font(58)
        lines: list[str] = []
        for paragraph in headline.split("\n"):
            line = ""
            for word in paragraph.split():
                test = f"{line} {word}".strip()
                if d.textlength(test, font=font) <= W - 128:
                    line = test
                elif line:
                    lines.append(line)
                    line = word
                else:
                    line = word
            if line:
                lines.append(line)
        y = 210
        for ln in lines[:6]:
            d.text((64, y), ln, font=font, fill=(245, 245, 245))
            y += 78

        d.text((64, H - 92), "@fashion_news_archive", font=_font(30, bold=False), fill=(150, 150, 150))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception as exc:
        log.warning("Card render failed: %s", exc)
        return None
