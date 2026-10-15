import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect(r"D:\nekit\data\bot.db")
print("--- опубликованные посты ---")
for title, ts in conn.execute("SELECT title, posted_at FROM posts ORDER BY posted_at"):
    from datetime import datetime, timezone, timedelta
    msk = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=3)))
    print(f"  {msk:%d.%m %H:%M} МСК | {title[:80]}")
print("--- очередь кандидатов ---")
for source, title, used in conn.execute(
    "SELECT source, title, used FROM candidates ORDER BY fetched_at DESC LIMIT 8"
):
    print(f"  [{'USED' if used else '    '}] [{source}] {title[:70]}")
print("--- всего просмотрено новостей ---")
print(" ", conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0])
