from __future__ import annotations

import re
from typing import Dict, List


def parse_excursions(raw_value: str) -> List[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    if text.lower() in {"none", "n/a", "na", "no"}:
        return []
    parts = re.split(r"\s*,\s*|\s*;\s*|\s*\n\s*", text)
    return [part.strip() for part in parts if part.strip()]


def derive_excursion_options(response_rows: List[Dict[str, str]]) -> List[str]:
    return sorted({name for row in response_rows for name in parse_excursions(row.get("excursions_raw", ""))})


def build_excursion_rows(response_row: Dict[str, str], excursion_options: List[str]) -> List[dict]:
    selected = set(parse_excursions(response_row.get("excursions_raw", "")))
    return [
        {
            "response_id": response_row["response_id"],
            "contact_phone": response_row.get("contact_phone", ""),
            "excursion_name": option,
            "interested": "true" if option in selected else "false",
        }
        for option in excursion_options
    ]
