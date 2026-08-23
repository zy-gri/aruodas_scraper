from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests


ARUODAS_KAUNAS_RENT_URL = "https://www.aruodas.lt/butu-nuoma/kaune/"


@dataclass
class FetchResult:
    url: str
    status_code: int
    elapsed_seconds: float
    content_length: int
    content_type: str | None
    sha256: str
    html_path: Path
    metadata_path: Path


def fetch_page(
    url: str = ARUODAS_KAUNAS_RENT_URL,
    raw_dir: str | Path = "data/raw",
) -> FetchResult:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "lt-LT,lt;q=0.9,en;q=0.8",
    }

    print(f"[FETCH] {url}")

    started = time.perf_counter()

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
        allow_redirects=True,
    )

    elapsed = time.perf_counter() - started

    html_bytes = response.content
    digest = hashlib.sha256(html_bytes).hexdigest()

    html_path = raw_dir / f"aruodas_{timestamp}.html"
    metadata_path = raw_dir / f"aruodas_{timestamp}.json"

    html_path.write_bytes(html_bytes)

    metadata = {
        "requested_url": url,
        "final_url": response.url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "status_code": response.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "content_length": len(html_bytes),
        "content_type": response.headers.get("Content-Type"),
        "sha256": digest,
        "response_headers": dict(response.headers),
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return FetchResult(
        url=response.url,
        status_code=response.status_code,
        elapsed_seconds=elapsed,
        content_length=len(html_bytes),
        content_type=response.headers.get("Content-Type"),
        sha256=digest,
        html_path=html_path,
        metadata_path=metadata_path,
    )