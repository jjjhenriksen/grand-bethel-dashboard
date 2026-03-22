from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Tuple


@dataclass
class ParsedAttendee:
    attendee_name: str
    attendee_age_raw: str
    attendee_age_normalized: str
    attendee_type: str
    parse_note: str = ""


PAIR_PATTERN = re.compile(
    r"""
    (?P<name>[A-Za-z][A-Za-z' -]*?[A-Za-z])
    \s*(?:-|:|\.|\s)\s*
    (?P<age>adult|\d{1,2}(?:\s*\([^)]*\))?)
    (?=\s*(?:,|;|\n|$|[A-Za-z][A-Za-z' -]*?(?:-|:|\.|\s)(?:adult\b|\d{1,2}\b)))
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _clean_name(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip(" .,-\t"))
    return cleaned.title()


def _first_name(text: str) -> str:
    parts = [part for part in str(text or "").strip().split() if part]
    return parts[0].title() if parts else ""


def _normalize_age(age_raw: str) -> tuple[str, str]:
    lowered = str(age_raw or "").strip().lower()
    digits = re.findall(r"\d{1,2}", lowered)
    if "adult" in lowered:
        if digits and int(digits[0]) < 18:
            return digits[0], "daughter"
        return "adult", "adult"
    if digits:
        age_value = int(digits[0])
        return str(age_value), "adult" if age_value >= 18 else "daughter"
    return "", "unknown"


def _parse_name_only_attendees(raw: str) -> tuple[list[ParsedAttendee], list[Dict[str, str]]]:
    parts = re.split(r"[\n,;&]+", str(raw or ""))
    names = [_clean_name(part) for part in parts if _clean_name(part)]
    if not names:
        return [], []
    attendees = [
        ParsedAttendee(
            attendee_name=name,
            attendee_age_raw="",
            attendee_age_normalized="",
            attendee_type="adult",
            parse_note="name_only_assumed_adult",
        )
        for name in names
    ]
    if len(attendees) == 1:
        return attendees, []
    flags = [
        {
            "severity": "warning",
            "issue_type": "attendee_parsing_ambiguity",
            "field_name": "family_attendance",
            "issue_detail": "Family attendance listed name(s) without ages. Defaulted to adult attendee(s).",
        }
    ]
    return attendees, flags


def parse_family_attendance(text: str) -> Tuple[List[ParsedAttendee], List[Dict[str, str]]]:
    attendees: List[ParsedAttendee] = []
    flags: List[Dict[str, str]] = []
    raw = str(text or "").strip()
    if not raw:
        return attendees, [
            {
                "severity": "error",
                "issue_type": "blank_family_attendance_field",
                "field_name": "family_attendance",
                "issue_detail": "Family attendance text is blank.",
            }
        ]

    normalized = raw.replace("\r", "\n")
    normalized = re.sub(r"\s+", " ", normalized.replace("\n", ", "))
    normalized = re.sub(
        r"(adult|\d{1,2}(?:\s*\([^)]*\))?)\s+(?=[A-Za-z][A-Za-z' -]*?(?:-|:|\.|\s)(?:adult\b|\d{1,2}\b))",
        r"\1, ",
        normalized,
        flags=re.IGNORECASE,
    )
    matches = list(PAIR_PATTERN.finditer(normalized))
    if not matches:
        fallback_attendees, fallback_flags = _parse_name_only_attendees(raw)
        if fallback_attendees:
            return fallback_attendees, fallback_flags
        return attendees, [
            {
                "severity": "error",
                "issue_type": "attendee_parsing_failed",
                "field_name": "family_attendance",
                "issue_detail": f"Unable to parse attendees from: {raw}",
            }
        ]

    for match in matches:
        name = _clean_name(match.group("name"))
        age_raw = match.group("age").strip(" ,.;")
        age_normalized, attendee_type = _normalize_age(age_raw)
        if attendee_type == "daughter":
            name = _first_name(name)
        parse_note = "adult_age_conflict" if "adult" in age_raw.lower() and age_normalized.isdigit() else ""
        attendees.append(
            ParsedAttendee(
                attendee_name=name,
                attendee_age_raw=age_raw,
                attendee_age_normalized=age_normalized,
                attendee_type=attendee_type,
                parse_note=parse_note,
            )
        )
        if parse_note:
            flags.append(
                {
                    "severity": "warning",
                    "issue_type": "attendee_parsing_ambiguity",
                    "field_name": "family_attendance",
                    "issue_detail": f"Attendee `{name}` included both age and adult marker: `{age_raw}`.",
                }
            )

    residual = re.sub(r"\s+", " ", PAIR_PATTERN.sub("", normalized)).strip(" ,;")
    if residual:
        flags.append(
            {
                "severity": "warning",
                "issue_type": "attendee_parsing_ambiguity",
                "field_name": "family_attendance",
                "issue_detail": f"Unparsed family attendance text remains: {residual}",
            }
        )

    return attendees, flags
