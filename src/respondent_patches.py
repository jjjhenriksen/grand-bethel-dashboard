from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from normalize_responses import normalize_response_record


DEFAULT_PATCHES = {"patches": []}


def load_respondent_patches(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_PATCHES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_PATCHES.copy()
    merged.update(loaded)
    return merged


def save_respondent_patches(path: Path, patches: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(patches, handle, sort_keys=False, allow_unicode=False)


def reset_respondent_patches(path: Path) -> dict[str, Any]:
    patches = {"patches": []}
    save_respondent_patches(path, patches)
    return patches


def add_respondent_patch(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    patches = load_respondent_patches(path)
    patches["patches"].append(patch)
    save_respondent_patches(path, patches)
    return patches


def summarize_respondent_patches(patches: dict[str, Any]) -> str:
    return f"patches={len(patches.get('patches', []))}"


def apply_respondent_patches(responses_df: pd.DataFrame, patch_config: dict[str, Any]) -> pd.DataFrame:
    rows = responses_df.fillna("").to_dict(orient="records") if not responses_df.empty else []

    for patch in patch_config.get("patches", []):
        action = str(patch.get("action", "")).strip().lower()
        response_id = str(patch.get("response_id", "")).strip()

        if action == "remove":
            if not response_id:
                continue
            rows = [row for row in rows if str(row.get("response_id", "")).strip() != response_id]
            continue

        if action == "add":
            if not response_id:
                continue
            fields = patch.get("fields", {}) or {}
            normalized = normalize_response_record(
                {str(key): str(value) for key, value in fields.items()},
                response_id=response_id,
            )
            rows = [row for row in rows if str(row.get("response_id", "")).strip() != response_id]
            rows.append(normalized)

    return pd.DataFrame(rows)
