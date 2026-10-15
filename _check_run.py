"""Проверяет статус последнего прогона workflow."""
import json
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = "catlavan070-svg/fashion-bot"

proc = subprocess.run(
    [r"C:\Program Files\Git\cmd\git.exe", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True,
)
token = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())["password"]

req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "fashion-bot-setup",
    },
)
with urllib.request.urlopen(req, timeout=20) as resp:
    data = json.loads(resp.read())

runs = data.get("workflow_runs", [])
if not runs:
    print("Прогонов пока нет")
else:
    r = runs[0]
    print(f"Статус: {r['status']} | Результат: {r.get('conclusion')} | {r['html_url']}")
