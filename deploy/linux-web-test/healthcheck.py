import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8080/api/health", timeout=3) as r:
    p=json.loads(r.read().decode("utf-8"))
if p.get("status")!="ok": raise SystemExit(1)
