from __future__ import annotations

import json
from pathlib import Path


def read_grids(store_grids: Path) -> list[dict]:
    if not store_grids.exists():
        return []
    try:
        d = json.loads(store_grids.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def write_grids(store_grids: Path, grids: list[dict]) -> None:
    store_grids.write_text(json.dumps(grids, indent=2), encoding="utf-8")
