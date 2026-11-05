"""Exécuter depuis la racine après installation Python."""
import json
from pathlib import Path
from apps.api.main import app

destination = Path("docs/openapi.json")
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
