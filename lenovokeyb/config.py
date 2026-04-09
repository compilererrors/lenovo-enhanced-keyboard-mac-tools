from __future__ import annotations

import json
from pathlib import Path

from .models import KeyMapping


def default_config_path() -> Path:
    return Path.home() / ".config" / "lenovokeyb" / "mappings.json"


def load_mappings(path: Path | None = None) -> list[KeyMapping]:
    config_path = path or default_config_path()
    if not config_path.exists():
        return []

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    raw_mappings = data.get("mappings", [])
    return [KeyMapping.from_dict(item) for item in raw_mappings]


def save_mappings(mappings: list[KeyMapping], path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "mappings": [m.to_dict() for m in mappings],
    }
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return config_path

