from __future__ import annotations

from pathlib import Path
from typing import Any

import re
import yaml


DEFAULT_PATCHES = {"patches": []}


def load_attendee_patches(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_PATCHES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_PATCHES.copy()
    merged.update(loaded)
    return merged


def save_attendee_patches(path: Path, patches: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(patches, handle, sort_keys=False, allow_unicode=False)


def reset_attendee_patches(path: Path) -> dict[str, Any]:
    patches = {"patches": []}
    save_attendee_patches(path, patches)
    return patches


def add_attendee_patch(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    patches = load_attendee_patches(path)
    patches["patches"].append(patch)
    save_attendee_patches(path, patches)
    return patches


def summarize_attendee_patches(patches: dict[str, Any]) -> str:
    return f"patches={len(patches.get('patches', []))}"


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_age_fields(age_raw: str, attendee_type: str) -> tuple[str, str]:
    raw = str(age_raw or "").strip()
    declared_type = str(attendee_type or "").strip().lower()
    digits = re.findall(r"\d{1,2}", raw)
    if declared_type in {"adult", "daughter"}:
        if raw:
            if declared_type == "adult":
                return ("adult" if not digits or int(digits[0]) >= 18 else digits[0], "adult")
            return (digits[0] if digits else "", "daughter")
        return ("adult" if declared_type == "adult" else "", declared_type)
    if digits:
        age_value = int(digits[0])
        return (str(age_value), "adult" if age_value >= 18 else "daughter")
    return ("adult", "adult")


def apply_attendee_patches(rows: list[dict], patch_config: dict[str, Any]) -> list[dict]:
    patched_rows = [dict(row) for row in rows]

    for patch in patch_config.get("patches", []):
        action = patch.get("action")
        response_id = str(patch.get("response_id", "")).strip()
        attendee_name = str(patch.get("attendee_name", "")).strip()

        if action == "remove":
            patched_rows = [
                row
                for row in patched_rows
                if not (
                    str(row.get("response_id", "")).strip() == response_id
                    and _normalize_text(row.get("attendee_name", "")) == _normalize_text(attendee_name)
                )
            ]
            continue

        if action == "add":
            if not response_id or not attendee_name:
                continue
            age_raw = str(patch.get("attendee_age_raw", "")).strip()
            age_normalized, normalized_type = _normalize_age_fields(age_raw, str(patch.get("attendee_type", "")))
            already_exists = any(
                str(row.get("response_id", "")).strip() == response_id
                and _normalize_text(row.get("attendee_name", "")) == _normalize_text(attendee_name)
                for row in patched_rows
            )
            if already_exists:
                continue

            template = next(
                (row for row in patched_rows if str(row.get("response_id", "")).strip() == response_id),
                {},
            )
            candidate = dict(template)
            candidate.update(
                {
                    "response_id": response_id,
                    "attendee_name": attendee_name,
                    "attendee_age_raw": age_raw,
                    "attendee_age_normalized": age_normalized,
                    "attendee_type": normalized_type,
                }
            )
            patched_rows.append(candidate)

    return patched_rows
