from __future__ import annotations

import re
from typing import Dict, List

from parse_program import canonical_day_label
from parse_program import build_override_block


DAY_TO_DATE = {
    "Wednesday": "2026-06-17",
    "Thursday": "2026-06-18",
    "Friday": "2026-06-19",
    "Saturday": "2026-06-20",
    "Sunday": "2026-06-21",
}

NON_OPERATIONAL_KEYWORDS = [
    "volleyball",
    "grand bethel officers",
    "jurisdiction representative",
    "roll call of bethels",
    "escort of honored queens",
    "project presentation",
    "introduction of jds to bee",
    "introduction of miss california job",
    "drawing of 2026-2027 jurisdiction representatives",
    "drawing for bethels eligible",
    "announcement of 2026-2027 grand bethel officers",
    "formal opening",
    "formal installation",
]


def is_operational_highlight(block: dict) -> bool:
    title = block.get("event_title", "").lower()
    if any(keyword in title for keyword in NON_OPERATIONAL_KEYWORDS):
        return False
    return block.get("event_type") in {"competition_related", "logistics", "meal_or_social", "bethel_local"}


def merge_program_with_overrides(program_blocks: List[dict], overrides: dict) -> List[dict]:
    merged = list(program_blocks)
    next_index = len(merged) + 1
    for block in overrides.get("extra_blocks", []):
        merged.append(build_override_block(f"L{next_index:03d}", block))
        next_index += 1
    return merged


def map_competitions_to_blocks(
    competition_rows: List[dict],
    program_blocks: List[dict],
    schedule_map: dict,
) -> List[dict]:
    rosters: List[dict] = []
    keyword_map = schedule_map.get("competition_event_keywords", {})
    advance_submission_competitions = {
        str(value).strip()
        for value in schedule_map.get("advance_submission_competitions", [])
        if str(value).strip()
    }
    override_rules = schedule_map.get("bethel_overrides", {}).get("competition_time_overrides", [])

    def participant_group(row: dict) -> str:
        competition_type = str(row.get("competition_type", "")).strip()
        category = str(row.get("category_raw", "") or "")
        if competition_type == "choir":
            return "choir"
        if competition_type != "performing_arts":
            return ""
        if "ensemble" in category.lower() or "sign language" in category.lower():
            return "ensemble"
        return "individual"

    def matching_manual_override(row: dict) -> dict:
        competition_type = str(row.get("competition_type", "")).strip()
        group = participant_group(row)
        participant_name = str(row.get("participant_name", "")).strip().lower()
        response_id = str(row.get("response_id", "")).strip()
        best_match: tuple[int, dict] | None = None
        for override in override_rules:
            if str(override.get("competition_type", "")).strip() != competition_type:
                continue
            override_group = str(override.get("participant_group", "")).strip().lower()
            override_name = str(override.get("participant_name", "")).strip().lower()
            override_response_id = str(override.get("response_id", "")).strip()
            if override_response_id and override_response_id != response_id:
                continue
            if override_name and override_name != participant_name:
                continue
            if override_group and override_group != group:
                continue
            score = 0
            if override_response_id:
                score += 4
            if override_name:
                score += 2
            if override_group:
                score += 1
            if best_match is None or score > best_match[0]:
                best_match = (score, override)
        return best_match[1] if best_match else {}

    for row in competition_rows:
        competition_type = row["competition_type"]
        override = matching_manual_override(row)
        if override:
            rosters.append(
                {
                    "block_id": "",
                    "day_label": override.get("day_label", ""),
                    "event_date": override.get("event_date", ""),
                    "time_raw": override.get("time_raw", ""),
                    "event_title": override.get("event_title", ""),
                    "response_id": row["response_id"],
                    "participant_name": row["participant_name"],
                    "competition_type": competition_type,
                    "is_group_competition": row.get("is_group_competition", "false"),
                    "category_raw": row["category_raw"],
                    "schedule_status": "scheduled",
                    "schedule_source": "bethel_override",
                    "notes": " ".join(part for part in [override.get("notes", ""), row.get("notes", "")] if part).strip(),
                }
            )
            continue

        override = schedule_map.get("bethel_overrides", {}).get("competition_overrides", {}).get(competition_type, {})
        if override:
            rosters.append(
                {
                    "block_id": "",
                    "day_label": override.get("day_label", ""),
                    "event_date": override.get("event_date", ""),
                    "time_raw": override.get("time_raw", ""),
                    "event_title": override.get("event_title", ""),
                    "response_id": row["response_id"],
                    "participant_name": row["participant_name"],
                    "competition_type": competition_type,
                    "is_group_competition": row.get("is_group_competition", "false"),
                    "category_raw": row["category_raw"],
                    "schedule_status": "scheduled",
                    "schedule_source": "bethel_override",
                    "notes": " ".join(part for part in [override.get("notes", ""), row.get("notes", "")] if part).strip(),
                }
            )
            continue

        if competition_type in advance_submission_competitions:
            rosters.append(
                {
                    "block_id": "",
                    "day_label": "",
                    "event_date": "",
                    "time_raw": "",
                    "event_title": "",
                    "response_id": row["response_id"],
                    "participant_name": row["participant_name"],
                    "competition_type": competition_type,
                    "is_group_competition": row.get("is_group_competition", "false"),
                    "category_raw": row["category_raw"],
                    "schedule_status": "submitted_in_advance",
                    "schedule_source": "advance_submission",
                    "notes": "Submitted in advance; no live session time slot required.",
                }
            )
            continue

        keywords = keyword_map.get(competition_type, [])
        matched_blocks = [
            block
            for block in program_blocks
            for keyword in keywords
            if keyword.lower() in block["event_title"].lower()
        ]

        if not matched_blocks:
            rosters.append(
                {
                    "block_id": "",
                    "day_label": "",
                    "event_date": "",
                    "time_raw": "",
                    "event_title": "",
                    "response_id": row["response_id"],
                    "participant_name": row["participant_name"],
                    "competition_type": competition_type,
                    "is_group_competition": row.get("is_group_competition", "false"),
                    "category_raw": row["category_raw"],
                    "schedule_status": "unscheduled_in_program",
                    "schedule_source": "",
                    "notes": row.get("notes", ""),
                }
            )
            continue

        for block in matched_blocks:
            rosters.append(
                {
                    "block_id": block["block_id"],
                    "day_label": block.get("day_name", canonical_day_label(block["day_label"])),
                    "event_date": block["event_date"],
                    "time_raw": block["time_raw"],
                    "event_title": block["event_title"],
                    "response_id": row["response_id"],
                    "participant_name": row["participant_name"],
                    "competition_type": competition_type,
                    "is_group_competition": row.get("is_group_competition", "false"),
                    "category_raw": row["category_raw"],
                    "schedule_status": "scheduled",
                    "schedule_source": block.get("schedule_source", "state_program"),
                    "notes": row.get("notes", ""),
                }
            )

    return rosters


def map_excursions_to_days(
    excursion_rows: List[dict],
    schedule_map: dict,
) -> List[dict]:
    rosters: List[dict] = []
    aliases = schedule_map.get("excursion_day_aliases", {})

    for row in excursion_rows:
        if row.get("interested") != "true":
            continue

        excursion_name = row["excursion_name"]
        override = schedule_map.get("bethel_overrides", {}).get("excursion_overrides", {}).get(excursion_name, {})
        if override:
            rosters.append(
                {
                    "response_id": row["response_id"],
                    "contact_phone": row["contact_phone"],
                    "excursion_name": excursion_name,
                    "scheduled_day_label": override.get("day_label", ""),
                    "scheduled_date": override.get("event_date", ""),
                    "schedule_status": "scheduled",
                    "schedule_source": "bethel_override",
                    "notes": override.get("notes", ""),
                }
            )
            continue

        day_hint = ""
        parenthetical = re.search(r"\(([^)]+)\)", excursion_name)
        if parenthetical:
            hint_text = parenthetical.group(1).strip()
            for key, mapped_day in aliases.items():
                if key.lower() in hint_text.lower():
                    day_hint = mapped_day
                    break
            if not day_hint:
                day_hint = hint_text

        rosters.append(
            {
                "response_id": row["response_id"],
                "contact_phone": row["contact_phone"],
                "excursion_name": excursion_name,
                "scheduled_day_label": day_hint,
                "scheduled_date": DAY_TO_DATE.get(day_hint, ""),
                "schedule_status": "scheduled" if day_hint else "unscheduled",
                "schedule_source": "state_program" if day_hint else "",
                "notes": "",
            }
        )

    return rosters


def build_participant_conflicts(competition_event_rows: List[dict]) -> List[dict]:
    conflicts: List[dict] = []
    grouped: Dict[tuple[str, str, str, str], List[dict]] = {}

    for row in competition_event_rows:
        if row.get("schedule_status") != "scheduled":
            continue
        participant_name = (row.get("participant_name") or "").strip()
        if not participant_name:
            continue
        key = (row["response_id"], participant_name.lower(), row["event_date"], row["time_raw"])
        grouped.setdefault(key, []).append(row)

    for entries in grouped.values():
        if len(entries) < 2:
            continue
        conflicts.append(
            {
                "response_id": entries[0]["response_id"],
                "participant_name": entries[0]["participant_name"],
                "day_label": entries[0]["day_label"],
                "event_date": entries[0]["event_date"],
                "time_raw": entries[0]["time_raw"],
                "conflict_type": "same_time_competition_overlap",
                "event_titles": " | ".join(entry["event_title"] for entry in entries),
                "competition_types": " | ".join(entry["competition_type"] for entry in entries),
                "notes": "Participant appears in multiple scheduled competition blocks with the same time slot.",
            }
        )

    return conflicts


def build_daily_program_summary(
    program_blocks: List[dict],
    competition_event_rows: List[dict],
    excursion_day_rows: List[dict],
) -> List[dict]:
    day_keys = {(block["day_label"], block["event_date"]) for block in program_blocks if block["day_label"]}
    day_keys = {(canonical_day_label(day_label), event_date) for day_label, event_date in day_keys}
    day_keys.update(
        (row["scheduled_day_label"], row["scheduled_date"])
        for row in excursion_day_rows
        if row.get("scheduled_day_label")
    )

    summaries: List[dict] = []
    for day_label, event_date in sorted(day_keys, key=lambda item: (item[1] or "9999-99-99", item[0])):
        blocks_for_day = [block for block in program_blocks if block["day_label"] == day_label]
        scheduled_competitions = [
            row
            for row in competition_event_rows
            if row.get("schedule_status") == "scheduled" and row.get("day_label") == day_label
        ]
        excursions_for_day = [row for row in excursion_day_rows if row.get("scheduled_day_label") == day_label]
        operational_blocks = [
            block
            for block in program_blocks
            if canonical_day_label(block["day_label"]) == day_label and is_operational_highlight(block)
        ]

        summaries.append(
            {
                "day_label": day_label,
                "event_date": event_date,
                "program_event_count": len(
                    [block for block in program_blocks if canonical_day_label(block["day_label"]) == day_label]
                ),
                "competition_block_count": len({row["block_id"] for row in scheduled_competitions if row.get("block_id")}),
                "competition_participant_count": len(scheduled_competitions),
                "excursion_family_count": len(excursions_for_day),
                "excursion_options": " | ".join(sorted({row["excursion_name"] for row in excursions_for_day})),
                "schedule_sources": " | ".join(
                    sorted(
                        {
                            block.get("schedule_source", "")
                            for block in program_blocks
                            if canonical_day_label(block["day_label"]) == day_label and block.get("schedule_source", "")
                        }
                        | {row.get("schedule_source", "") for row in excursions_for_day if row.get("schedule_source", "")}
                    )
                ),
                "operational_highlights": " | ".join(block["event_title"] for block in operational_blocks[:8]),
            }
        )

    return summaries
