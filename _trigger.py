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
    f"https://api.github.com/repos/{REPO}/actions/workflows/bot.yml/dispatches",
    method="POST",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "fashion-bot-setup",
    },
    data=json.dumps({"ref": "main"}).encode(),
)
with urllib.request.urlopen(req, timeout=20) as resp:
    print("Запущен:", resp.status)
