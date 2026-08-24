from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_ENRICHMENT_DIR = Path("data/enrichment")
DEFAULT_PATTERN = "aruodas_text_enrichment*.json"


def load_enrichments(path: str | Path = DEFAULT_ENRICHMENT_DIR) -> list[dict[str, Any]]:
    """Load one enrichment JSON file or merge all sidecars in a directory.

    Directory mode lets us append researched batches without rewriting older
    source files. Duplicate listing IDs are resolved deterministically: files
    are read in sorted filename order and the later record wins.
    """

    path = Path(path)

    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Enrichment file must contain a JSON list: {path}")
        return data

    if not path.exists():
        raise FileNotFoundError(f"Enrichment path not found: {path}")

    files = sorted(path.glob(DEFAULT_PATTERN))
    if not files:
        raise FileNotFoundError(
            f"No enrichment files matching {DEFAULT_PATTERN!r} in {path}"
        )

    by_id: dict[str, dict[str, Any]] = {}

    for file_path in files:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(
                f"Enrichment file must contain a JSON list: {file_path}"
            )

        for record in data:
            listing_id = record.get("listing_id") if isinstance(record, dict) else None
            if not listing_id:
                continue
            by_id[listing_id] = record

    return list(by_id.values())
