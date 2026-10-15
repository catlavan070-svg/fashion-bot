"""Разово настраивает GitHub: кладёт 3 секрета в репозиторий через API.
Токен берётся из Git Credential Manager и никуда не выводится.
"""
import base64
import json
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nacl import encoding, public

from bot import config

REPO = "catlavan070-svg/fashion-bot"

# 1. Токен из Git Credential Manager
proc = subprocess.run(
    [r"C:\Program Files\Git\cmd\git.exe", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True,
)
creds = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())
token = creds.get("password")
if not token:
    print("FAIL: не удалось получить токен из GCM")
    sys.exit(1)
print("Токен из GCM получен (не показываю)")


def api(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "fashion-bot-setup",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode() or "{}"
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


# 2. Проверяем доступ к репозиторию
status, body = api("GET", f"/repos/{REPO}")
print("Репозиторий:", status, json.loads(body).get("full_name", body[:200]))
if status != 200:
    sys.exit(1)

# 3. Публичный ключ репозитория для шифрования секретов
status, body = api("GET", f"/repos/{REPO}/actions/secrets/public-key")
if status != 200:
    print("FAIL public-key:", status, body[:300])
    sys.exit(1)
key_data = json.loads(body)
pub_key = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())
sealed = public.SealedBox(pub_key)

# 4. Кладём три секрета
secrets = {
    "BOT_TOKEN": config.BOT_TOKEN,
    "CHANNEL_ID": config.CHANNEL_ID,
    "GEMINI_API_KEY": config.GEMINI_API_KEY,
}
for name, value in secrets.items():
    encrypted = sealed.encrypt(value.encode())
    payload = {"encrypted_value": base64.b64encode(encrypted).decode(), "key_id": key_data["key_id"]}
    status, body = api("PUT", f"/repos/{REPO}/actions/secrets/{name}", payload)
    print(f"Секрет {name}: HTTP {status} {'OK' if status in (201, 204) else body[:200]}")

# 5. Запускаем workflow вручную для первой проверки
status, body = api("POST", f"/repos/{REPO}/actions/workflows/bot.yml/dispatches", {"ref": "main"})
print("Запуск workflow:", status, "OK" if status == 204 else body[:300])
