from __future__ import annotations

from pathlib import Path
from typing import Any

import re
import yaml


DEFAULT_PATCHES = {"patches": []}


def load_excursion_patches(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_PATCHES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_PATCHES.copy()
    merged.update(loaded)
    return merged


def save_excursion_patches(path: Path, patches: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(patches, handle, sort_keys=False, allow_unicode=False)


def reset_excursion_patches(path: Path) -> dict[str, Any]:
    patches = {"patches": []}
    save_excursion_patches(path, patches)
    return patches


def add_excursion_patch(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    patches = load_excursion_patches(path)
    patches["patches"].append(patch)
    save_excursion_patches(path, patches)
    return patches


def summarize_excursion_patches(patches: dict[str, Any]) -> str:
    return f"patches={len(patches.get('patches', []))}"


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"\s+", " ", text)
    return text


def apply_excursion_patches(rows: list[dict], patch_config: dict[str, Any]) -> list[dict]:
    patched_rows = [dict(row) for row in rows]

    for patch in patch_config.get("patches", []):
        excursion_name = str(patch.get("excursion_name", "")).strip()
        decision = str(patch.get("decision", "")).strip().lower()
        if not excursion_name or decision not in {"accept", "deny"}:
            continue

        for row in patched_rows:
            if _normalize_text(row.get("excursion_name", "")) != _normalize_text(excursion_name):
                continue
            row["interested"] = "true" if decision == "accept" else "false"

    return patched_rows
