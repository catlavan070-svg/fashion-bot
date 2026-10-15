import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect(r"D:\nekit\data\bot.db")
junk = [
    "Day in the city",
    "Nature inspired color palette",
    "FS Supreme Long Sleeve Bundle Size Medium",
    "My first time wearing pink",
]
for title in junk:
    conn.execute("DELETE FROM candidates WHERE title = ?", (title,))
conn.commit()

print("очередь после чистки:")
for source, title in conn.execute("SELECT source, title FROM candidates WHERE used = 0"):
    print(f"  [{source}] {title[:70]}")
conn.close()
