"""Конфигурация бота. Все секреты берутся из файла .env"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

# --- Обязательные секреты (.env) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")  # @username канала или id вида -100...
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Запасной ключ Gemini (необязательно): при исчерпании дневной квоты основного
# бот прозрачно переключается на него — суммарная квота удваивается
GEMINI_API_KEY2 = os.getenv("GEMINI_API_KEY2", "")
GEMINI_API_KEY3 = os.getenv("GEMINI_API_KEY3", "")
# Третья линия обороны: Groq (llama-3.3-70b) выручает, когда Gemini в 503-шторме
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Настройки с дефолтами ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
DAILY_QUOTA = int(os.getenv("DAILY_QUOTA", "5"))
# 150 мин между постами равномерно размазывает 5 постов по окну 10:00–23:00
MIN_POST_GAP_MINUTES = int(os.getenv("MIN_POST_GAP_MINUTES", "150"))
REQUIRE_IMAGE = os.getenv("REQUIRE_IMAGE", "true").lower() == "true"
# news.google.com заблокирован с российских IP — с зарубежного VPS работает
GOOGLE_NEWS_ENABLED = os.getenv("GOOGLE_NEWS_ENABLED", "true").lower() == "true"

# Кандидаты старше этого возраста считаются протухшими и не постятся
MAX_CANDIDATE_AGE_HOURS = int(os.getenv("MAX_CANDIDATE_AGE_HOURS", "48"))

# Окно постинга (по местному времени канала): посты выходят только с 10:00 до 23:00
POST_WINDOW_START_HOUR = int(os.getenv("POST_WINDOW_START_HOUR", "10"))
POST_WINDOW_END_HOUR = int(os.getenv("POST_WINDOW_END_HOUR", "23"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

DB_PATH = DATA_DIR / "bot.db"
LOG_PATH = DATA_DIR / "bot.log"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 FashionNewsBot/1.0"
)


def validate() -> list[str]:
    """Возвращает список незаполненных обязательных настроек."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not CHANNEL_ID:
        missing.append("CHANNEL_ID")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    return missing
