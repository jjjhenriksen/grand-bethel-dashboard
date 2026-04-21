from __future__ import annotations

from pathlib import Path
from typing import Any

import re
import yaml


DEFAULT_PATCHES = {"patches": []}


def load_competition_patches(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_PATCHES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_PATCHES.copy()
    merged.update(loaded)
    return merged


def save_competition_patches(path: Path, patches: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(patches, handle, sort_keys=False, allow_unicode=False)


def reset_competition_patches(path: Path) -> dict[str, Any]:
    patches = {"patches": []}
    save_competition_patches(path, patches)
    return patches


def add_competition_patch(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    patches = load_competition_patches(path)
    patches["patches"].append(patch)
    save_competition_patches(path, patches)
    return patches


def summarize_competition_patches(patches: dict[str, Any]) -> str:
    return f"patches={len(patches.get('patches', []))}"


def _normalize(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    text = text.replace("&", " and ")
    text = re.sub(r"[()\\[\\],:]+", " ", text)
    text = text.replace("this includes", "including")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _matches_text(actual: str, expected: str) -> bool:
    normalized_actual = _normalize(actual)
    normalized_expected = _normalize(expected)
    if not normalized_expected:
        return True
    if normalized_actual == normalized_expected:
        return True
    if normalized_actual and normalized_expected and (
        normalized_expected in normalized_actual or normalized_actual in normalized_expected
    ):
        return True

    actual_tokens = {token for token in normalized_actual.split(" ") if token}
    expected_tokens = {token for token in normalized_expected.split(" ") if token}
    if expected_tokens and expected_tokens.issubset(actual_tokens):
        return True
    if actual_tokens and actual_tokens.issubset(expected_tokens):
        return True
    return False


def _canonical_participant_name(
    participant_name: str,
    response_id: str,
    attendee_rows: list[dict],
) -> str:
    normalized_name = _normalize(participant_name)
    for attendee in attendee_rows:
        if str(attendee.get("response_id", "")).strip() != str(response_id).strip():
            continue
        attendee_name = str(attendee.get("attendee_name", "")).strip()
        if _matches_text(attendee_name, participant_name):
            return attendee_name
        if normalized_name and _normalize(attendee_name) == normalized_name:
            return attendee_name
    return str(participant_name).strip()


def apply_competition_patches(
    rows: list[dict],
    patch_config: dict[str, Any],
    attendee_rows: list[dict] | None = None,
) -> list[dict]:
    patched_rows = [dict(row) for row in rows]
    attendee_rows = attendee_rows or []

    for patch in patch_config.get("patches", []):
        action = patch.get("action")

        if action == "remove":
            filtered_rows: list[dict] = []
            for row in patched_rows:
                matches = True

                response_id = patch.get("response_id", "")
                if response_id and str(row.get("response_id", "")).strip() != str(response_id).strip():
                    matches = False

                competition_type = patch.get("competition_type", "")
                if competition_type and not _matches_text(row.get("competition_type", ""), competition_type):
                    matches = False

                participant_name = patch.get("participant_name", "")
                if participant_name and not _matches_text(row.get("participant_name", ""), participant_name):
                    matches = False

                category_raw = patch.get("category_raw", "")
                if category_raw and not _matches_text(row.get("category_raw", ""), category_raw):
                    matches = False

                if matches:
                    continue
                filtered_rows.append(row)

            patched_rows = filtered_rows
            continue

        if action == "add":
            response_id = str(patch.get("response_id", "")).strip()
            if not response_id:
                continue

            participant_name = _canonical_participant_name(
                str(patch.get("participant_name", "")).strip(),
                response_id,
                attendee_rows,
            )
            competition_type = str(patch.get("competition_type", "")).strip()
            category_raw = str(patch.get("category_raw", "")).strip()
            lowered_type = competition_type.lower()
            lowered_category = category_raw.lower()
            explicit_group_flag = str(patch.get("is_group_competition", "")).strip().lower()
            if explicit_group_flag in {"true", "false"}:
                is_group_competition = explicit_group_flag == "true"
            else:
                is_group_competition = (
                    lowered_type in {"choir", "variety_show"}
                    or (lowered_type == "performing_arts" and ("ensemble" in lowered_category or "sign language" in lowered_category))
                )

            candidate = {
                "response_id": response_id,
                "participant_name": participant_name,
                "competition_type": competition_type,
                "is_group_competition": "true" if is_group_competition else "false",
                "category_raw": category_raw,
                "source_field": "competition_patch",
                "notes": "Added via competition patch.",
            }
            already_exists = any(
                str(row.get("response_id", "")).strip() == response_id
                and _matches_text(str(row.get("participant_name", "")), participant_name)
                and _matches_text(str(row.get("competition_type", "")), competition_type)
                and (
                    not category_raw
                    or _matches_text(str(row.get("category_raw", "")), category_raw)
                )
                for row in patched_rows
            )
            if not already_exists:
                patched_rows.append(candidate)
            continue

        if action == "set_group_flag":
            response_id = str(patch.get("response_id", "")).strip()
            participant_name = str(patch.get("participant_name", "")).strip()
            competition_type = str(patch.get("competition_type", "")).strip()
            category_raw = str(patch.get("category_raw", "")).strip()
            explicit_group_flag = str(patch.get("is_group_competition", "")).strip().lower()
            if explicit_group_flag not in {"true", "false"}:
                continue
            for row in patched_rows:
                matches = True
                if response_id and str(row.get("response_id", "")).strip() != response_id:
                    matches = False
                if participant_name and not _matches_text(str(row.get("participant_name", "")), participant_name):
                    matches = False
                if competition_type and not _matches_text(str(row.get("competition_type", "")), competition_type):
                    matches = False
                if category_raw and not _matches_text(str(row.get("category_raw", "")), category_raw):
                    matches = False
                if matches:
                    row["is_group_competition"] = explicit_group_flag
            continue

    return patched_rows
