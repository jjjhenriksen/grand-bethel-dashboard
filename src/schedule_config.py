from __future__ import annotations

from pathlib import Path
from typing import List

import yaml


DEFAULT_SCHEDULE_MAP = {
    "competition_event_keywords": {
        "variety_show": ["Variety Show"],
        "choir": ["Performing Arts Competition"],
        "performing_arts": ["Performing Arts Competition"],
        "arts_and_crafts": ["Turn in Arts & Crafts Competition Items"],
        "librarians_report": [],
        "essay": [],
        "ritual": ["Ritual Competition"],
        "sew_and_show": [
            "Sew and Show Turn in and Judging",
            "Sew & Show Fashion Show and Awards",
        ],
    },
    "advance_submission_competitions": [
        "librarians_report",
        "essay",
    ],
    "excursion_day_aliases": {
        "Wednesday on drive up": "Wednesday",
        "Thursday": "Thursday",
        "Any day of the session": "Any Day",
    },
}


def load_schedule_map(path: Path) -> dict:
    if not path.exists():
        return DEFAULT_SCHEDULE_MAP.copy()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if "competition_event_keywords" not in data:
        data["competition_event_keywords"] = {}
    if "advance_submission_competitions" not in data:
        data["advance_submission_competitions"] = DEFAULT_SCHEDULE_MAP["advance_submission_competitions"].copy()
    if "excursion_day_aliases" not in data:
        data["excursion_day_aliases"] = DEFAULT_SCHEDULE_MAP["excursion_day_aliases"].copy()
    return data


def save_schedule_map(path: Path, schedule_map: dict) -> dict:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(schedule_map, handle, sort_keys=False)
    return schedule_map


def set_competition_timing_keywords(
    path: Path,
    competition_type: str,
    event_titles: List[str],
) -> dict:
    schedule_map = load_schedule_map(path)
    keyword_map = schedule_map.setdefault("competition_event_keywords", {})
    keyword_map[str(competition_type).strip()] = [title.strip() for title in event_titles if str(title).strip()]
    return save_schedule_map(path, schedule_map)


def add_advance_submission_competition(path: Path, competition_type: str) -> dict:
    schedule_map = load_schedule_map(path)
    items = [str(value).strip() for value in schedule_map.setdefault("advance_submission_competitions", []) if str(value).strip()]
    normalized = str(competition_type).strip()
    if normalized and normalized not in items:
        items.append(normalized)
    schedule_map["advance_submission_competitions"] = sorted(items)
    return save_schedule_map(path, schedule_map)


def remove_advance_submission_competition(path: Path, competition_type: str) -> dict:
    schedule_map = load_schedule_map(path)
    normalized = str(competition_type).strip()
    schedule_map["advance_submission_competitions"] = [
        str(value).strip()
        for value in schedule_map.get("advance_submission_competitions", [])
        if str(value).strip() and str(value).strip() != normalized
    ]
    return save_schedule_map(path, schedule_map)


def summarize_competition_timing(schedule_map: dict) -> str:
    keyword_map = schedule_map.get("competition_event_keywords", {})
    lines = ["Competition timing mappings:"]
    for competition_type in sorted(keyword_map):
        titles = keyword_map.get(competition_type) or []
        if titles:
            lines.append(f"- {competition_type}: " + " | ".join(titles))
        else:
            lines.append(f"- {competition_type}: (no mapped program blocks)")
    advance_items = schedule_map.get("advance_submission_competitions", []) or []
    lines.append("")
    lines.append("Advance-submission competitions:")
    if advance_items:
        for competition_type in sorted(str(value).strip() for value in advance_items if str(value).strip()):
            lines.append(f"- {competition_type}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)
