"""Скачивает лог последнего прогона workflow."""
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
HEADERS = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "fashion-bot-setup",
}


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


runs = json.loads(get(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1"))["workflow_runs"]
run_id = runs[0]["id"]
jobs = json.loads(get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs"))["jobs"]
for job in jobs:
    print(f"=== JOB {job['name']}: {job['conclusion']} ===")
    for step in job.get("steps", []):
        print(f"  {step['name']}: {step['conclusion']}")
    # лог джобы (plain text)
    try:
        logs = get(f"https://api.github.com/repos/{REPO}/actions/jobs/{job['id']}/logs").decode("utf-8", errors="replace")
        # показываем только строки нашего бота
        for line in logs.splitlines():
            if "bot." in line or "INFO" in line or "WARNING" in line or "ERROR" in line:
                print("   ", line.split(" ", 2)[-1][:160])
    except Exception as exc:
        print("  logs unavailable:", exc)
