"""Vérification de la démo réellement servie, via HTTP standard, sans écriture."""
import hashlib
import json
import os
from urllib.request import urlopen

base = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")


def get(path):
    with urlopen(base + path, timeout=10) as response:
        assert response.status == 200
        return json.load(response)


assert get("/health/ready")["status"] == "ok"
caps = get("/api/v1/capabilities")
assert caps["version"] == "0.2.0"
assert all(provider["status"] == "unsupported" for provider in caps["providers"] if provider["chain_id"] != "eip155:1")
cases = get("/api/v1/cases")
case = next(item for item in cases if item["is_demo"])
detail = get(f'/api/v1/cases/{case["id"]}')
run = detail["runs"][0]
assert run["is_demo"] and run["coverage_status"] == "partial"
assert run["allocation_policy"] == "none" and run["label_snapshot"] == []
operations = get(f'/api/v1/runs/{run["id"]}/operations')
movements = [movement["observation"] for operation in operations for movement in operation["movements"]]
assert len(movements) == 3
assert all(movement["is_demo"] for movement in movements)
assert "1000000000000000001" in [movement["amount_raw"] for movement in movements]
snapshot = get(f'/api/v1/snapshots/{movements[0]["snapshot_id"]}')
canonical = json.dumps(snapshot["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
assert hashlib.sha256(canonical).hexdigest() == snapshot["sha256"] == run["manifest"][0]["sha256"]
print("V0.2.0 OK : PostgreSQL/Redis, Démonstration séparée, montants exacts, preuves et couverture explicite.")
