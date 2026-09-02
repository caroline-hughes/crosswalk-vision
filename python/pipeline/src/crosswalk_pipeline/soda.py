from __future__ import annotations

from typing import Callable, Dict, List

import requests

# Socrata's default page is 100 records. A $limit on a pre-baked URL is easy to
# drop; always pass $limit/$offset/$order and walk until a short page.
DEFAULT_PAGE_SIZE = 1000


def fetch_soda_records(
    resource_url: str,
    *,
    select: str,
    where: str,
    order: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    timeout: int = 120,
    getter: Callable[[str, Dict[str, str]], List[dict]] | None = None,
) -> List[dict]:
    fetch = getter or _http_get_json
    rows: List[dict] = []
    offset = 0
    while True:
        params = {
            "$select": select,
            "$where": where,
            "$order": order,
            "$limit": str(page_size),
            "$offset": str(offset),
        }
        page = fetch(resource_url, params)
        if not isinstance(page, list):
            raise ValueError(f"SODA response was not a list: {page!r}")
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def _http_get_json(url: str, params: Dict[str, str]) -> List[dict]:
    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload.get("message") or "SODA error")
    return payload
