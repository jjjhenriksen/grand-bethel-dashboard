from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
import json
from pathlib import Path
from typing import Any

import pandas as pd

from assignment_logic import build_assignment_rows
from bethel_overrides import load_overrides
from build_dashboard import (
    _render_competition_dashboard,
    _render_conflict_cards,
    _render_family_cards,
    _render_kv,
    _program_audience_tag,
    _render_program_table,
    _render_table,
    _render_validation_table,
)

ROOT = Path(__file__).resolve().parent.parent
BETHEL_OVERRIDES_PATH = ROOT / "config" / "bethel_overrides.yaml"


STATE: dict[str, Any] = {
    "now": None,
    "program_blocks": [],
    "personal_program_blocks": [],
    "block_assignments": [],
    "operational_duties": {},
    "families": [],
    "competitions": {"entries": [], "rosters": []},
    "conflicts": [],
    "assignments": [],
}


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


def _parse_clock_on_date(date_text: object, time_text: object) -> datetime | None:
    clean_date = str(date_text or "").strip()
    clean_time = str(time_text or "").strip().lower().replace(" ", "")
    if not clean_date or not clean_time:
        return None
    for fmt in ("%Y-%m-%d %I:%M%p", "%Y-%m-%d %I%p"):
        try:
            return datetime.strptime(f"{clean_date} {clean_time}", fmt)
        except ValueError:
            continue
    return None


def _humanize(value: object) -> str:
    return str(value or "").strip().replace("_", " ").title()


def _owner_for_block(row: dict) -> str:
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


def _assignment_urgency(now: datetime, event_dt: datetime | None) -> str:
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


def _program_load_density(program_blocks: list[dict]) -> dict[str, str]:
    counts: dict[str, int] = {}
    for row in program_blocks:
        day = str(row.get("day_label", "")).strip()
        if day:
            counts[day] = counts.get(day, 0) + 1
    density: dict[str, str] = {}
    for day, count in counts.items():
        if count >= 12:
            density[day] = "high"
        elif count >= 6:
            density[day] = "medium"
        else:
            density[day] = "low"
    return density


def _program_concurrency(program_blocks: list[dict]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in program_blocks:
        key = (
            str(row.get("day_label", "")).strip(),
            str(row.get("time_raw", "")).strip(),
        )
        if not key[0] or not key[1]:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _program_risk_level(row: dict, concurrent_events_count: int, load_density: str) -> str:
    event_type = str(row.get("event_type", "")).strip().lower()
    title = str(row.get("event_title", "")).strip().lower()
    operational = event_type in {"competition_related", "logistics", "meal_or_social", "bethel_local"} or "registration" in title
    if concurrent_events_count >= 3:
        return "high"
    if concurrent_events_count == 2 and operational:
        return "high"
    if load_density == "high" and operational:
        return "high"
    if concurrent_events_count == 2 or load_density == "medium":
        return "medium"
    return "low"


def _family_flags(family: dict) -> list[str]:
    flags: list[str] = []
    if not str(family.get("emergency_contact_name", "")).strip():
        flags.append("missing_emergency_contact")
    if str(family.get("allergies_raw", "")).strip() and str(family.get("allergies_raw", "")).strip().lower() not in {"no", "none"}:
        flags.append("allergies_listed")
    if int(family.get("attendee_count_total", 0) or 0) >= 5:
        flags.append("large_family")
    return flags


def _load_block_assignments() -> list[dict]:
    overrides = load_overrides(BETHEL_OVERRIDES_PATH)
    assignments = overrides.get("block_assignments", []) or []
    return [
        {
            "block_id": str(item.get("block_id", "")).strip(),
            "assignment": str(item.get("assignment", "")).strip().lower(),
            "people": [str(person).strip() for person in item.get("people", []) if str(person).strip()],
        }
        for item in assignments
        if str(item.get("block_id", "")).strip() and str(item.get("assignment", "")).strip()
    ]


def _block_group_key(row: dict) -> tuple[str, str]:
    return (
        str(row.get("day_label", "")).strip(),
        str(row.get("time_raw", "")).strip(),
    )


def _apply_block_assignments(program_blocks: list[dict], block_assignments: list[dict]) -> tuple[list[dict], dict[str, Any]]:
    assignment_by_block = {
        str(item.get("block_id", "")).strip(): item
        for item in block_assignments
        if str(item.get("assignment", "")).strip().lower() == "guard_duty"
    }
    if not assignment_by_block:
        return list(program_blocks), {"guard_duty_count": 0, "blocks_replaced": 0, "guard_duty_wu": 0, "attendance": []}

    grouped_blocks: dict[tuple[str, str], list[dict]] = {}
    group_order: list[tuple[str, str]] = []
    for row in program_blocks:
        key = _block_group_key(row)
        if key not in grouped_blocks:
            grouped_blocks[key] = []
            group_order.append(key)
        grouped_blocks[key].append(dict(row))

    personal_blocks: list[dict] = []
    attendance_rows: list[str] = []
    guard_duty_count = 0
    blocks_replaced = 0

    # Personal schedule overrides replace the visible session block while leaving the
    # base program schedule untouched for reference and summary calculations.
    for key in group_order:
        rows = grouped_blocks[key]
        matched_assignment = next(
            (assignment_by_block.get(str(row.get("block_id", "")).strip()) for row in rows if str(row.get("block_id", "")).strip() in assignment_by_block),
            None,
        )
        if not matched_assignment:
            personal_blocks.extend(rows)
            continue

        first_row = rows[0]
        guard_duty_count += 1
        blocks_replaced += 1
        replaced_titles = [str(row.get("event_title", "")).strip() for row in rows if str(row.get("event_title", "")).strip()]
        people = matched_assignment.get("people", []) or []
        attendance_rows.append(
            f"{str(first_row.get('day_name', '')).strip() or str(first_row.get('day_label', '')).strip()} {str(first_row.get('time_raw', '')).strip()}: Replaced by duty"
            f"{' (' + ', '.join(people) + ')' if people else ''}"
        )
        personal_blocks.append(
            {
                **first_row,
                "event_title": "GUARD DUTY — Assigned",
                "event_type": "operational_duty",
                "schedule_source": "personal_override",
                "override_assignment": "guard_duty",
                "assigned_people": " | ".join(people),
                "replaced_event_titles": " | ".join(replaced_titles),
                "attendance_note": "Assigned to Guard Duty — session attendance not expected",
                # Work units are counted at the transformed personal-view block level so
                # replaced session blocks are not double-counted alongside guard duty.
                "work_unit": 1,
            }
        )

    return personal_blocks, {
        "guard_duty_count": guard_duty_count,
        "blocks_replaced": blocks_replaced,
        "guard_duty_wu": guard_duty_count,
        "attendance": attendance_rows,
    }


def _derive_assignments(program_blocks_df: pd.DataFrame, now: datetime) -> list[dict]:
    return build_assignment_rows(program_blocks_df, now)


def _derive_open_issues(flags_df: pd.DataFrame, competition_event_rosters_df: pd.DataFrame) -> list[dict]:
    issues: list[dict] = []
    if not flags_df.empty:
        for _, row in flags_df.fillna("").iterrows():
            severity = "High" if str(row.get("severity", "")).lower() == "error" else "Medium"
            issues.append(
                {
                    "title": _humanize(row.get("issue_type", "")),
                    "severity": severity,
                    "owner": "Registrar",
                    "detail": str(row.get("issue_detail", "")).strip(),
                }
            )
    if not competition_event_rosters_df.empty:
        unscheduled = competition_event_rosters_df.fillna("")
        unscheduled = unscheduled[unscheduled["schedule_status"] == "unscheduled_in_program"]
        for _, row in unscheduled.iterrows():
            issues.append(
                {
                    "title": "Competition Needs Mapping",
                    "severity": "High",
                    "owner": "Competition Lead",
                    "detail": f"{row.get('participant_name', '')} - {row.get('competition_type', '')}",
                }
            )
    return issues


def _derive_conflicts(participant_conflicts_df: pd.DataFrame, now: datetime) -> list[dict]:
    if participant_conflicts_df.empty:
        return []
    rows: list[dict] = []
    for _, row in participant_conflicts_df.fillna("").iterrows():
        competition_labels = [part.strip().replace("_", " ").title() for part in str(row.get("competition_types", "")).split("|") if part.strip()]
        event_dt = _parse_event_datetime(row.get("event_date", ""), row.get("time_raw", ""))
        resolution_state = str(row.get("resolution_state", "")).strip().lower() or "unresolved"
        priority = "later"
        if event_dt and event_dt <= now + timedelta(hours=6):
            priority = "critical"
        elif event_dt and event_dt <= now + timedelta(hours=48):
            priority = "soon"
        escalation_logic = "monitor"
        if resolution_state != "resolved" and event_dt and event_dt <= now + timedelta(hours=48):
            escalation_logic = "escalate"
        rows.append(
            {
                **row.to_dict(),
                "status": str(row.get("status", "")).strip() or "Unresolved",
                "resolution_note": str(row.get("resolution_note", "")).strip(),
                "chosen_event": str(row.get("chosen_event", "")).strip(),
                "resolution_type": str(row.get("resolution_type", "")).strip() or "needs_decision",
                "resolution_state": resolution_state,
                "priority": priority,
                "escalation_logic": escalation_logic,
                "conflict_pair": " vs ".join(competition_labels[:2]) if competition_labels else "Multiple entries",
            }
        )
    return rows


def _block_window(row: dict) -> tuple[datetime | None, datetime | None]:
    event_date = row.get("event_date", "")
    start_time = row.get("start_time_raw", "") or str(row.get("time_raw", "")).split("-", 1)[0].strip()
    end_time = row.get("end_time_raw", "")
    start_dt = _parse_clock_on_date(event_date, start_time)
    end_dt = _parse_clock_on_date(event_date, end_time)
    if start_dt and not end_dt:
        end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def getCurrentContext(now: datetime, program_blocks: list[dict]) -> dict[str, Any]:
    windows = []
    for row in program_blocks:
        start_dt, end_dt = _block_window(row)
        if start_dt:
            windows.append((start_dt, end_dt, row))
    windows.sort(key=lambda item: item[0])
    if not windows:
        return {"current_block": {}, "next_block": {}, "deadlines": [], "state": "unknown", "now": now}

    earliest_start = windows[0][0]
    latest_end = max((end or start) for start, end, _ in windows)
    current_block = next((row for start, end, row in windows if end and start <= now <= end), {})
    next_block = next((row for start, _, row in windows if start >= now), windows[0][2] if windows else {})
    if now < earliest_start:
        state = "before"
    elif now > latest_end:
        state = "after"
    elif current_block:
        state = "active"
    else:
        state = "between"
    baseline = now if state in {"before", "active", "between"} else latest_end
    deadlines = [
        row
        for start, _, row in windows
        if baseline <= start <= baseline + timedelta(hours=48)
    ][:3]
    return {
        "current_block": current_block,
        "next_block": next_block,
        "deadlines": deadlines,
        "state": state,
        "now": now,
        "program_start": earliest_start,
        "program_end": latest_end,
    }


def getContext(state: dict[str, Any]) -> dict[str, Any]:
    return getCurrentContext(state.get("now") or datetime.now(), state.get("program_blocks", []))


def _planning_phase_label(context: dict[str, Any]) -> tuple[str, str]:
    state = context.get("state")
    now_dt = context.get("now")
    program_start = context.get("program_start")
    if state == "before" and now_dt and program_start:
        days = max((program_start.date() - now_dt.date()).days, 0)
        return (f"Planning Phase: Pre-Event (T-{days} days)", "Status: No active program blocks")
    if state == "after":
        return ("Planning Phase: Post-Event", "Status: No active program blocks")
    return ("Program Phase: Live Session", "Status: No active program blocks")


def _render_summary_entry(row: dict, empty_label: str, *, include_owner: bool = False) -> str:
    if not row:
        return (
            f"<article class='summary-card'><h3>{escape(empty_label)}</h3>"
            "<p class='subtle'>No active program block at this time.</p></article>"
        )
    meta = [
        str(row.get("day_name", "")).strip() or str(row.get("day_label", "")).strip(),
        str(row.get("time_raw", "")).strip(),
    ]
    if include_owner:
        meta.append(_owner_for_block(row))
    meta_bits = " | ".join(bit for bit in meta if bit)
    return (
        f"<article class='summary-card'><h3>{escape(empty_label)}</h3>"
        f"<p><strong>{escape(str(row.get('event_title', '')))}</strong></p>"
        f"<p class='summary-meta'>{escape(meta_bits)}</p></article>"
    )


def renderNowNextCritical(context: dict[str, Any], *, include_owner: bool = False) -> str:
    if not context or context.get("state") == "unknown":
        return "<section class='panel'><h2>Now / Next / Critical</h2><p class='empty'>Program timing is not available.</p></section>"

    now_dt = context["now"]
    state = context["state"]
    current_block = context.get("current_block", {})
    next_block = context.get("next_block", {})
    deadlines = context.get("deadlines", [])
    earliest_start = context.get("program_start")
    latest_end = context.get("program_end")
    pre_event_mode = state == "before"
    current_label = "Current Planning State" if pre_event_mode else "Now"
    next_label = "Next Scheduled Block" if pre_event_mode else "Next"
    critical_label = "Upcoming Deadlines" if pre_event_mode else "Critical"
    critical_html = "".join(
        f"<li><strong>{escape(str(row.get('event_title', '')))}</strong> <span class='subtle'>({escape((str(row.get('day_name', '')).strip() or str(row.get('day_label', '')).strip()) + ' | ' + str(row.get('time_raw', '')).strip())})</span></li>"
        for row in deadlines
    )
    if not critical_html:
        if state == "before":
            critical_html = "<li>Deadlines will populate as Grand Bethel approaches.</li>"
        elif state == "after":
            critical_html = "<li>No remaining program deadlines.</li>"
        else:
            critical_html = "<li>No deadlines in the next 48 hours.</li>"
    if state == "before":
        current_message = "Grand Bethel has not started yet."
        phase_line, status_line = _planning_phase_label(context)
        context_note = (
            f"<p class='summary-note'>Current date: {escape(now_dt.strftime('%B %d, %Y'))}. "
            f"Program begins {escape(earliest_start.strftime('%B %d, %Y'))}.</p>"
        )
    elif state == "after":
        current_message = "Grand Bethel has concluded."
        phase_line, status_line = _planning_phase_label(context)
        context_note = (
            f"<p class='summary-note'>Current date: {escape(now_dt.strftime('%B %d, %Y'))}. "
            f"Program ended {escape(latest_end.strftime('%B %d, %Y'))}.</p>"
        )
    else:
        current_message = "No active program block at this time."
        phase_line, status_line = _planning_phase_label(context)
        context_note = f"<p class='summary-note'>Today: {escape(now_dt.strftime('%A, %B %d, %Y'))}</p>"
    next_time_note = ""
    if next_block:
        next_day = str(next_block.get("day_name", "")).strip() or str(next_block.get("day_label", "")).strip()
        next_time = str(next_block.get("time_raw", "")).strip()
        if pre_event_mode and (next_day or next_time):
            next_time_note = f"<p class='summary-meta'>First scheduled program block: {escape(' | '.join(bit for bit in [next_day, next_time] if bit))}</p>"
        elif next_time:
            next_time_note = f"<p class='summary-meta'>Next block begins at {escape(next_time)}.</p>"
    current_card_html = (
        f"<article class='summary-card'><h3>{escape(current_label)}</h3>"
        f"<p>{escape(current_message)}</p>"
        f"<p class='summary-meta'>{escape(phase_line)}</p>"
        f"<p class='summary-meta'>{escape(status_line)}</p>"
        f"{next_time_note}"
        "</article>"
    )
    fallback_note = (
        "<p class='summary-note'>Using the nearest upcoming program window from the generated schedule.</p>"
        if not current_block and state != "after"
        else ""
    )
    return (
        "<section class='panel'><h2>Now / Next / Critical</h2>"
        "<div class='summary-grid'>"
        f"{_render_summary_entry(current_block, current_label, include_owner=include_owner) if current_block else current_card_html}"
        f"{_render_summary_entry(next_block, next_label, include_owner=include_owner)}"
        f"<article class='summary-card'><h3>{escape(critical_label)}</h3><ul class='action-list'>{critical_html}</ul></article>"
        "</div>"
        f"{context_note}"
        f"{fallback_note}"
        "</section>"
    )


def _derive_operational_signals(program_blocks: list[dict], operational_duties: dict[str, Any] | None = None) -> list[str]:
    if not program_blocks:
        return []
    signals: list[str] = []
    operational_duties = operational_duties or {}
    by_day: dict[str, list[dict]] = {}
    for row in program_blocks:
        by_day.setdefault(str(row.get("day_name", "")).strip() or str(row.get("day_label", "")).strip(), []).append(row)

    if by_day:
        peak_day, peak_rows = max(by_day.items(), key=lambda item: len(item[1]))
        signals.append(f"{peak_day} is peak program density with {len(peak_rows)} scheduled blocks.")

    intake_days = []
    for day, rows in by_day.items():
        intake_count = sum(
            1
            for row in rows
            if str(row.get("event_type", "")).strip().lower() == "logistics"
            or "registration" in str(row.get("event_title", "")).strip().lower()
            or "turn in" in str(row.get("event_title", "")).strip().lower()
        )
        if intake_count >= 2:
            intake_days.append((day, intake_count))
    for day, intake_count in intake_days[:2]:
        signals.append(f"{day} is intake-heavy with {intake_count} registration or turn-in blocks.")

    overlap_groups: dict[tuple[str, str], list[dict]] = {}
    for row in program_blocks:
        key = (
            str(row.get("day_name", "")).strip() or str(row.get("day_label", "")).strip(),
            str(row.get("time_raw", "")).strip(),
        )
        if all(key):
            overlap_groups.setdefault(key, []).append(row)
    for (day, time_raw), rows in overlap_groups.items():
        competitor_rows = [row for row in rows if _program_audience_tag(row) == "Competitors"]
        if len(competitor_rows) >= 2:
            signals.append(f"{day} {time_raw} has a competitor load conflict with {len(competitor_rows)} concurrent competition events.")
            break

    if int(operational_duties.get("guard_duty_count", 0) or 0) > 0:
        signals.append(f"Guard Duty replaces {int(operational_duties.get('blocks_replaced', 0) or 0)} session block(s).")
        signals.append("Schedule flexibility reduced.")
        signals.append("Load redistributed rather than increased.")

    return signals


def _audience_load_summary(program_blocks: list[dict]) -> dict[str, list[str]]:
    by_day: dict[str, list[dict]] = {}
    for row in program_blocks:
        day = str(row.get("day_name", "")).strip() or str(row.get("day_label", "")).strip()
        if day:
            by_day.setdefault(day, []).append(row)

    summary: dict[str, list[str]] = {}
    for day, rows in by_day.items():
        total = len(rows) or 1
        counts = {
            "All Daughters": sum(1 for row in rows if _program_audience_tag(row) == "All Daughters"),
            "Competitors": sum(1 for row in rows if _program_audience_tag(row) == "Competitors"),
            "Families": sum(1 for row in rows if _program_audience_tag(row) == "Families"),
        }
        items: list[str] = []
        for label, count in counts.items():
            if count <= 0:
                continue
            ratio = count / total
            level = "High involvement" if ratio >= 0.45 else "Peak load" if label == "Competitors" and ratio >= 0.3 else "Medium visibility" if ratio >= 0.25 else "Light"
            items.append(f"{label}: {level}")
        summary[day] = items
    return summary


def _render_operational_signals(program_blocks: list[dict], operational_duties: dict[str, Any] | None = None) -> str:
    signals = _derive_operational_signals(program_blocks, operational_duties)
    if not signals:
        return "<p class='empty'>No operational signals yet.</p>"
    items = "".join(f"<li>{escape(signal)}</li>" for signal in signals)
    return f"<ul class='action-list'>{items}</ul>"


def _render_operational_duties_summary(operational_duties: dict[str, Any]) -> str:
    if not operational_duties or int(operational_duties.get("guard_duty_count", 0) or 0) == 0:
        return "<p class='empty'>No operational duty overrides.</p>"
    attendance_rows = operational_duties.get("attendance", []) or []
    attendance_html = "".join(f"<li>{escape(item)}</li>" for item in attendance_rows) or "<li>No attendance changes.</li>"
    return (
        f"{_render_kv([('Guard Duty', operational_duties.get('guard_duty_count', 0)), ('Blocks replaced', operational_duties.get('blocks_replaced', 0)), ('Guard Duty WU', operational_duties.get('guard_duty_wu', 0))])}"
        "<div class='day-card-block'><span class='family-detail-label'>Attendance</span>"
        f"<ul class='action-list'>{attendance_html}</ul></div>"
    )


def _render_upcoming_program_preview(program_blocks_df: pd.DataFrame, limit: int = 5) -> str:
    if isinstance(program_blocks_df, pd.DataFrame):
        rows = program_blocks_df.fillna("").to_dict(orient="records")
    else:
        rows = list(program_blocks_df or [])
    if not rows:
        return "<p class='empty'>No program rows.</p>"
    rows = sorted(
        rows,
        key=lambda row: (_block_window(row)[0] or datetime.max),
    )
    upcoming = rows[:limit]
    if not upcoming:
        return "<p class='empty'>No program rows.</p>"
    grouped: dict[str, list[dict]] = {}
    for row in upcoming:
        day = str(row.get("day_label", "")).strip() or "Upcoming"
        grouped.setdefault(day, []).append(row)
    sections = []
    for day, day_rows in grouped.items():
        preview_items = []
        for row in day_rows:
            risk_tag = " <span class='source-tag'>high density</span>" if str(row.get("risk_level", "")).strip() == "high" else ""
            preview_items.append(
                f"<li><strong>{escape(str(row.get('time_raw', '')).strip() or 'Time TBD')}</strong> {escape(str(row.get('event_title', '')).strip())}{risk_tag}</li>"
            )
        items = "".join(
            preview_items
        )
        sections.append(
            "<div class='preview-day'>"
            f"<span class='family-detail-label'>{escape(day)}</span>"
            f"<ul class='action-list'>{items}</ul>"
            "</div>"
        )
    return "".join(sections)


def _render_assignment_lists(assignments: list[dict]) -> str:
    if not assignments:
        return "<ul class='action-list'><li>No assignments.</li></ul>"
    ordered = sorted(assignments, key=lambda item: (item.get("sort_key", ""), item.get("day", ""), item.get("time_window", "") or item.get("time", ""), item.get("title", "")))
    primary = ordered[:5]
    later = ordered[5:]
    primary_html = "".join(
        f"<li><strong>{escape(item['title'])}</strong> <span class='subtle'>({escape(item['day'])} {escape(str(item.get('time_window', '') or item.get('time', '')))}, {escape(item['owner'])})</span>"
        f" <span class='source-tag'>{escape(str(item.get('urgency', 'later')).replace('_', ' '))}</span>"
        f" <span class='source-tag'>{escape(str(item.get('status', 'pending')).replace('_', ' '))}</span></li>"
        for item in primary
    ) or "<li>No assignments.</li>"
    if not later:
        return f"<ul class='action-list'>{primary_html}</ul>"
    later_html = "".join(
        f"<li><strong>{escape(item['title'])}</strong> <span class='subtle'>({escape(item['day'])} {escape(str(item.get('time_window', '') or item.get('time', '')))}, {escape(item['owner'])})</span>"
        f" <span class='source-tag'>{escape(str(item.get('urgency', 'later')).replace('_', ' '))}</span>"
        f" <span class='source-tag'>{escape(str(item.get('status', 'pending')).replace('_', ' '))}</span></li>"
        for item in later
    )
    return (
        f"<ul class='action-list'>{primary_html}</ul>"
        "<details class='later-block'><summary>Later</summary>"
        f"<ul class='action-list'>{later_html}</ul>"
        "</details>"
    )


def _render_execution_buckets(assignments: list[dict], conflicts: list[dict]) -> str:
    assignment_buckets = [
        ("Now", [item for item in assignments if item.get("urgency") == "now" and item.get("status") != "done"]),
        ("Today", [item for item in assignments if item.get("urgency") == "today" and item.get("status") != "done"]),
        ("Upcoming", [item for item in assignments if item.get("urgency") == "upcoming" and item.get("status") != "done"]),
    ]
    assignment_cards = []
    for label, rows in assignment_buckets:
        items = "".join(
            f"<li><strong>{escape(str(item.get('title', '')))}</strong> <span class='subtle'>({escape(str(item.get('day', '')))} {escape(str(item.get('time_window', '') or item.get('time', '')))}, {escape(str(item.get('owner', '')))})</span></li>"
            for item in rows[:5]
        ) or "<li>No assignments.</li>"
        assignment_cards.append(f"<article class='mini-card'><h3>{escape(label)}</h3><ul class='action-list'>{items}</ul></article>")

    conflict_buckets = [
        ("Critical Conflicts", [item for item in conflicts if item.get("priority") == "critical"]),
        ("Soon Conflicts", [item for item in conflicts if item.get("priority") == "soon"]),
        ("Later Conflicts", [item for item in conflicts if item.get("priority") == "later"]),
    ]
    conflict_cards = []
    for label, rows in conflict_buckets:
        items = "".join(
            f"<li><strong>{escape(str(item.get('participant_name', 'Unknown participant')))}</strong> <span class='subtle'>({escape(str(item.get('conflict_pair', 'Multiple entries')))}, {escape(str(item.get('resolution_state', 'unresolved')).replace('_', ' '))})</span></li>"
            for item in rows[:5]
        ) or "<li>No conflicts.</li>"
        conflict_cards.append(f"<article class='mini-card'><h3>{escape(label)}</h3><ul class='action-list'>{items}</ul></article>")

    return (
        "<section class='panel'><h2>Execution Buckets</h2>"
        "<div class='card-grid'>"
        f"{''.join(assignment_cards)}"
        f"{''.join(conflict_cards)}"
        "</div></section>"
    )


def _build_state(
    now: datetime,
    program_blocks_df: pd.DataFrame,
    assignments_df: pd.DataFrame,
    families_df: pd.DataFrame,
    attendees_df: pd.DataFrame,
    competitions_df: pd.DataFrame,
    competition_event_rosters_df: pd.DataFrame,
    participant_conflicts_df: pd.DataFrame,
) -> dict[str, Any]:
    program_blocks = program_blocks_df.fillna("").to_dict(orient="records") if not program_blocks_df.empty else []
    density_map = _program_load_density(program_blocks)
    concurrency_map = _program_concurrency(program_blocks)
    for row in program_blocks:
        load_density = density_map.get(str(row.get("day_label", "")).strip(), "low")
        concurrency = concurrency_map.get(
            (
                str(row.get("day_label", "")).strip(),
                str(row.get("time_raw", "")).strip(),
            ),
            1,
        )
        row["load_density"] = load_density
        row["concurrent_events_count"] = concurrency
        explicit_risk = str(row.get("risk_level", "")).strip().lower()
        row["risk_level"] = explicit_risk or _program_risk_level(row, concurrency, load_density)

    block_assignments = _load_block_assignments()
    personal_program_blocks, operational_duties = _apply_block_assignments(program_blocks, block_assignments)

    families = families_df.fillna("").to_dict(orient="records") if not families_df.empty else []
    for family in families:
        family["family_flags"] = _family_flags(family)

    assignments = assignments_df.fillna("").to_dict(orient="records") if not assignments_df.empty else _derive_assignments(program_blocks_df, now)
    conflicts = _derive_conflicts(participant_conflicts_df, now)

    return {
        "now": now,
        "program_blocks": program_blocks,
        "personal_program_blocks": personal_program_blocks,
        "block_assignments": block_assignments,
        "operational_duties": operational_duties,
        "families": families,
        "competitions": {
            "entries": competitions_df.fillna("").to_dict(orient="records") if not competitions_df.empty else [],
            "rosters": competition_event_rosters_df.fillna("").to_dict(orient="records") if not competition_event_rosters_df.empty else [],
        },
        "conflicts": conflicts,
        "assignments": assignments,
    }


def _render_day_summary_cards(daily_program_summary_df: pd.DataFrame, program_blocks: list[dict]) -> str:
    if daily_program_summary_df.empty:
        return "<p class='subtle'>No daily summary.</p>"

    working = daily_program_summary_df.fillna("").copy()
    event_dates = working["event_date"].astype(str).str.strip() if "event_date" in working.columns else pd.Series(dtype=str)
    real_days = working[event_dates != ""].copy()
    planning_buckets = working[event_dates == ""].copy()
    audience_summary = _audience_load_summary(program_blocks)

    cards: list[str] = []
    for _, row in real_days.iterrows():
        day_key = str(row.get("day_label", "Day")).split(",")[0].strip()
        highlights = [item.strip() for item in str(row.get("operational_highlights", "")).split("|") if item.strip()]
        highlight_items = "".join(f"<li>{escape(item)}</li>" for item in highlights[:5]) or "<li>No highlighted moments.</li>"
        audience_items = "".join(f"<li>{escape(item)}</li>" for item in audience_summary.get(day_key, [])[:3])
        audience_block = (
            f"<div class='day-card-block'><span class='family-detail-label'>Audience Load</span><ul class='action-list'>{audience_items}</ul></div>"
            if audience_items
            else ""
        )
        cards.append(
            "<article class='day-card'>"
            f"<h3>{escape(str(row.get('day_label', 'Day')))}</h3>"
            f"<p class='day-card-date'>{escape(str(row.get('event_date', '')))}</p>"
            f"<div class='day-card-block'><span class='family-detail-label'>Key Moments</span><ul class='action-list'>{highlight_items}</ul></div>"
            f"{audience_block}"
            f"{_render_kv([('Program events', row.get('program_event_count', 0)), ('Competition participants', row.get('competition_participant_count', 0)), ('Excursion families', row.get('excursion_family_count', 0))])}"
            f"<div class='day-card-block'><span class='family-detail-label'>Excursions</span><div>{escape(str(row.get('excursion_options', 'None listed')) or 'None listed')}</div></div>"
            "</article>"
        )

    bucket_html = ""
    if not planning_buckets.empty:
        bucket_rows = []
        for _, row in planning_buckets.iterrows():
            bucket_rows.append(
                {
                    "Bucket": row.get("day_label", ""),
                    "Excursion families": row.get("excursion_family_count", 0),
                    "Excursion options": row.get("excursion_options", ""),
                }
            )
        bucket_df = pd.DataFrame(bucket_rows)
        bucket_html = (
            "<section class='panel'>"
            "<h2>Planning Buckets</h2>"
            "<p class='subtle'>These are useful planning groups, but they are not single scheduled session days.</p>"
            f"{_render_table(bucket_df)}"
            "</section>"
        )

    if not cards:
        return bucket_html or "<p class='subtle'>No daily summary.</p>"
    return f"<div class='day-card-grid'>{''.join(cards)}</div>{bucket_html}"


def _js_string(value: str) -> str:
    return json.dumps(value)


def _site_shell(title: str, subtitle: str, current_page: str, content: str, generated_at: str) -> str:
    nav = [
        ("index.html", "Home"),
        ("operations.html", "Operations"),
        ("program.html", "Program"),
        ("competitions.html", "Competitions"),
        ("families.html", "Families"),
    ]
    nav_html = "".join(
        f"<a class='nav-chip{' current' if href == current_page else ''}' href='{escape(href)}'>{escape(label)}</a>"
        for href, label in nav
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f2ff;
      --bg-accent: #e7dbff;
      --panel: rgba(255, 255, 255, 0.94);
      --panel-strong: #ffffff;
      --ink: #261a3b;
      --muted: #6e5a95;
      --line: #d8c7f1;
      --line-strong: #b89be4;
      --chip: #efe5ff;
      --chip-text: #563a8c;
      --shadow: rgba(88, 57, 138, 0.12);
      --time-bg: #f3ebff;
      --dress-bg: #faf7ff;
      --tag-bg: #eee3ff;
      --tag-text: #5a3f8f;
    }}
    :root[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #171122;
      --bg-accent: #26163d;
      --panel: rgba(32, 22, 49, 0.92);
      --panel-strong: #241735;
      --ink: #f5efff;
      --muted: #cdbef2;
      --line: #56427d;
      --line-strong: #7a5fb2;
      --chip: #352252;
      --chip-text: #f2eaff;
      --shadow: rgba(0, 0, 0, 0.34);
      --time-bg: #312048;
      --dress-bg: #281b3b;
      --tag-bg: #3b2858;
      --tag-text: #eadbff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, var(--bg-accent), transparent 34%),
        linear-gradient(180deg, var(--bg-accent) 0%, var(--bg) 36%, var(--bg) 100%);
    }}
    a {{ color: inherit; }}
    .page-shell {{ max-width: 1380px; margin: 0 auto; padding: 24px 18px 56px; }}
    .masthead {{
      position: sticky;
      top: 0;
      z-index: 20;
      margin-bottom: 18px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: color-mix(in srgb, var(--panel) 94%, transparent);
      backdrop-filter: blur(18px);
      box-shadow: 0 12px 28px var(--shadow);
    }}
    .masthead-row {{ display:flex; gap:16px; align-items:center; justify-content:space-between; flex-wrap:wrap; }}
    .title-wrap h1 {{ margin:0; font-size: clamp(1.8rem, 3vw, 2.5rem); }}
    .title-wrap p {{ margin:6px 0 0; color:var(--muted); max-width:74ch; }}
    .theme-toggle {{
      border:1px solid var(--line-strong);
      background:var(--panel-strong);
      color:var(--ink);
      border-radius:999px;
      padding:10px 14px;
      font:inherit;
      cursor:pointer;
    }}
    .jump-nav {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
    .status-row {{
      display:flex;
      justify-content:space-between;
      gap:12px;
      flex-wrap:wrap;
      margin-top:14px;
      padding-top:14px;
      border-top:1px solid var(--line);
    }}
    .live-status {{
      display:inline-flex;
      align-items:center;
      gap:8px;
      padding:8px 12px;
      border-radius:999px;
      border:1px solid var(--line);
      background:color-mix(in srgb, var(--panel-strong) 88%, transparent);
      font-size:13px;
    }}
    .live-dot {{
      width:10px;
      height:10px;
      border-radius:50%;
      background:#2f9e44;
      box-shadow:0 0 0 4px color-mix(in srgb, #2f9e44 18%, transparent);
    }}
    .live-status.is-syncing .live-dot {{ background:#f59f00; box-shadow:0 0 0 4px color-mix(in srgb, #f59f00 18%, transparent); }}
    .live-status.is-error .live-dot {{ background:#d9480f; box-shadow:0 0 0 4px color-mix(in srgb, #d9480f 18%, transparent); }}
    .live-meta {{ color:var(--muted); font-size:13px; }}
    .nav-chip {{
      display:inline-flex; align-items:center; justify-content:center;
      padding:8px 12px; border-radius:999px; background:var(--chip);
      color:var(--chip-text); text-decoration:none; border:1px solid var(--line); font-size:14px;
    }}
    .nav-chip.current {{ border-color: var(--line-strong); font-weight: 700; }}
    .content-grid {{ display:grid; gap:18px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 10px 26px var(--shadow);
      overflow: hidden;
    }}
    .panel h2, .panel h3 {{ margin-top: 0; }}
    .overview-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; }}
    .table-wrap {{ overflow:auto; border-radius:14px; border:1px solid var(--line); background:var(--panel-strong); }}
    table {{ border-collapse:collapse; width:100%; font-size:14px; }}
    th, td {{ border:1px solid var(--line); padding:9px 10px; text-align:left; vertical-align:top; }}
    th {{ background: color-mix(in srgb, var(--bg-accent) 58%, var(--panel-strong)); }}
    .kv th {{ width:60%; background:transparent; }}
    .action-list {{ margin:0; padding-left:18px; }}
    .action-list li + li {{ margin-top:8px; }}
    .card-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:14px; }}
    .summary-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:14px; }}
    .mini-card {{
      border:1px solid var(--line);
      border-radius:14px;
      padding:14px;
      background: color-mix(in srgb, var(--panel-strong) 90%, transparent);
    }}
    .summary-card {{
      border:1px solid var(--line);
      border-radius:14px;
      padding:14px;
      background: color-mix(in srgb, var(--panel-strong) 90%, transparent);
    }}
    .summary-card h3 {{ margin-bottom: 8px; }}
    .summary-meta {{ margin: 0; color: var(--muted); }}
    .summary-note {{ margin: 12px 2px 0; color: var(--muted); font-size: 13px; }}
    .empty {{ color: var(--muted); font-style: italic; }}
    .subtle {{ color: var(--muted); font-size: 13px; }}
    .later-block {{ margin-top: 12px; }}
    .later-block summary {{ cursor: pointer; color: var(--muted); }}
    .section-stack {{ display:grid; gap:18px; }}
    .split-grid {{ display:grid; grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.8fr); gap:18px; align-items:start; }}
    .list-preview {{ margin:0; padding-left:18px; }}
    .list-preview li + li {{ margin-top:8px; }}
    .preview-day + .preview-day {{ margin-top: 12px; }}
    .program-day + .program-day {{ margin-top: 18px; }}
    .program-day h3 {{ margin-bottom: 12px; }}
    .program-event-single {{ display:block; line-height:1.45; }}
    .program-event-group {{ margin:0; padding-left:18px; }}
    .program-event-item + .program-event-item {{
      margin-top:8px;
      padding-top:8px;
      border-top:1px solid color-mix(in srgb, var(--line) 65%, transparent);
    }}
    .program-event-title {{ font-weight:600; }}
    .program-table th:nth-child(1), .program-table td:nth-child(1) {{ width: 18%; }}
    .program-table th:nth-child(3), .program-table td:nth-child(3) {{ width: 24%; }}
    .time-cell {{ background: var(--time-bg); font-weight: 700; white-space: nowrap; vertical-align: top; }}
    .dress-cell {{ background: var(--dress-bg); vertical-align: top; min-width: 160px; }}
    .dress-pill, .source-tag, .category-badge, .family-chip, .severity-pill, .audience-tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--tag-bg) 78%, var(--panel-strong));
      color: var(--tag-text);
      font-size: 12px;
      font-weight: 700;
      line-height: 1.2;
    }}
    .source-tag {{ margin-left: 8px; text-transform: capitalize; }}
    .audience-tag {{ margin-left: 8px; background: color-mix(in srgb, var(--tag-bg) 62%, var(--panel-strong)); }}
    .audience-tag--all-daughters {{ border-color: var(--line-strong); background: color-mix(in srgb, var(--tag-bg) 82%, var(--panel-strong)); }}
    .audience-tag--competitors {{ background: color-mix(in srgb, var(--tag-bg) 72%, var(--panel-strong)); }}
    .audience-tag--families {{ background: color-mix(in srgb, var(--tag-bg) 54%, var(--panel-strong)); }}
    .roster-grid, .family-card-grid, .conflict-grid {{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap:14px;
    }}
    .roster-card, .family-card, .conflict-card {{
      border:1px solid var(--line);
      border-radius:16px;
      padding:16px;
      background: color-mix(in srgb, var(--panel-strong) 92%, transparent);
    }}
    .roster-card h3, .family-card h3, .conflict-card h3 {{ margin-bottom: 6px; }}
    .roster-meta, .family-meta, .conflict-meta {{ margin: 0 0 12px; color: var(--muted); }}
    .roster-list {{ margin:0; padding-left:18px; }}
    .roster-list.compact li + li {{ margin-top:6px; }}
    .bucket-title {{ margin: 12px 0 6px; font-size: 15px; }}
    .day-card-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:14px; }}
    .day-card {{
      border:1px solid var(--line);
      border-radius:16px;
      padding:16px;
      background: color-mix(in srgb, var(--panel-strong) 92%, transparent);
    }}
    .day-card h3 {{ margin-bottom: 4px; }}
    .day-card-date {{ margin: 0 0 12px; color: var(--muted); }}
    .day-card-block {{ margin-top: 12px; }}
    .attendee-list {{ list-style:none; margin:0; padding:0; display:grid; gap:8px; }}
    .attendee-pill {{
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:10px;
      padding:10px 12px;
      border-radius:12px;
      background: color-mix(in srgb, var(--bg-accent) 35%, var(--panel-strong));
      border: 1px solid var(--line);
    }}
    .attendee-pill.type-daughter {{ border-color: color-mix(in srgb, #c290ff 45%, var(--line)); }}
    .attendee-pill.type-adult {{ border-color: color-mix(in srgb, #85a8ff 45%, var(--line)); }}
    .attendee-meta {{ color: var(--muted); font-size: 13px; }}
    .family-card-top {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; }}
    .family-chip-row {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }}
    .family-detail-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:12px; margin-top:14px; }}
    .family-detail-label {{ display:block; margin-bottom:4px; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0.05em; }}
    .mono-cell {{
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }}
    .detail-cell {{ line-height: 1.4; overflow-wrap: anywhere; }}
    .validation-note {{ margin: 10px 2px 2px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 900px) {{
      .split-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="page-shell">
    <header class="masthead">
      <div class="masthead-row">
        <div class="title-wrap">
          <h1 id="page-title">{escape(title)}</h1>
          <p id="page-subtitle">{escape(subtitle)}</p>
        </div>
        <button class="theme-toggle" id="theme-toggle" type="button">Toggle theme</button>
      </div>
      <nav class="jump-nav">{nav_html}</nav>
      <div class="status-row">
        <div class="live-status" id="live-status"><span class="live-dot" aria-hidden="true"></span><span id="live-status-label">Live updates on</span></div>
        <div class="live-meta" id="live-meta">Generated {escape(generated_at)}</div>
      </div>
    </header>
    <div class="content-grid" id="page-content">
      {content}
    </div>
  </div>
  <script>
    (function () {{
      const root = document.documentElement;
      const button = document.getElementById("theme-toggle");
      const storageKey = "grand-bethel-dashboard-theme";
      const savedTheme = window.localStorage.getItem(storageKey);
      if (savedTheme === "light" || savedTheme === "dark") {{
        root.dataset.theme = savedTheme;
      }}
      if (button) {{
        button.addEventListener("click", function () {{
          const current = root.dataset.theme === "dark" ? "dark" : root.dataset.theme === "light" ? "light" : "";
          const next = current === "dark" ? "light" : "dark";
          root.dataset.theme = next;
          window.localStorage.setItem(storageKey, next);
        }});
      }}

      const pageName = { _js_string(current_page) };
      const pageTitle = document.getElementById("page-title");
      const pageSubtitle = document.getElementById("page-subtitle");
      const pageContent = document.getElementById("page-content");
      const liveStatus = document.getElementById("live-status");
      const liveStatusLabel = document.getElementById("live-status-label");
      const liveMeta = document.getElementById("live-meta");
      let latestVersion = { _js_string(generated_at) };

      function setStatus(mode, label, meta) {{
        if (!liveStatus || !liveStatusLabel || !liveMeta) {{
          return;
        }}
        liveStatus.classList.toggle("is-syncing", mode === "syncing");
        liveStatus.classList.toggle("is-error", mode === "error");
        liveStatusLabel.textContent = label;
        liveMeta.textContent = meta;
      }}

      async function refreshPage() {{
        try {{
          setStatus("syncing", "Checking for updates", "Looking for regenerated site data...");
          const response = await window.fetch("./site-data.json?ts=" + Date.now(), {{ cache: "no-store" }});
          if (!response.ok) {{
            throw new Error("Request failed with status " + response.status);
          }}
          const payload = await response.json();
          const nextVersion = typeof payload.generated_at === "string" ? payload.generated_at : "";
          const nextPage = payload.pages && payload.pages[pageName];
          if (!nextPage) {{
            throw new Error("Missing page payload for " + pageName);
          }}
          if (nextVersion && nextVersion !== latestVersion) {{
            latestVersion = nextVersion;
            document.title = nextPage.title || document.title;
            if (pageTitle) {{
              pageTitle.textContent = nextPage.title || "";
            }}
            if (pageSubtitle) {{
              pageSubtitle.textContent = nextPage.subtitle || "";
            }}
            if (pageContent) {{
              pageContent.innerHTML = nextPage.content || "";
            }}
            setStatus("live", "Live updates on", "Updated " + nextVersion);
            return;
          }}
          setStatus("live", "Live updates on", "Last checked " + new Date().toLocaleTimeString());
        }} catch (error) {{
          setStatus("error", "Live updates unavailable", "Serve the site over http to enable auto-refresh.");
        }}
      }}

      window.setTimeout(refreshPage, 1200);
      window.setInterval(refreshPage, 15000);
    }})();
  </script>
</body>
</html>"""


def build_site(
    output_dir: Path,
    summary: dict,
    assignments_df: pd.DataFrame,
    families_df: pd.DataFrame,
    attendees_df: pd.DataFrame,
    flags_df: pd.DataFrame,
    competitions_df: pd.DataFrame,
    meals_df: pd.DataFrame,
    excursions_df: pd.DataFrame,
    program_blocks_df: pd.DataFrame,
    competition_event_rosters_df: pd.DataFrame,
    excursion_day_rosters_df: pd.DataFrame,
    participant_conflicts_df: pd.DataFrame,
    daily_program_summary_df: pd.DataFrame,
) -> None:
    global STATE
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    generated_at = now.strftime("%Y-%m-%d %I:%M:%S %p")
    STATE = _build_state(
        now,
        program_blocks_df,
        assignments_df,
        families_df,
        attendees_df,
        competitions_df,
        competition_event_rosters_df,
        participant_conflicts_df,
    )
    context = getContext(STATE)
    assignments = STATE["assignments"]
    issues = _derive_open_issues(flags_df, competition_event_rosters_df)
    next_block = context.get("next_block", {})
    now_next_critical_public = renderNowNextCritical(context)
    now_next_critical_ops = renderNowNextCritical(context, include_owner=True)
    conflict_preview = pd.DataFrame(STATE["conflicts"]).head(4) if STATE["conflicts"] else pd.DataFrame()
    families_preview = pd.DataFrame(STATE["families"]).head(4) if STATE["families"] else pd.DataFrame()
    program_preview_html = _render_upcoming_program_preview(STATE["program_blocks"], limit=5)
    operational_signals_html = _render_operational_signals(STATE["program_blocks"], STATE["operational_duties"])
    operational_duties_html = _render_operational_duties_summary(STATE["operational_duties"])

    home_content = (
        f"{now_next_critical_public}"
        f"<section class='panel'><h2>Operational Signals</h2>{operational_signals_html}</section>"
        f"<section class='panel'><h2>Session Program</h2>{program_preview_html}</section>"
        "<section class='overview-grid'>"
        f"<section class='panel'><h2>Overview</h2>{_render_kv([('Families', summary['total_responses']), ('Attending families', summary['yes_attending_count']), ('Attendees', summary['total_attendees']), ('Program Blocks', summary.get('program_block_count', 0))])}</section>"
        f"<section class='panel'><h2>Competition Planning</h2>{_render_kv([('Scheduled', int((competition_event_rosters_df['schedule_status'] == 'scheduled').sum()) if not competition_event_rosters_df.empty else 0), ('Advance submitted', int((competition_event_rosters_df['schedule_status'] == 'submitted_in_advance').sum()) if not competition_event_rosters_df.empty else 0), ('Needs mapping', int((competition_event_rosters_df['schedule_status'] == 'unscheduled_in_program').sum()) if not competition_event_rosters_df.empty else 0)])}</section>"
        f"<section class='panel'><h2>Quick Links</h2><ul class='action-list'><li><a href='operations.html'>Operations center</a></li><li><a href='program.html'>Session program</a></li><li><a href='competitions.html'>Competition planning</a></li><li><a href='families.html'>Families</a></li></ul></section>"
        "</section>"
        f"<section class='panel'><h2>Participant Conflicts</h2>{_render_conflict_cards(conflict_preview)}</section>"
    )

    issue_items = "".join(
        f"<li><strong>{escape(issue['title'])}</strong> <span class='subtle'>({escape(issue['severity'])}, {escape(issue['owner'])})</span><br>{escape(issue['detail'])}</li>"
        for issue in issues[:12]
    ) or "<li>No open issues.</li>"
    assignment_items = _render_assignment_lists(assignments)
    operations_content = (
        f"{now_next_critical_ops}"
        "<section class='panel'><h2>Immediate Actions</h2>"
        "<div class='card-grid'>"
        f"<article class='mini-card'><h3>Next Program Block</h3>{_render_kv([('Event', next_block.get('event_title', 'None')), ('Day', next_block.get('day_name', '') or next_block.get('day_label', '')), ('Time', next_block.get('time_raw', ''))])}</article>"
        f"<article class='mini-card'><h3>Open Issues</h3><ul class='action-list'>{issue_items}</ul></article>"
        f"<article class='mini-card'><h3>Assignments</h3>{assignment_items}</article>"
        "</div></section>"
        f"{_render_execution_buckets(assignments, STATE['conflicts'])}"
        f"<section class='panel'><h2>Operational Duties</h2>{operational_duties_html}</section>"
        f"<section class='panel'><h2>Operational Signals</h2>{operational_signals_html}</section>"
        f"<section class='panel'><h2>Session Program Snapshot</h2>{program_preview_html}</section>"
        f"<section class='panel'><h2>Conflict Queue</h2>{_render_conflict_cards(pd.DataFrame(STATE['conflicts']))}</section>"
        f"<section class='panel'><h2>Validation Queue</h2>{_render_validation_table(flags_df)}</section>"
    )

    program_summary = _render_day_summary_cards(daily_program_summary_df, STATE["program_blocks"])
    program_content = (
        f"{now_next_critical_public}"
        f"<section class='panel'><h2>Personal Schedule View</h2>{_render_program_table(pd.DataFrame(STATE['personal_program_blocks']))}</section>"
        f"<section class='panel'><h2>Operational Duties</h2>{operational_duties_html}</section>"
        f"<section class='panel'><h2>Operational Signals</h2>{operational_signals_html}</section>"
        f"<section class='panel'><h2>Program</h2><p class='subtle'>This is the ground-truth session program. Personal duty overrides are shown separately above.</p>{_render_program_table(pd.DataFrame(STATE['program_blocks']))}</section>"
        f"<section class='panel'><h2>Daily Summary</h2>{program_summary}</section>"
    )

    competitions_content = (
        f"<section class='panel'><h2>Competitions</h2>{_render_competition_dashboard(pd.DataFrame(STATE['competitions']['rosters']), pd.DataFrame(STATE['competitions']['entries']))}</section>"
    )

    families_content = (
        f"<section class='panel'><h2>Families</h2>{_render_family_cards(pd.DataFrame(STATE['families']), attendees_df, meals_df)}</section>"
    )

    page_specs = {
        "index.html": {
            "title": "Grand Bethel Site",
            "subtitle": "A calmer website wrapper around the current dashboard flow, with separate pages for the operational details.",
            "content": home_content,
        },
        "operations.html": {
            "title": "Operations",
            "subtitle": "The action-oriented layer from the earlier operations dashboard, kept in the same visual language as the current site.",
            "content": operations_content,
        },
        "program.html": {
            "title": "Program",
            "subtitle": "Program blocks and daily session summary.",
            "content": program_content,
        },
        "competitions.html": {
            "title": "Competitions",
            "subtitle": "Competition rosters, submitted-in-advance entries, and mapping gaps.",
            "content": competitions_content,
        },
        "families.html": {
            "title": "Families",
            "subtitle": "Family attendance, contact details, and meal summaries.",
            "content": families_content,
        },
    }

    pages = {
        filename: _site_shell(spec["title"], spec["subtitle"], filename, spec["content"], generated_at)
        for filename, spec in page_specs.items()
    }

    for filename, html in pages.items():
        (output_dir / filename).write_text(html, encoding="utf-8")
    (output_dir / "site-data.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "pages": page_specs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
