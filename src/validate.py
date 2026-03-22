from __future__ import annotations

from collections import defaultdict
from typing import Dict, List


def add_flag(flags: List[dict], response_id: str, severity: str, issue_type: str, field_name: str, issue_detail: str) -> None:
    flags.append(
        {
            "response_id": response_id,
            "severity": severity,
            "issue_type": issue_type,
            "field_name": field_name,
            "issue_detail": issue_detail,
        }
    )


def validate_response(
    row: Dict[str, str],
    attendees: List[dict],
    attendee_flags: List[dict],
    competition_flags: List[dict],
    meal_flags: List[dict],
) -> List[dict]:
    flags: List[dict] = []
    response_id = row["response_id"]

    for source_flags in [attendee_flags, competition_flags, meal_flags]:
        for source_flag in source_flags:
            add_flag(
                flags,
                response_id,
                source_flag["severity"],
                source_flag["issue_type"],
                source_flag["field_name"],
                source_flag["issue_detail"],
            )

    if row.get("attending_grand_bethel") == "no" and attendees:
        add_flag(
            flags,
            response_id,
            "warning",
            "attendance_says_no_but_family_members_listed",
            "attending_grand_bethel",
            "Attendance is marked no, but family members were listed.",
        )

    if row.get("attending_grand_bethel") == "yes" and not attendees:
        add_flag(
            flags,
            response_id,
            "error",
            "blank_family_attendance_field",
            "family_attendance",
            "Attendance marked yes but no attendees were parsed.",
        )

    if not row.get("emergency_contact_name"):
        add_flag(
            flags,
            response_id,
            "warning",
            "emergency_contact_missing",
            "emergency_contact_name",
            "Emergency contact name is missing.",
        )

    if not row.get("emergency_contact_phone"):
        add_flag(
            flags,
            response_id,
            "warning",
            "emergency_contact_missing",
            "emergency_contact_phone",
            "Emergency contact phone is missing.",
        )

    if not row.get("contact_phone"):
        add_flag(
            flags,
            response_id,
            "warning",
            "contact_phone_missing",
            "contact_phone",
            "Contact phone is missing.",
        )

    if row.get("family_room_preference") == "yes" and row.get("girl_adult_only_room_preference") == "yes":
        add_flag(
            flags,
            response_id,
            "warning",
            "contradictory_rooming_preferences",
            "rooming_preferences",
            "Family room preference conflicts with girl-only/adult-only room preference.",
        )

    return flags


def flag_duplicate_attendee_names(attendee_rows: List[dict]) -> List[dict]:
    flags: List[dict] = []
    names_to_responses: Dict[str, set[str]] = defaultdict(set)
    for attendee in attendee_rows:
        normalized_name = attendee.get("attendee_name", "").strip().lower()
        if normalized_name:
            names_to_responses[normalized_name].add(attendee["response_id"])

    for normalized_name, response_ids in names_to_responses.items():
        if len(response_ids) > 1:
            pretty_name = next(
                attendee["attendee_name"]
                for attendee in attendee_rows
                if attendee.get("attendee_name", "").strip().lower() == normalized_name
            )
            for response_id in sorted(response_ids):
                add_flag(
                    flags,
                    response_id,
                    "warning",
                    "duplicate_attendee_name_across_rows",
                    "attendee_name",
                    f"Attendee name appears in multiple responses: {pretty_name}",
                )
    return flags
