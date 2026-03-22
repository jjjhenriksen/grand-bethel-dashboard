from __future__ import annotations

from html import escape
from pathlib import Path
import re

import pandas as pd


MEAL_LABELS = {
    "T": "Turkey Sandwich",
    "H": "Ham Sandwich",
    "C": "Chicken Strips",
    "S": "Caesar Salad",
    "V": "Caprese Sandwich",
    "P": "Child's Pizza",
}

COMPETITION_LABELS = {
    "variety_show": "Variety Show",
    "choir": "Performing Arts",
    "performing_arts": "Performing Arts",
    "arts_and_crafts": "Arts & Crafts",
    "librarians_report": "Librarian's Report",
    "essay": "Essay",
    "ritual": "Ritual",
    "sew_and_show": "Sew & Show",
}

COMPETITION_SUBTYPE_LABELS = {
    "choir": "Choir",
    "performing_arts": "General",
}

ARTS_AND_CRAFTS_CATEGORY_LABELS = {
    "1": "Cat. 1",
    "2": "Cat. 2",
    "3": "Cat. 3",
    "4": "Cat. 4",
    "5": "Cat. 5",
    "6": "Cat. 6",
    "7": "Cat. 7",
    "8": "Cat. 8",
    "2/7": "Cat. 2/7",
}

ARTS_AND_CRAFTS_CATEGORY_TOOLTIPS = {
    "1": "Handcrafts: Fired Ceramic, Painted Plaster, Modeling Clay, Paper Mache/Decoupage, Woodcarving, Jewelry Making, Metalwork, Glassworks",
    "2": "Painting and Drawing (Traditional): Oil and Acrylic, Watercolor, Pastels, Pen/Pencil/Ink Sketches",
    "3": "Handiwork and Needlework: Knitting/Crochet, Latchhook and Macrame, Needlepoint/Embroidery, Flower Arranging",
    "4": "Photography: Black and White Portrait, Black and White Landscape, Black and White Color Accents, Color Portrait, Color Landscape",
    "5": "Fabric Crafts: Decorated Clothing, Stuffed Toys, Quilts, Accessory Items (different than Sew and Show)",
    "6": "Paper Crafts: Scrapbook Page, Collage, Other",
    "7": "Digital Arts: Drawing and Painting, Mixed Media, 3D Modelling",
    "8": "Miscellaneous: Pinterest Inspired",
    "2/7": "Painting and Drawing (Traditional) and Digital Arts",
}

PERFORMING_ARTS_LABELS = {
    "Instrumental (Any instrument, including piano)": "Instrumental",
    "Vocal Soloist": "Vocal Solo",
    "Daughter Musician (Piano only) [Required Song: Now Our Work Is Over from Music Ritual]": "Daughter Musician",
    "Sign Language (Individual or Ensemble) [Required Song: Forward All Job's Daughters]": "Sign Language",
    "Theater (Monologue)": "Theater",
    "Dance (Any Style)": "Dance",
    "Vocal or Instrumental Ensemble (This includes vocal duets)": "Ensemble",
    "Ensemble sign?": "Sign Language / Ensemble",
}


def _extract_arts_and_crafts_categories(text: str) -> list[str]:
    matches = re.findall(r"Category\s*(\d+(?:/\d+)?)", str(text or ""), flags=re.IGNORECASE)
    ordered: list[str] = []
    for match in matches:
        if match not in ordered:
            ordered.append(match)
    return ordered


def _expand_arts_and_crafts_categories(categories: list[str]) -> list[str]:
    expanded: list[str] = []
    for category in categories:
        parts = [part.strip() for part in str(category).split("/") if part.strip()]
        if len(parts) > 1:
            for part in parts:
                if part not in expanded:
                    expanded.append(part)
            continue
        if category not in expanded:
            expanded.append(category)
    return expanded


def _render_kv(rows: list[tuple[str, object]]) -> str:
    table_rows = "".join(
        f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>" for label, value in rows
    )
    return f"<table class='kv'>{table_rows}</table>"


def _render_table(df: pd.DataFrame, max_rows: int = 25) -> str:
    preview = df.head(max_rows).fillna("")
    if preview.empty:
        return "<p class='empty'>No rows.</p>"
    headers = "".join(f"<th>{escape(str(column))}</th>" for column in preview.columns)
    body = []
    for _, row in preview.iterrows():
        cells = "".join(f"<td>{escape(str(value))}</td>" for value in row.tolist())
        body.append(f"<tr>{cells}</tr>")
    return f"<div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def _render_excursion_summary(excursions_df: pd.DataFrame, attendees_df: pd.DataFrame) -> str:
    if excursions_df.empty:
        return _render_kv([("None", 0)])

    interested = excursions_df.fillna("")
    interested = interested[interested["interested"] == "true"].copy()
    if interested.empty:
        return _render_kv([("None", 0)])

    attendees_by_response: dict[str, list[str]] = {}
    if not attendees_df.empty:
        working_attendees = attendees_df.fillna("")
        for response_id, rows in working_attendees.groupby("response_id", sort=False):
            attendees_by_response[str(response_id)] = [
                str(row["attendee_name"]).strip()
                for _, row in rows.iterrows()
                if str(row.get("attendee_name", "")).strip()
            ]

    body = []
    for excursion_name, rows in interested.groupby("excursion_name", sort=True):
        attendee_names: list[str] = []
        for _, row in rows.iterrows():
            attendee_names.extend(attendees_by_response.get(str(row.get("response_id", "")), []))
        tooltip = ", ".join(attendee_names) if attendee_names else "No attendee names available"
        body.append(
            "<tr>"
            f"<th><span class='hover-detail' title='{escape(tooltip)}'>{escape(str(excursion_name))}</span></th>"
            f"<td>{len(rows)}</td>"
            "</tr>"
        )
    return f"<table class='kv'>{''.join(body)}</table>"


def _preference_label(value: object) -> str:
    text = str(value or "").strip().replace("_", " ")
    return text.title() if text else ""


def _age_label(row: pd.Series) -> str:
    age = str(row.get("attendee_age_normalized", "") or "").strip()
    raw = str(row.get("attendee_age_raw", "") or "").strip()
    return age or raw


def _first_name(value: object) -> str:
    parts = [part for part in str(value or "").strip().split() if part]
    if not parts:
        return ""
    compound_second_tokens = {
        "ann",
        "anne",
        "bella",
        "beth",
        "claire",
        "ellen",
        "jean",
        "jo",
        "jane",
        "joy",
        "kay",
        "kim",
        "lee",
        "lynn",
        "mae",
        "rae",
        "rose",
    }
    if len(parts) >= 2 and parts[1].lower().strip(".") in compound_second_tokens:
        return f"{parts[0].title()} {parts[1].title()}"
    return parts[0].title()


def _render_family_cards(families_df: pd.DataFrame, attendees_df: pd.DataFrame, meals_df: pd.DataFrame) -> str:
    if families_df.empty:
        return "<p class='empty'>No family rows.</p>"

    working_families = families_df.copy().fillna("")
    working_attendees = attendees_df.copy().fillna("") if not attendees_df.empty else pd.DataFrame()
    working_meals = meals_df.copy().fillna("") if not meals_df.empty else pd.DataFrame()

    cards = []
    for _, family in working_families.sort_values("response_id").iterrows():
        response_id = str(family.get("response_id", ""))
        attendee_rows = (
            working_attendees[working_attendees["response_id"] == response_id].copy()
            if not working_attendees.empty and "response_id" in working_attendees.columns
            else pd.DataFrame()
        )
        attendee_rows = attendee_rows.sort_values(["attendee_type", "attendee_name"]) if not attendee_rows.empty else attendee_rows

        attendee_items = []
        for _, attendee in attendee_rows.iterrows():
            attendee_name = str(attendee.get("attendee_name", "")).strip()
            attendee_type = str(attendee.get("attendee_type", "")).strip()
            if not attendee_name:
                continue
            meta = []
            if attendee_type == "daughter":
                age_text = _age_label(attendee)
                if age_text:
                    meta.append(f"Age {age_text}")
            elif attendee_type == "adult":
                meta.append("Adult")
            elif attendee_type:
                meta.append(attendee_type.title())
            meta_html = f"<span class='attendee-meta'>{escape(' | '.join(meta))}</span>" if meta else ""
            type_class = f" type-{escape(attendee_type or 'unknown')}"
            attendee_items.append(
                f"<li class='attendee-pill{type_class}'><strong>{escape(attendee_name)}</strong>{meta_html}</li>"
            )

        preference_chips = []
        family_room = _preference_label(family.get("family_room_preference", ""))
        if family_room:
            preference_chips.append(f"<span class='family-chip'>Family Room: {escape(family_room)}</span>")
        separate_rooms = _preference_label(family.get("girl_adult_only_room_preference", ""))
        if separate_rooms:
            preference_chips.append(f"<span class='family-chip'>Separate Rooms: {escape(separate_rooms)}</span>")
        bed_share = _preference_label(family.get("bed_share_acknowledged", ""))
        if bed_share:
            preference_chips.append(f"<span class='family-chip'>Bed Share Ack: {escape(bed_share)}</span>")
        meal_chips = []
        if not working_meals.empty and "response_id" in working_meals.columns:
            family_meals = working_meals[working_meals["response_id"] == response_id]
            for _, meal in family_meals.iterrows():
                meal_name = str(meal.get("meal_name", "")).strip()
                attendee_name = _first_name(meal.get("attendee_name_if_known", ""))
                if not meal_name:
                    continue
                label = f"{attendee_name}: {meal_name}" if attendee_name else meal_name
                meal_chips.append(f"<span class='family-chip meal-chip'>{escape(label)}</span>")

        summary_bits = [
            f"{int(family.get('attendee_count_total', 0) or 0)} attending",
            f"{int(family.get('attendee_count_daughters', 0) or 0)} daughters",
            f"{int(family.get('attendee_count_adults', 0) or 0)} adults",
        ]
        contact_phone = str(family.get("contact_phone", "")).strip()
        emergency_name = str(family.get("emergency_contact_name", "")).strip()
        emergency_phone = str(family.get("emergency_contact_phone", "")).strip()
        allergies = str(family.get("allergies_raw", "")).strip()
        meal_section = (
            "<div class='family-meals'>"
            "<span class='family-detail-label'>Meals</span>"
            f"<div class='family-chip-row'>{''.join(meal_chips)}</div>"
            "</div>"
            if meal_chips
            else ""
        )
        attendee_list_html = "".join(attendee_items) or "<li class='empty'>No attendees parsed.</li>"

        cards.append(
            "<article class='family-card'>"
            "<div class='family-card-top'>"
            f"<h3>{escape(response_id)}</h3>"
            f"<p class='family-meta'>{escape(' • '.join(summary_bits))}</p>"
            "</div>"
            f"<ul class='attendee-list'>{attendee_list_html}</ul>"
            f"<div class='family-chip-row'>{''.join(preference_chips)}</div>"
            "<div class='family-detail-grid'>"
            f"<div><span class='family-detail-label'>Contact</span><div>{escape(contact_phone or 'Missing')}</div></div>"
            f"<div><span class='family-detail-label'>Emergency</span><div>{escape(emergency_name or 'Missing')}</div><div class='subtle'>{escape(emergency_phone)}</div></div>"
            f"<div><span class='family-detail-label'>Allergies</span><div>{escape(allergies or 'None listed')}</div></div>"
            "</div>"
            f"{meal_section}"
            "</article>"
        )

    return f"<div class='family-card-grid'>{''.join(cards)}</div>"


def _render_conflict_cards(participant_conflicts_df: pd.DataFrame) -> str:
    if participant_conflicts_df.empty:
        return "<p class='empty'>No participant conflicts flagged.</p>"

    working = participant_conflicts_df.copy().fillna("")
    cards = []
    for _, row in working.sort_values(["day_label", "time_raw", "participant_name"]).iterrows():
        participant_name = str(row.get("participant_name", "")).strip() or "Unknown participant"
        time_bits = " | ".join(
            bit
            for bit in [
                str(row.get("day_label", "")).strip(),
                str(row.get("time_raw", "")).strip(),
            ]
            if bit
        )
        competition_labels = [part.strip().replace("_", " ").title() for part in str(row.get("competition_types", "")).split("|") if part.strip()]
        conflict_pair = " vs ".join(competition_labels[:2]) if competition_labels else "Multiple entries"
        status_text = str(row.get("status", "")).strip() or "Unresolved"
        resolution_note = str(row.get("resolution_note", "")).strip()
        priority = str(row.get("priority", "")).strip()
        resolution_state = str(row.get("resolution_state", "")).strip() or "unresolved"
        escalation_logic = str(row.get("escalation_logic", "")).strip()
        cards.append(
            "<article class='conflict-card'>"
            f"<h3>{escape(participant_name)}</h3>"
            f"<p class='conflict-meta'>{escape(time_bits or 'Schedule overlap')}</p>"
            f"<p><strong>Conflict:</strong> {escape(conflict_pair)}</p>"
            f"<p><strong>Status:</strong> {escape(status_text)}</p>"
            f"<p><strong>Resolution state:</strong> {escape(resolution_state.replace('_', ' '))}</p>"
            f"{f'<p><strong>Priority:</strong> {escape(priority)}</p>' if priority else ''}"
            f"{f'<p><strong>Escalation:</strong> {escape(escalation_logic)}</p>' if escalation_logic else ''}"
            f"<p><strong>Resolution note:</strong> {escape(resolution_note)}</p>"
            "</article>"
        )

    return f"<div class='conflict-grid'>{''.join(cards)}</div>"


def _humanize_issue_type(value: object) -> str:
    text = str(value or "").strip().replace("_", " ")
    text = text.replace("cannot be aligned with attendee count", "count mismatch")
    return text.title()


def _humanize_field_name(value: object) -> str:
    text = str(value or "").strip().replace("_", " ")
    return text.title()


def _render_validation_table(flags_df: pd.DataFrame) -> str:
    if flags_df.empty:
        return "<p class='empty'>No validation issues.</p>"

    working = flags_df.copy().fillna("")
    rows = []
    for _, row in working.iterrows():
        rows.append(
            {
                "response_id": row.get("response_id", ""),
                "severity": str(row.get("severity", "")).title(),
                "issue_type": _humanize_issue_type(row.get("issue_type", "")),
                "field_name": _humanize_field_name(row.get("field_name", "")),
                "issue_detail": row.get("issue_detail", ""),
            }
        )

    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td class='mono-cell'>{escape(str(row['response_id']))}</td>"
            f"<td><span class='severity-pill'>{escape(str(row['severity']))}</span></td>"
            f"<td>{escape(str(row['issue_type']))}</td>"
            f"<td>{escape(str(row['field_name']))}</td>"
            f"<td class='detail-cell'>{escape(str(row['issue_detail']))}</td>"
            "</tr>"
        )

    return (
        "<div class='table-wrap validation-wrap'>"
        "<table class='validation-table'>"
        "<thead><tr><th>Response</th><th>Severity</th><th>Issue</th><th>Field</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody>"
        "</table>"
        "<p class='validation-note'>Warnings are preserved so you can review ambiguous or incomplete registrations without editing derived files by hand.</p>"
        "</div>"
    )


def _shorten_event_title(title: str) -> str:
    shortened = str(title)
    replacements = [
        ("Practice with the 2025-2026 Grand Bethel Officers", "Officer Practice"),
        ("Deadline for turning in Arts & Crafts Competition Items", "Arts & Crafts Turn-In Deadline"),
        ("Turn in Arts & Crafts Competition Items", "Arts & Crafts Turn-In"),
        ("Sew and Show Turn in and Judging", "Sew & Show Turn-In and Judging"),
        ("Flag Ceremony Practice (member & chaperone)", "Flag Ceremony Practice"),
        ("Pre-Opening Festivities", "Pre-Opening"),
        ("Entrance of the 2025-2026 Grand Bethel Officers", "Officer Entrance"),
        ("Escort of Honored Queens and Senior Princesses Formal", "Escort of Honored Queens"),
        ("Introduction of Miss California Job’s Daughter Contestants", "Introduce MCJD Contestants"),
        ("Drawing for Bethels eligible for 2027-2028 Grand Bethel Officer", "Eligible Bethels Drawing"),
        ("Retiring/Closing ceremonies for the 2025-2026 Grand Bethel Officers", "Retiring/Closing Ceremonies"),
        ("Announcement of 2026-2027 Grand Bethel Officers Livestream", "Officer Announcement"),
        ("2025-26 and 2026-27 Grand Bethel Officers Luncheon", "Officer Luncheon"),
        ("Arts & Crafts Competition Room open for viewing", "Arts & Crafts Viewing"),
        ("Pick up Arts & Crafts Competition items", "Arts & Crafts Pickup"),
        ("Adventure Park Private Event Casual Attire GB Session T-shirts are available for pre purchase", "Adventure Park Private Event"),
        ("(with Bethel Guardian OR member of the Executive BGC)", "With Bethel Guardian or Exec BGC"),
    ]
    for original, replacement in replacements:
        if shortened == original:
            return replacement
    return shortened


def _clean_dress_code(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""

    replacements = [
        ("Bethel Look-a-Likes! Business Casual Attire", "Business Casual"),
        ("Bethel Look-a-Likes / Business Casual", "Business Casual"),
        ("Business Attire", "Business Casual"),
        ("Casual Attire", "Casual"),
        ("Formal Attire", "Formal"),
    ]
    for original, replacement in replacements:
        if text == original:
            return replacement

    text = text.replace("[GB Session T-shirts are available for pre purchase]", "")
    text = text.replace("GB Session T-shirts are available for pre purchase", "")
    text = " ".join(text.split())
    text = text.replace("Attire", "").replace("  ", " ").strip(" -")
    if "business casual" in text.lower():
        return "Business Casual"
    if text.lower() == "business":
        return "Business Casual"
    return text


def _dress_code_display(value: object) -> str:
    cleaned = _clean_dress_code(value)
    if cleaned:
        return f"<span class='dress-pill'>{escape(str(cleaned))}</span>"
    return "<span class='dress-pill dress-pill-muted'>Unspecified</span>"


def _program_audience_tag(row: dict[str, object]) -> str:
    title = str(row.get("event_title", "") or "").strip().lower()
    event_type = str(row.get("event_type", "") or "").strip().lower()
    if not title and not event_type:
        return ""
    if "registration" in title or "luncheon" in title or "banquet" in title or "excursion" in title:
        return "Families"
    if "guardian" in title or "chaperone" in title or "adult" in title:
        return "Adults"
    if event_type == "competition_related" or "competition" in title or "awards" in title or "variety show" in title:
        return "Competitors"
    if event_type == "bethel_local":
        return "Staff"
    if "formal opening" in title or "installation" in title or "officer" in title:
        return "All Daughters"
    return ""


def _program_audience_class(label: str) -> str:
    normalized = str(label or "").strip().lower().replace(" ", "-")
    if normalized in {"all-daughters", "competitors", "families"}:
        return f" audience-tag--{normalized}"
    return ""


def _render_program_table(program_blocks_df: pd.DataFrame) -> str:
    if program_blocks_df.empty:
        return "<p class='empty'>No program rows.</p>"

    columns = [
        "day_label",
        "display_time_raw",
        "time_raw",
        "event_title",
        "dress_code",
        "schedule_source",
        "event_type",
        "override_assignment",
        "assigned_people",
        "replaced_event_titles",
        "attendance_note",
    ]
    working = program_blocks_df.copy()
    for column in columns:
        if column not in working.columns:
            working[column] = ""
    working = working[columns].fillna("")

    sections = []
    for day_label, day_rows in working.groupby("day_label", sort=False):
        rows = day_rows.to_dict(orient="records")
        effective_dress_codes = []
        current_dress_code = ""
        for row in rows:
            if row["dress_code"]:
                current_dress_code = _clean_dress_code(row["dress_code"])
                effective_dress_codes.append(current_dress_code)
            else:
                effective_dress_codes.append(current_dress_code if row["time_raw"] else "")
        for row, effective_dress_code in zip(rows, effective_dress_codes):
            row["effective_dress_code"] = effective_dress_code

        group_rows = []
        index = 0
        while index < len(rows):
            current = rows[index]
            group = [current]
            next_index = index + 1
            while next_index < len(rows):
                candidate = rows[next_index]
                if candidate["display_time_raw"]:
                    break
                if candidate["time_raw"] != current["time_raw"]:
                    break
                group.append(candidate)
                next_index += 1

            event_entries = []
            for row in group:
                source = row["schedule_source"]
                source_tag = ""
                if source and source not in {"state_program", "program_patch"}:
                    source_tag = f" <span class='source-tag'>{escape(str(source).replace('_', ' '))}</span>"
                audience = _program_audience_tag(row)
                audience_tag = (
                    f" <span class='audience-tag{_program_audience_class(audience)}'>{escape(audience)}</span>"
                    if audience
                    else ""
                )
                risk_level = str(row.get("risk_level", "")).strip().lower()
                risk_tag = ""
                if risk_level in {"high", "medium"}:
                    label = "High Density" if risk_level == "high" else "Watch"
                    risk_tag = f" <span class='source-tag'>{escape(label)}</span>"
                event_entries.append(
                    {
                        "title": _shorten_event_title(str(row["event_title"])),
                        "meta_html": f"{audience_tag}{risk_tag}{source_tag}",
                        "override_assignment": str(row.get("override_assignment", "")).strip(),
                        "assigned_people": str(row.get("assigned_people", "")).strip(),
                        "replaced_event_titles": str(row.get("replaced_event_titles", "")).strip(),
                        "attendance_note": str(row.get("attendance_note", "")).strip(),
                    }
                )

            group_rows.append(
                {
                    "time_text": current["display_time_raw"] or current["time_raw"],
                    "event_entries": event_entries,
                    "effective_dress_code": current["effective_dress_code"],
                }
            )

            index = next_index

        body_rows = []
        for row in group_rows:
            event_entries = row["event_entries"]
            override_assignment = str(event_entries[0].get("override_assignment", "")).strip().lower() if event_entries else ""
            if override_assignment == "guard_duty":
                assigned_people = str(event_entries[0].get("assigned_people", "")).strip()
                attendance_note = str(event_entries[0].get("attendance_note", "")).strip() or "Assigned to Guard Duty — session attendance not expected"
                replaced_titles = [part.strip() for part in str(event_entries[0].get("replaced_event_titles", "")).split("|") if part.strip()]
                people_html = f"<p class='subtle'><strong>People:</strong> {escape(assigned_people)}</p>" if assigned_people else ""
                replaces_html = (
                    "<details class='later-block'><summary>Replaces</summary>"
                    f"<ul class='action-list'>{''.join(f'<li>{escape(title)}</li>' for title in replaced_titles)}</ul>"
                    "</details>"
                    if replaced_titles
                    else ""
                )
                # Guard duty is a personal-view override: the ground-truth program remains
                # intact elsewhere, but the personal view swaps the whole session block.
                event_html = (
                    "<div class='program-event-single'>"
                    "<span class='program-event-title'>GUARD DUTY — Assigned</span>"
                    " <span class='source-tag'>assigned</span>"
                    f"<p class='subtle'>{escape(attendance_note)}</p>"
                    f"{people_html}"
                    f"{replaces_html}"
                    "</div>"
                )
            elif len(event_entries) == 1:
                only_entry = event_entries[0]
                event_html = f"<div class='program-event-single'>{escape(str(only_entry['title']))}{only_entry['meta_html']}</div>"
            else:
                items = "".join(
                    f"<li class='program-event-item'><span class='program-event-title'>{escape(str(entry['title']))}</span>{entry['meta_html']}</li>"
                    for entry in event_entries
                )
                event_html = f"<ul class='program-event-group'>{items}</ul>"

            cells = []
            cells.append(f"<td class='time-cell'>{escape(str(row['time_text']))}</td>")
            cells.append(f"<td>{event_html}</td>")
            cells.append(f"<td class='dress-cell'>{_dress_code_display(row['effective_dress_code'])}</td>")

            body_rows.append(f"<tr>{''.join(cells)}</tr>")

        sections.append(
            "<section class='program-day'>"
            f"<h3>{escape(str(day_label))}</h3>"
            "<div class='table-wrap'>"
            "<table class='program-table'>"
            "<thead><tr><th>Time</th><th>Event</th><th>Dress Code</th></tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
            "</table>"
            "</div>"
            "</section>"
        )
    return "".join(sections)


def _format_competition_label(value: str) -> str:
    return COMPETITION_LABELS.get(str(value), str(value).replace("_", " ").title())


def _render_category_badge(value: object, competition_type: str) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    if competition_type == "arts_and_crafts":
        categories = _expand_arts_and_crafts_categories(_extract_arts_and_crafts_categories(text) or [text])
        if categories:
            badges = []
            for category in categories:
                label = ARTS_AND_CRAFTS_CATEGORY_LABELS.get(category, f"Cat. {category}")
                tooltip = ARTS_AND_CRAFTS_CATEGORY_TOOLTIPS.get(category, f"Category {category}")
                badges.append(f"<span class='category-badge' title='{escape(tooltip)}'>{escape(label)}</span>")
            return "".join(badges)
    if competition_type in {"performing_arts", "choir"}:
        shorthand = PERFORMING_ARTS_LABELS.get(text, text)
        return f"<span class='category-badge' title='{escape(text)}'>{escape(shorthand)}</span>"
    if len(text) > 50:
        short = text[:47].rstrip() + "..."
        return f"<span class='category-badge' title='{escape(text)}'>{escape(short)}</span>"
    return f"<span class='category-badge' title='{escape(text)}'>{escape(text)}</span>"


def _performing_arts_bucket(row: pd.Series) -> str:
    competition_type = str(row.get("competition_type", ""))
    category = str(row.get("category_raw", "") or "")
    if competition_type == "choir":
        return "Choir"
    if "ensemble" in category.lower() or "sign language" in category.lower():
        return "Ensemble"
    return "Individual"


def _render_competition_dashboard(
    competition_event_rosters_df: pd.DataFrame,
    competitions_df: pd.DataFrame,
) -> str:
    if competition_event_rosters_df.empty and competitions_df.empty:
        return "<p class='empty'>No competition entries.</p>"

    sections = []

    if not competition_event_rosters_df.empty:
        scheduled = competition_event_rosters_df.fillna("")
        scheduled = scheduled[scheduled["schedule_status"] == "scheduled"].copy()
        if not scheduled.empty:
            scheduled_sections = []
            grouped = scheduled.copy()
            grouped = grouped.assign(
                dashboard_competition_type=grouped["competition_type"].replace({"choir": "performing_arts"})
            )

            for competition_type, rows in grouped.groupby("dashboard_competition_type", sort=True):
                if competition_type == "performing_arts":
                    bucket_sections = []
                    rows = rows.copy()
                    rows["performing_arts_bucket"] = rows.apply(_performing_arts_bucket, axis=1)
                    for bucket in ["Choir", "Individual", "Ensemble"]:
                        bucket_rows = rows[rows["performing_arts_bucket"] == bucket].sort_values(
                            ["day_label", "time_raw", "participant_name"]
                        )
                        if bucket_rows.empty:
                            continue
                        items = []
                        for _, row in bucket_rows.iterrows():
                            category_html = _render_category_badge(row.get("category_raw", ""), str(row["competition_type"]))
                            group_badge = " <span class='source-tag'>group</span>" if str(row.get("is_group_competition", "")).strip().lower() == "true" else ""
                            items.append(
                                "<li>"
                                f"<strong>{escape(str(row['participant_name']))}</strong>"
                                f"{group_badge}"
                                f"{' ' + category_html if category_html and bucket != 'Choir' else ''}"
                                "</li>"
                            )
                        bucket_sections.append(
                            f"<h4 class='bucket-title'>{escape(bucket)}:</h4>"
                            f"<ul class='roster-list compact'>{''.join(items)}</ul>"
                        )
                    scheduled_sections.append(
                        "<article class='roster-card'>"
                        "<h3>Performing Arts</h3>"
                        f"<p class='roster-meta'>{len(rows)} scheduled entries</p>"
                        f"{''.join(bucket_sections)}"
                        "</article>"
                    )
                    continue

                items = []
                for _, row in rows.sort_values(["day_label", "time_raw", "participant_name"]).iterrows():
                    category_html = _render_category_badge(row.get("category_raw", ""), str(row["competition_type"]))
                    group_badge = " <span class='source-tag'>group</span>" if str(row.get("is_group_competition", "")).strip().lower() == "true" else ""
                    items.append(
                        "<li>"
                        f"<strong>{escape(str(row['participant_name']))}</strong>"
                        f"{group_badge}"
                        f"{' ' + category_html if category_html else ''}"
                        "</li>"
                    )
                scheduled_sections.append(
                    "<article class='roster-card'>"
                    f"<h3>{escape(_format_competition_label(competition_type))}</h3>"
                    f"<p class='roster-meta'>{len(rows)} scheduled entries</p>"
                    f"<ul class='roster-list compact'>{''.join(items)}</ul>"
                    "</article>"
                )
            sections.append(
                "<section class='competition-group'>"
                f"<div class='roster-grid'>{''.join(scheduled_sections)}</div>"
                "</section>"
            )

        advance_submissions = competition_event_rosters_df.fillna("")
        advance_submissions = advance_submissions[advance_submissions["schedule_status"] == "submitted_in_advance"].copy()
        if not advance_submissions.empty:
            sections.append(
                "<section class='competition-group'>"
                "<h3>Submitted In Advance</h3>"
                f"{_render_table(advance_submissions[['response_id', 'participant_name', 'competition_type', 'is_group_competition', 'category_raw', 'schedule_status', 'notes']])}"
                "</section>"
            )

        unscheduled = competition_event_rosters_df.fillna("")
        unscheduled = unscheduled[unscheduled["schedule_status"] == "unscheduled_in_program"].copy()
        if not unscheduled.empty:
            sections.append(
                "<section class='competition-group'>"
                "<h3>Unscheduled or Needs Mapping</h3>"
                f"{_render_table(unscheduled[['response_id', 'participant_name', 'competition_type', 'is_group_competition', 'category_raw', 'schedule_status', 'notes']])}"
                "</section>"
            )

    elif not competitions_df.empty:
        sections.append(_render_table(competitions_df))

    return "".join(sections)


def _render_section(section_id: str, title: str, content: str, *, collapsible: bool = False, open_by_default: bool = True) -> str:
    if not collapsible:
        return f"<section id='{escape(section_id)}' class='panel'><h2>{escape(title)}</h2>{content}</section>"
    open_attr = " open" if open_by_default else ""
    return (
        f"<section id='{escape(section_id)}' class='panel collapse-panel'>"
        f"<details{open_attr}><summary>{escape(title)}</summary>{content}</details>"
        "</section>"
    )


def _render_nav(items: list[tuple[str, str]]) -> str:
    links = "".join(
        f"<a class='nav-chip' href='#{escape(section_id)}'>{escape(label)}</a>" for section_id, label in items
    )
    return f"<nav class='jump-nav'>{links}</nav>"


def build_dashboard(
    output_path: Path,
    summary: dict,
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
    overview = [
        ("Total families", summary["total_responses"]),
        ("Attending families", summary["yes_attending_count"]),
        ("Total attendees", summary["total_attendees"]),
        ("Daughters", summary["daughters_count"]),
        ("Adults", summary["adults_count"]),
        ("Flagged records", summary["flagged_record_counts"]),
        ("Program blocks", summary.get("program_block_count", 0)),
        ("Scheduled competition roster rows", summary.get("scheduled_competition_roster_count", 0)),
        ("Possible participant conflicts", summary.get("participant_conflict_count", 0)),
    ]
    meal_summary_rows = [
        (f"{code} - {MEAL_LABELS.get(code, code)}", count)
        for code, count in sorted(summary["meal_counts_by_code"].items())
    ] or [("None", 0)]
    validation_count = int(summary.get("flagged_record_counts", 0))
    nav_items = [
        ("overview", "Overview"),
        ("session-program", "Session Program"),
        ("competition-rosters", "Competition Rosters"),
        ("conflicts", "Conflicts"),
        ("families", "Families"),
    ]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Grand Bethel Registration Dashboard</title>
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
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
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
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, var(--bg-accent), transparent 34%),
        linear-gradient(180deg, var(--bg-accent) 0%, var(--bg) 36%, var(--bg) 100%);
    }}
    a {{ color: inherit; }}
    .page-shell {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 24px 18px 56px;
    }}
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
    .masthead-row {{
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
    }}
    .title-wrap h1 {{
      margin: 0;
      font-size: clamp(1.8rem, 3vw, 2.5rem);
    }}
    .title-wrap p {{
      margin: 6px 0 0;
      color: var(--muted);
      max-width: 72ch;
    }}
    .theme-toggle {{
      border: 1px solid var(--line-strong);
      background: var(--panel-strong);
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
    }}
    .jump-nav {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .nav-chip {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--chip);
      color: var(--chip-text);
      text-decoration: none;
      border: 1px solid var(--line);
      font-size: 14px;
    }}
    .warning-banner {{
      margin-top: 14px;
      padding: 12px 14px;
      border: 1px solid #8c69c7;
      border-radius: 14px;
      background: color-mix(in srgb, #b492ef 28%, var(--panel-strong));
      color: var(--ink);
    }}
    .warning-banner-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .warning-banner-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .warning-banner button {{
      margin-top: 10px;
      border: 1px solid var(--line-strong);
      background: var(--panel-strong);
      color: var(--ink);
      border-radius: 999px;
      padding: 7px 11px;
      font: inherit;
      cursor: pointer;
    }}
    .warning-banner-top button {{
      margin-top: 0;
    }}
    .warning-banner[hidden], .warning-modal[hidden] {{
      display: none;
    }}
    .warning-modal {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.45);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 50;
    }}
    .warning-dialog {{
      width: min(1080px, 100%);
      max-height: 80vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--panel-strong);
      padding: 18px;
      box-shadow: 0 20px 40px var(--shadow);
    }}
    .warning-dialog-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .warning-close {{
      border: 1px solid var(--line);
      background: transparent;
      color: var(--ink);
      border-radius: 999px;
      padding: 6px 10px;
      font: inherit;
      cursor: pointer;
    }}
    .validation-wrap {{
      margin-top: 10px;
      border-radius: 16px;
    }}
    .validation-table {{
      table-layout: fixed;
    }}
    .validation-table th:nth-child(1),
    .validation-table td:nth-child(1) {{
      width: 13%;
    }}
    .validation-table th:nth-child(2),
    .validation-table td:nth-child(2) {{
      width: 12%;
    }}
    .validation-table th:nth-child(3),
    .validation-table td:nth-child(3) {{
      width: 26%;
    }}
    .validation-table th:nth-child(4),
    .validation-table td:nth-child(4) {{
      width: 12%;
    }}
    .mono-cell {{
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }}
    .detail-cell {{
      line-height: 1.4;
      overflow-wrap: anywhere;
    }}
    .severity-pill {{
      display: inline-block;
      padding: 2px 9px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--tag-bg) 78%, var(--panel-strong));
      color: var(--tag-text);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .validation-note {{
      margin: 10px 2px 2px;
      color: var(--muted);
      font-size: 13px;
    }}
    .overview-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .content-grid {{
      display: grid;
      gap: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 10px 26px var(--shadow);
      overflow: hidden;
    }}
    .panel h2, .panel h3 {{
      margin-top: 0;
    }}
    .panel h2 {{
      margin-bottom: 12px;
      font-size: 1.15rem;
    }}
    .table-wrap {{
      overflow: auto;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 14px;
      background: transparent;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: color-mix(in srgb, var(--bg-accent) 58%, var(--panel-strong));
    }}
    .kv th {{
      width: 60%;
      background: transparent;
    }}
    .program-day + .program-day {{
      margin-top: 22px;
    }}
    .program-day h3 {{
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--line);
    }}
    .program-event-single {{
      display: block;
      line-height: 1.45;
    }}
    .program-event-group {{
      margin: 0;
      padding-left: 18px;
    }}
    .program-event-item + .program-event-item {{
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid color-mix(in srgb, var(--line) 65%, transparent);
    }}
    .program-event-title {{
      font-weight: 600;
    }}
    .program-table th {{
      background: color-mix(in srgb, var(--bg-accent) 72%, var(--panel-strong));
    }}
    .program-table .time-cell {{
      width: 17%;
      min-width: 92px;
      white-space: nowrap;
      font-weight: 700;
      background: var(--time-bg);
    }}
    .program-table .dress-cell {{
      width: 22%;
      min-width: 120px;
      background: var(--dress-bg);
    }}
    .dress-pill {{
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--dress-bg) 88%, transparent);
      font-size: 12px;
      white-space: nowrap;
    }}
    .dress-pill-muted {{
      color: var(--muted);
      background: color-mix(in srgb, var(--dress-bg) 72%, transparent);
    }}
    .source-tag {{
      display: inline-block;
      margin-left: 8px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 12px;
      color: var(--tag-text);
      background: var(--tag-bg);
      vertical-align: middle;
    }}
    .audience-tag {{
      display: inline-block;
      margin-left: 8px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 12px;
      color: var(--tag-text);
      background: color-mix(in srgb, var(--tag-bg) 62%, var(--panel-strong));
      vertical-align: middle;
      font-weight: 700;
    }}
    .audience-tag--all-daughters {{
      border-color: var(--line-strong);
      background: color-mix(in srgb, var(--tag-bg) 82%, var(--panel-strong));
    }}
    .audience-tag--competitors {{
      background: color-mix(in srgb, var(--tag-bg) 72%, var(--panel-strong));
    }}
    .audience-tag--families {{
      background: color-mix(in srgb, var(--tag-bg) 54%, var(--panel-strong));
    }}
    .competition-group + .competition-group {{
      margin-top: 20px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }}
    .roster-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 14px;
    }}
    .roster-card {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: color-mix(in srgb, var(--panel-strong) 90%, transparent);
    }}
    .roster-card h3 {{
      margin-bottom: 6px;
      font-size: 1rem;
    }}
    .bucket-title {{
      margin: 12px 0 6px;
      font-size: 0.95rem;
    }}
    .roster-meta, .subtle {{
      color: var(--muted);
      font-size: 13px;
    }}
    .roster-list {{
      margin: 10px 0 0;
      padding-left: 18px;
    }}
    .roster-list.compact li + li {{
      margin-top: 4px;
    }}
    .category-badge {{
      display: inline-block;
      margin-left: 6px;
      padding: 1px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--tag-bg);
      color: var(--tag-text);
      font-size: 12px;
      cursor: help;
      vertical-align: middle;
    }}
    .hover-detail {{
      cursor: help;
      text-decoration: underline dotted;
      text-underline-offset: 0.16em;
    }}
    .family-card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }}
    .family-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 15px;
      background: color-mix(in srgb, var(--panel-strong) 92%, transparent);
    }}
    .family-card-top {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .family-card-top h3 {{
      margin: 0;
      font-size: 1rem;
    }}
    .family-meta {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .attendee-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .attendee-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      font-size: 14px;
    }}
    .attendee-pill.type-daughter {{
      background: color-mix(in srgb, var(--tag-bg) 45%, var(--panel-strong));
    }}
    .attendee-pill.type-adult {{
      background: color-mix(in srgb, var(--bg-accent) 35%, var(--panel-strong));
    }}
    .attendee-meta {{
      color: var(--muted);
      font-size: 12px;
    }}
    .family-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .family-chip {{
      display: inline-block;
      padding: 4px 9px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--chip);
      color: var(--chip-text);
      font-size: 12px;
    }}
    .family-detail-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      font-size: 14px;
    }}
    .family-detail-label {{
      display: block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .family-meals {{
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .meal-chip {{
      background: color-mix(in srgb, var(--tag-bg) 38%, var(--panel-strong));
    }}
    .conflict-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .conflict-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: color-mix(in srgb, var(--panel-strong) 92%, transparent);
    }}
    .conflict-card h3 {{
      margin: 0 0 6px;
      font-size: 1rem;
    }}
    .conflict-card p {{
      margin: 6px 0 0;
    }}
    .conflict-meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .collapse-panel details {{
      display: block;
    }}
    .collapse-panel summary {{
      list-style: none;
      cursor: pointer;
      font-weight: 600;
      margin: -18px -18px 14px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel-strong) 80%, transparent);
    }}
    .collapse-panel summary::-webkit-details-marker {{
      display: none;
    }}
    .collapse-panel summary::after {{
      content: "Open";
      float: right;
      color: var(--muted);
      font-weight: 400;
    }}
    .collapse-panel details[open] summary::after {{
      content: "Close";
    }}
    .empty {{
      color: var(--muted);
      margin: 0;
    }}
  </style>
</head>
<body>
  <div class="page-shell">
    <header class="masthead" id="top">
      <div class="masthead-row">
        <div class="title-wrap">
          <h1>2026 Grand Bethel Registration Dashboard</h1>
          <p>Operational view of registration, schedule, competitions, excursions, and planning data.</p>
        </div>
        <button class="theme-toggle" id="theme-toggle" type="button" aria-label="Toggle light or dark theme">Toggle theme</button>
      </div>
      {_render_nav(nav_items)}
      <div class="warning-banner" id="validation-banner" data-validation-count="{validation_count}" {'hidden' if validation_count == 0 else ''}>
        <div class="warning-banner-top">
          <div><strong>Warning:</strong> {validation_count} record(s) have validation issues.</div>
          <div class="warning-banner-actions">
            <button type="button" id="open-validation-modal">View issues</button>
            <button type="button" id="dismiss-validation-banner">Dismiss</button>
          </div>
        </div>
      </div>
    </header>

    <section id="overview" class="overview-grid">
      <section class="panel">
        <h2>Overview</h2>
        {_render_kv(overview)}
      </section>
      <section class="panel">
        <h2>Meals</h2>
        {_render_kv(meal_summary_rows)}
      </section>
      <section class="panel">
        <h2>Competitions</h2>
        {_render_kv(sorted(summary["competition_counts_by_type"].items()) or [("None", 0)])}
      </section>
      <section class="panel">
        <h2>Excursions</h2>
        {_render_excursion_summary(excursions_df, attendees_df)}
      </section>
    </section>

    <div class="content-grid">
      {_render_section("session-program", "Session Program", _render_program_table(program_blocks_df))}
      {_render_section("competition-rosters", "Competition Planning", _render_competition_dashboard(competition_event_rosters_df, competitions_df))}
      {_render_section("conflicts", "Participant Conflicts", _render_conflict_cards(participant_conflicts_df))}
      {_render_section("families", "Families", _render_family_cards(families_df, attendees_df, meals_df))}
    </div>
  </div>
  <div class="warning-modal" id="validation-modal" hidden>
    <div class="warning-dialog">
      <div class="warning-dialog-top">
        <h2>Validation Issues</h2>
        <button type="button" class="warning-close" id="close-validation-modal">Close</button>
      </div>
      {_render_validation_table(flags_df)}
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
      button.addEventListener("click", function () {{
        const current = root.dataset.theme === "dark" ? "dark" : root.dataset.theme === "light" ? "light" : "";
        const next = current === "dark" ? "light" : "dark";
        root.dataset.theme = next;
        window.localStorage.setItem(storageKey, next);
      }});

      const openValidation = document.getElementById("open-validation-modal");
      const closeValidation = document.getElementById("close-validation-modal");
      const modal = document.getElementById("validation-modal");
      const warningBanner = document.getElementById("validation-banner");
      const dismissValidationBanner = document.getElementById("dismiss-validation-banner");
      const validationStorageKey = "grand-bethel-dashboard-validation-banner";
      if (warningBanner && !warningBanner.hidden) {{
        const currentValidationCount = warningBanner.dataset.validationCount || "0";
        const dismissedForCount = window.localStorage.getItem(validationStorageKey);
        if (dismissedForCount === currentValidationCount) {{
          warningBanner.hidden = true;
        }}
        if (dismissValidationBanner) {{
          dismissValidationBanner.addEventListener("click", function () {{
            warningBanner.hidden = true;
            window.localStorage.setItem(validationStorageKey, currentValidationCount);
          }});
        }}
      }}
      if (openValidation && closeValidation && modal) {{
        openValidation.addEventListener("click", function () {{
          modal.hidden = false;
        }});
        closeValidation.addEventListener("click", function () {{
          modal.hidden = true;
        }});
        modal.addEventListener("click", function (event) {{
          if (event.target === modal) {{
            modal.hidden = true;
          }}
        }});
      }}
    }})();
  </script>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
