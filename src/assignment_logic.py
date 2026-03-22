from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from typing import Any

import pandas as pd


def owner_for_block(row: dict) -> str:
    title = str(row.get("event_title", "")).lower()
    competition_related = str(row.get("event_type", "")).lower() == "competition_related"
    if "registration" in title:
        return "Registrar"
    if "lunch" in title or "luncheon" in title or "banquet" in title:
        return "Hospitality Lead"
    if "excursion" in title or "adventure park" in title:
        return "Excursions Lead"
    if competition_related or "variety show" in title or "arts & crafts" in title or "ritual" in title:
        return "Competition Lead"
    if str(row.get("event_type", "")).lower() == "bethel_local":
        return "Bethel 337 Lead"
    return "Operations Lead"


def backup_owner_for_block(row: dict) -> str:
    title = str(row.get("event_title", "")).lower()
    competition_related = str(row.get("event_type", "")).lower() == "competition_related"
    if "registration" in title:
        return "Bethel Guardian"
    if "lunch" in title or "luncheon" in title or "banquet" in title:
        return "Operations Lead"
    if competition_related:
        return "Assistant Competition Lead"
    return "Bethel Guardian"


def assignment_urgency(now: datetime, event_dt: datetime | None) -> str:
    if not event_dt:
        return "later"
    delta = event_dt - now
    hours = delta.total_seconds() / 3600
    if hours <= 0:
        return "now"
    if event_dt.date() == now.date():
        return "today"
    if hours <= 72:
        return "upcoming"
    return "later"


def _parse_event_datetime(event_date: object, time_raw: object) -> datetime | None:
    date_text = str(event_date or "").strip()
    time_text = str(time_raw or "").strip().split("-", 1)[0].strip().lower().replace(" ", "")
    if not date_text or not time_text:
        return None
    for fmt in ("%Y-%m-%d %I:%M%p", "%Y-%m-%d %I%p"):
        try:
            return datetime.strptime(f"{date_text} {time_text}", fmt)
        except ValueError:
            continue
    return None


def _assignment_id(program_block_id: str, title: str) -> str:
    digest = hashlib.sha1(f"{program_block_id}|{title}".encode("utf-8")).hexdigest()[:10]
    return f"assignment_{program_block_id.lower()}_{digest}"


def build_assignment_rows(program_blocks_df: pd.DataFrame, now: datetime) -> list[dict[str, Any]]:
    if program_blocks_df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in program_blocks_df.fillna("").iterrows():
        event_type = str(row.get("event_type", "")).strip().lower()
        title = str(row.get("event_title", "")).strip()
        if event_type not in {"competition_related", "logistics", "meal_or_social", "bethel_local"} and "registration" not in title.lower():
            continue
        event_dt = _parse_event_datetime(row.get("event_date", ""), row.get("time_raw", ""))
        owner = owner_for_block(row.to_dict())
        trigger_event = title
        assignment_title = f"Prep {title}"
        rows.append(
            {
                "assignment_id": _assignment_id(str(row.get("block_id", "")).strip() or "manual", assignment_title),
                "program_block_id": str(row.get("block_id", "")).strip(),
                "title": assignment_title,
                "category": event_type or "operations",
                "owner": owner,
                "backup_owner": backup_owner_for_block(row.to_dict()),
                "day": str(row.get("day_name", "")).strip() or str(row.get("day_label", "")).strip(),
                "time_window": (
                    f"{(event_dt - timedelta(minutes=30)).strftime('%I:%M%p').lower().lstrip('0')} - {event_dt.strftime('%I:%M%p').lower().lstrip('0')}"
                    if event_dt
                    else ""
                ),
                "trigger_event": trigger_event,
                "status": "done" if event_dt and event_dt <= now else "pending",
                "dependencies": "",
                "notes": title,
                "urgency": assignment_urgency(now, event_dt),
                "sort_key": event_dt.isoformat() if event_dt else "",
            }
        )
    return rows


def apply_assignment_patches(rows: list[dict[str, Any]], patch_config: dict[str, Any]) -> list[dict[str, Any]]:
    patched = [dict(row) for row in rows]
    for patch in patch_config.get("patches", []):
        action = str(patch.get("action", "")).strip().lower()
        assignment_id = str(patch.get("assignment_id", "")).strip()
        if action == "remove":
            patched = [row for row in patched if str(row.get("assignment_id", "")).strip() != assignment_id]
            continue
        if action == "assign":
            for row in patched:
                if str(row.get("assignment_id", "")).strip() != assignment_id:
                    continue
                for field in ["owner", "backup_owner", "status", "urgency", "notes"]:
                    if field in patch:
                        value = patch.get(field, None)
                        if value is not None:
                            row[field] = value
                break
            continue
        if action == "bulk_assign":
            match_owner = str(patch.get("match_owner", "")).strip().lower()
            replacement_owner = patch.get("owner", None)
            replacement_backup_owner = patch.get("backup_owner", None)
            if not match_owner:
                continue
            for row in patched:
                if str(row.get("owner", "")).strip().lower() == match_owner and replacement_owner is not None:
                    row["owner"] = replacement_owner
                if str(row.get("backup_owner", "")).strip().lower() == match_owner and replacement_backup_owner is not None:
                    row["backup_owner"] = replacement_backup_owner
            continue
        if action == "clear_all_owners":
            replacement_owner = patch.get("owner", None)
            replacement_backup_owner = patch.get("backup_owner", None)
            for row in patched:
                if replacement_owner is not None:
                    row["owner"] = replacement_owner
                if replacement_backup_owner is not None:
                    row["backup_owner"] = replacement_backup_owner
            continue
        if action == "add":
            candidate = {
                "assignment_id": assignment_id or _assignment_id(str(patch.get("program_block_id", "")).strip() or "manual", str(patch.get("title", "")).strip()),
                "program_block_id": str(patch.get("program_block_id", "")).strip(),
                "title": str(patch.get("title", "")).strip(),
                "category": str(patch.get("category", "")).strip() or "operations",
                "owner": str(patch.get("owner", "")).strip(),
                "backup_owner": str(patch.get("backup_owner", "")).strip(),
                "day": str(patch.get("day", "")).strip(),
                "time_window": str(patch.get("time_window", "")).strip(),
                "trigger_event": str(patch.get("trigger_event", "")).strip(),
                "status": str(patch.get("status", "")).strip() or "pending",
                "dependencies": str(patch.get("dependencies", "")).strip(),
                "notes": str(patch.get("notes", "")).strip(),
                "urgency": str(patch.get("urgency", "")).strip() or "later",
                "sort_key": str(patch.get("sort_key", "")).strip(),
            }
            if not any(str(row.get("assignment_id", "")).strip() == candidate["assignment_id"] for row in patched):
                patched.append(candidate)
    return patched
