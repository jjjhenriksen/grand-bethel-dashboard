from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_PATCHES = {"patches": []}


def load_assignment_patches(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_PATCHES.copy()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    merged = DEFAULT_PATCHES.copy()
    merged.update(loaded)
    return merged


def save_assignment_patches(path: Path, patches: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(patches, handle, sort_keys=False, allow_unicode=False)


def reset_assignment_patches(path: Path) -> dict[str, Any]:
    patches = {"patches": []}
    save_assignment_patches(path, patches)
    return patches


def add_assignment_patch(path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    patches = load_assignment_patches(path)
    patches["patches"].append(patch)
    save_assignment_patches(path, patches)
    return patches


def summarize_assignment_patches(patches: dict[str, Any]) -> str:
    return f"patches={len(patches.get('patches', []))}"

