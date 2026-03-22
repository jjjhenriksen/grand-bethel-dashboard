from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, Tuple

import pandas as pd
import yaml


def normalize_header(text: str) -> str:
    normalized = str(text).strip()
    normalized = normalized.replace("–", "-").replace("—", "-")
    normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
    normalized = normalized.replace('"', "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def load_field_map(path: Path) -> Dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        raw_map = yaml.safe_load(handle) or {}
    return {canonical: normalize_header(raw_name) for canonical, raw_name in raw_map.items()}


def discover_input_csv(raw_dir: Path) -> Path:
    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")
    if len(csv_files) > 1:
        raise FileExistsError(
            f"Expected exactly one CSV in {raw_dir}, found {len(csv_files)}. Use --input to choose a file."
        )
    return csv_files[0]


def load_raw_csv(csv_path: Path, field_map: Dict[str, str]) -> Tuple[pd.DataFrame, Dict[str, str]]:
    raw_df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    normalized_columns = {column: normalize_header(column) for column in raw_df.columns}
    reverse_columns = {normalized: original for original, normalized in normalized_columns.items()}

    missing = [raw_name for raw_name in field_map.values() if raw_name not in reverse_columns]
    if missing:
        missing_str = "\n".join(f"- {name}" for name in missing)
        raise ValueError(f"Input CSV is missing expected columns:\n{missing_str}")

    canonical_to_original = {
        canonical: reverse_columns[raw_name]
        for canonical, raw_name in field_map.items()
    }
    renamed = raw_df.rename(columns={original: canonical for canonical, original in canonical_to_original.items()})
    return renamed, canonical_to_original
