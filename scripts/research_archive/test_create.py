import urllib.request
import json
import urllib.error

payload = {
    "model": "k2horizon",
    "modelfile": 'FROM "G:/My Drive/K2-Horizon-1B-BF16.gguf"'
}

req = urllib.request.Request(
    "http://127.0.0.1:11434/api/create",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        for line in resp:
            print(line.decode("utf-8", errors="ignore"))
except urllib.error.HTTPError as e:
    print("ERR:", e.code, e.read().decode())
