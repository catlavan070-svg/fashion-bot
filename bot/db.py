"""SQLite: дедупликация, очередь кандидатов, дневная квота постов."""
import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config


@dataclass
class Candidate:
    id: int
    title: str
    summary: str
    link: str
    source: str
    images: list[str]
    fetched_at: float


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen (
                url_hash   TEXT PRIMARY KEY,
                title_hash TEXT,
                first_seen REAL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash   TEXT UNIQUE,
                title      TEXT,
                summary    TEXT,
                link       TEXT,
                source     TEXT,
                images     TEXT,          -- JSON-список URL картинок
                fetched_at REAL,
                used       INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS posts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT,
                link       TEXT,
                posted_at  REAL
            );
            """
        )


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "", title.lower())


def url_hash(link: str) -> str:
    return _hash(link.strip())


def title_hash(title: str) -> str:
    return _hash(_norm_title(title))


def is_seen(link: str, title: str) -> bool:
    """True, если такая новость уже попадалась (по ссылке или по заголовку)."""
    uh, th = url_hash(link), title_hash(title)
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen WHERE url_hash = ? OR title_hash = ? LIMIT 1",
            (uh, th),
        ).fetchone()
    return row is not None


def mark_seen(link: str, title: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen (url_hash, title_hash, first_seen) VALUES (?, ?, ?)",
            (url_hash(link), title_hash(title), time.time()),
        )


def add_candidate(link: str, title: str, summary: str, source: str, images: list[str]) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO candidates
               (url_hash, title, summary, link, source, images, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (url_hash(link), title, summary, link, source, json.dumps(images), time.time()),
        )


def get_fresh_candidates(max_age_hours: int, limit: int = 12) -> list[Candidate]:
    """Непротухшие неиспользованные кандидаты, свежие первыми."""
    cutoff = time.time() - max_age_hours * 3600
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM candidates
               WHERE used = 0 AND fetched_at >= ?
               ORDER BY fetched_at DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    return [
        Candidate(
            id=r["id"], title=r["title"], summary=r["summary"], link=r["link"],
            source=r["source"], images=json.loads(r["images"] or "[]"),
            fetched_at=r["fetched_at"],
        )
        for r in rows
    ]


def mark_candidate_used(candidate_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE candidates SET used = 1 WHERE id = ?", (candidate_id,))


def cleanup_old(max_age_hours: int = 72) -> None:
    """Удаляет совсем старые кандидаты, чтобы база не пухла."""
    cutoff = time.time() - max_age_hours * 3600
    with _conn() as conn:
        conn.execute("DELETE FROM candidates WHERE fetched_at < ?", (cutoff,))


def posts_today() -> int:
    """Сколько постов опубликовано сегодня (по местному времени канала, а не сервера)."""
    start = (
        datetime.now(ZoneInfo(config.TIMEZONE))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM posts WHERE posted_at >= ?", (start,)).fetchone()
    return row["c"]


def gap_ok(min_gap_minutes: int) -> bool:
    """Прошло ли достаточно времени с последнего поста."""
    with _conn() as conn:
        row = conn.execute("SELECT MAX(posted_at) AS last FROM posts").fetchone()
    if not row or row["last"] is None:
        return True
    return (time.time() - row["last"]) >= min_gap_minutes * 60


def record_post(title: str, link: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO posts (title, link, posted_at) VALUES (?, ?, ?)",
            (title, link, time.time()),
        )
