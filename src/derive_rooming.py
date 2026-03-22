from __future__ import annotations

from typing import List


def build_rooming_rows(response_row: dict, attendees: List[dict]) -> List[dict]:
    rooming_rows = []
    for attendee in attendees:
        notes = []
        if response_row.get("family_room_preference") == "yes":
            notes.append("Family room requested.")
        if response_row.get("girl_adult_only_room_preference") == "yes":
            notes.append("Girl-only/adult-only room requested.")
        if attendee.get("attendee_type") == "unknown":
            notes.append("Attendee type unknown.")
        rooming_rows.append(
            {
                "response_id": response_row["response_id"],
                "attendee_name": attendee["attendee_name"],
                "attendee_type": attendee["attendee_type"],
                "family_room_preference": response_row.get("family_room_preference", ""),
                "girl_adult_only_room_preference": response_row.get("girl_adult_only_room_preference", ""),
                "bed_share_acknowledged": response_row.get("bed_share_acknowledged", ""),
                "allergies_raw": response_row.get("allergies_raw", ""),
                "rooming_notes": " ".join(notes),
            }
        )
    return rooming_rows
