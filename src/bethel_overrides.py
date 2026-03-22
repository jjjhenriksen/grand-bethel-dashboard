from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_OVERRIDES = {
    "extra_blocks": [],
    "competition_overrides": {},
    "competition_time_overrides": [],
    "excursion_overrides": {},
    "block_assignments": [],
    "conflict_ignores": [],
}


def load_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_OVERRIDES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_OVERRIDES.copy()
    merged.update(loaded)
    return merged


def save_overrides(path: Path, overrides: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(overrides, handle, sort_keys=False, allow_unicode=False)


def reset_overrides(path: Path) -> dict[str, Any]:
    overrides = {
        "extra_blocks": [],
        "competition_overrides": {},
        "competition_time_overrides": [],
        "excursion_overrides": {},
        "block_assignments": [],
        "conflict_ignores": [],
    }
    save_overrides(path, overrides)
    return overrides


def add_extra_block(
    path: Path,
    *,
    day_label: str,
    event_date: str,
    time_raw: str,
    event_title: str,
    dress_code: str,
    event_type: str,
) -> dict[str, Any]:
    overrides = load_overrides(path)
    overrides["extra_blocks"].append(
        {
            "day_label": day_label,
            "event_date": event_date,
            "time_raw": time_raw,
            "event_title": event_title,
            "dress_code": dress_code,
            "event_type": event_type,
        }
    )
    save_overrides(path, overrides)
    return overrides


def set_competition_override(
    path: Path,
    *,
    competition_type: str,
    day_label: str,
    event_date: str,
    time_raw: str,
    event_title: str,
    notes: str,
) -> dict[str, Any]:
    overrides = load_overrides(path)
    overrides["competition_overrides"][competition_type] = {
        "day_label": day_label,
        "event_date": event_date,
        "time_raw": time_raw,
        "event_title": event_title,
        "notes": notes,
    }
    save_overrides(path, overrides)
    return overrides


def set_competition_time_override(
    path: Path,
    *,
    competition_type: str,
    participant_group: str,
    participant_name: str,
    response_id: str,
    day_label: str,
    event_date: str,
    time_raw: str,
    event_title: str,
    notes: str,
) -> dict[str, Any]:
    overrides = load_overrides(path)
    rules = overrides.setdefault("competition_time_overrides", [])
    normalized_type = str(competition_type).strip()
    normalized_group = str(participant_group or "").strip().lower()

    rule = {
        "competition_type": normalized_type,
        "participant_group": normalized_group,
        "participant_name": str(participant_name or "").strip(),
        "response_id": str(response_id or "").strip(),
        "day_label": day_label,
        "event_date": event_date,
        "time_raw": time_raw,
        "event_title": event_title,
        "notes": notes,
    }

    replaced = False
    for index, existing in enumerate(rules):
        if (
            str(existing.get("competition_type", "")).strip() == normalized_type
            and str(existing.get("participant_group", "")).strip().lower() == normalized_group
            and str(existing.get("participant_name", "")).strip().lower() == str(participant_name or "").strip().lower()
            and str(existing.get("response_id", "")).strip() == str(response_id or "").strip()
        ):
            rules[index] = rule
            replaced = True
            break

    if not replaced:
        rules.append(rule)

    save_overrides(path, overrides)
    return overrides


def set_excursion_override(
    path: Path,
    *,
    excursion_name: str,
    day_label: str,
    event_date: str,
    notes: str,
) -> dict[str, Any]:
    overrides = load_overrides(path)
    overrides["excursion_overrides"][excursion_name] = {
        "day_label": day_label,
        "event_date": event_date,
        "notes": notes,
    }
    save_overrides(path, overrides)
    return overrides


def set_block_assignment(
    path: Path,
    *,
    block_id: str,
    assignment: str,
    people: list[str] | None = None,
) -> dict[str, Any]:
    overrides = load_overrides(path)
    rules = overrides.setdefault("block_assignments", [])
    normalized_block_id = str(block_id).strip()
    normalized_assignment = str(assignment).strip().lower()
    rule = {
        "block_id": normalized_block_id,
        "assignment": normalized_assignment,
        "people": [str(person).strip() for person in (people or []) if str(person).strip()],
    }

    replaced = False
    for index, existing in enumerate(rules):
        if str(existing.get("block_id", "")).strip() == normalized_block_id:
            rules[index] = rule
            replaced = True
            break

    if not replaced:
        rules.append(rule)

    save_overrides(path, overrides)
    return overrides


def summarize_overrides(overrides: dict[str, Any]) -> str:
    return (
        f"extra_blocks={len(overrides.get('extra_blocks', []))}, "
        f"competition_overrides={len(overrides.get('competition_overrides', {}))}, "
        f"competition_time_overrides={len(overrides.get('competition_time_overrides', []))}, "
        f"excursion_overrides={len(overrides.get('excursion_overrides', {}))}, "
        f"block_assignments={len(overrides.get('block_assignments', []))}, "
        f"conflict_ignores={len(overrides.get('conflict_ignores', []))}"
    )
