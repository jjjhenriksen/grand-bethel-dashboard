from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from parse_program import recompute_block_fields


DEFAULT_PATCHES = {"patches": []}


SHORT_TITLE_EQUIVALENTS = {
    "Officer Practice": "Practice with the 2025-2026 Grand Bethel Officers",
    "Arts & Crafts Turn-In Deadline": "Deadline for turning in Arts & Crafts Competition Items",
    "Arts & Crafts Turn-In": "Turn in Arts & Crafts Competition Items",
    "Sew & Show Turn-In and Judging": "Sew and Show Turn in and Judging",
    "Flag Ceremony Practice": "Flag Ceremony Practice (member & chaperone)",
    "Pre-Opening": "Pre-Opening Festivities",
    "Officer Entrance": "Entrance of the 2025-2026 Grand Bethel Officers",
    "Escort of Honored Queens": "Escort of Honored Queens and Senior Princesses Formal",
    "Introduce MCJD Contestants": "Introduction of Miss California Job’s Daughter Contestants",
    "Eligible Bethels Drawing": "Drawing for Bethels eligible for 2027-2028 Grand Bethel Officer",
    "Retiring/Closing Ceremonies": "Retiring/Closing ceremonies for the 2025-2026 Grand Bethel Officers",
    "Officer Announcement": "Announcement of 2026-2027 Grand Bethel Officers Livestream",
    "Officer Luncheon": "2025-26 and 2026-27 Grand Bethel Officers Luncheon",
    "Arts & Crafts Viewing": "Arts & Crafts Competition Room open for viewing",
    "Arts & Crafts Pickup": "Pick up Arts & Crafts Competition items",
    "Adventure Park Private Event": "Adventure Park Private Event Casual Attire GB Session T-shirts are available for pre purchase",
    "With Bethel Guardian or Exec BGC": "(with Bethel Guardian OR member of the Executive BGC)",
}


def _normalize_title(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _matches_event_title(block_title: str, patch_title: str) -> bool:
    normalized_patch = _normalize_title(patch_title)
    normalized_block = _normalize_title(block_title)
    if not normalized_patch or not normalized_block:
        return False
    if normalized_patch == normalized_block:
        return True

    raw_equivalent = SHORT_TITLE_EQUIVALENTS.get(str(patch_title).strip(), "")
    if raw_equivalent and _normalize_title(raw_equivalent) == normalized_block:
        return True

    for short_title, raw_title in SHORT_TITLE_EQUIVALENTS.items():
        if _normalize_title(raw_title) == normalized_block and _normalize_title(short_title) == normalized_patch:
            return True
    return False


def load_program_patches(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_PATCHES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_PATCHES.copy()
    merged.update(loaded)
    return merged


def save_program_patches(path: Path, patches: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(patches, handle, sort_keys=False, allow_unicode=False)


def reset_program_patches(path: Path) -> dict[str, Any]:
    patches = {"patches": []}
    save_program_patches(path, patches)
    return patches


def add_patch(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    patches = load_program_patches(path)
    patches["patches"].append(patch)
    save_program_patches(path, patches)
    return patches


def summarize_program_patches(patches: dict[str, Any]) -> str:
    return f"patches={len(patches.get('patches', []))}"


def apply_program_patches(blocks: list[dict], patch_config: dict[str, Any]) -> list[dict]:
    patched = [dict(block) for block in blocks]
    for patch in patch_config.get("patches", []):
        block_id = patch.get("block_id", "")
        match_event_title = patch.get("match_event_title", "")
        action = patch.get("action", "")
        for block in patched:
            matches_block = bool(block_id) and block.get("block_id") == block_id
            matches_title = bool(match_event_title) and _matches_event_title(block.get("event_title", ""), match_event_title)
            if not (matches_block or matches_title):
                continue
            if action == "remove":
                block["_removed"] = True
            elif action == "update":
                for field, value in patch.get("fields", {}).items():
                    block[field] = value
                recompute_block_fields(block)
                block["schedule_source"] = "program_patch"
            break
    return [block for block in patched if not block.get("_removed")]
