from __future__ import annotations

import re
from typing import Dict, List, Tuple


MEAL_CODE_PATTERN = re.compile(r"\b([THCSVP])\b", re.IGNORECASE)
NAMED_MEAL_TEXT_PATTERN = re.compile(
    r"([A-Za-z][A-Za-z' ]*[A-Za-z])\s*[-:]\s*(.*?)(?=(?:\s+[A-Za-z][A-Za-z' ]*[A-Za-z]\s*[-:])|[,;\n]|$)",
    re.IGNORECASE,
)

MEAL_TEXT_ALIASES = {
    "turkey": "T",
    "classic turkey sandwich": "T",
    "ham": "H",
    "classic ham sandwich": "H",
    "chicken strips": "C",
    "chicken strip": "C",
    "chicken strips and fries": "C",
    "chicken strip and fries": "C",
    "fries": "C",
    "chicken caesar salad": "S",
    "caesar salad": "S",
    "chicken cesar salad": "S",
    "cesar salad": "S",
    "caprese": "V",
    "caprese sandwich": "V",
    "pizza": "P",
    "child pizza": "P",
    "childs pizza": "P",
}


def parse_meal_codes(raw_text: str) -> List[str]:
    return [match.upper() for match in MEAL_CODE_PATTERN.findall(str(raw_text or ""))]


def _normalize_meal_text(text: str) -> str:
    cleaned = str(text or "").lower()
    cleaned = cleaned.replace("&", "and")
    cleaned = cleaned.replace("child's", "child")
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", cleaned)
    return " ".join(cleaned.split())


def meal_text_to_code(raw_text: str) -> str:
    normalized = _normalize_meal_text(raw_text)
    if not normalized:
        return ""
    if normalized in MEAL_TEXT_ALIASES:
        return MEAL_TEXT_ALIASES[normalized]
    for alias, code in sorted(MEAL_TEXT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in normalized:
            return code
    return ""


def _match_label_to_attendee(label: str, attendee_names: List[str]) -> str:
    cleaned_label = str(label or "").strip()
    if not cleaned_label:
        return ""

    normalized_label = cleaned_label.lower()
    for attendee_name in attendee_names:
        if attendee_name.strip().lower() == normalized_label:
            return attendee_name

    if len(normalized_label) == 1:
        matches = [
            attendee_name
            for attendee_name in attendee_names
            if attendee_name.strip() and attendee_name.strip()[0].lower() == normalized_label
        ]
        if len(matches) == 1:
            return matches[0]

    return cleaned_label.title()


def build_meal_rows(response_id: str, attendees: List[dict], raw_text: str, meal_map: Dict[str, str]) -> Tuple[List[dict], List[dict]]:
    raw = str(raw_text or "").strip()
    if not raw:
        return [], []

    rows: List[dict] = []
    flags: List[dict] = []
    named_assignments: List[Tuple[str, str]] = []
    unnamed_codes: List[str] = []

    attendee_names = [attendee["attendee_name"] for attendee in attendees]

    for named_match in NAMED_MEAL_TEXT_PATTERN.finditer(raw):
        label = named_match.group(1).strip()
        meal_text = named_match.group(2).strip()
        code = meal_text_to_code(meal_text)
        if not code and len(meal_text) == 1:
            code = meal_text.upper() if meal_text.upper() in meal_map else ""
        if code:
            named_assignments.append((_match_label_to_attendee(label, attendee_names), code))

    residual_text = NAMED_MEAL_TEXT_PATTERN.sub(" ", raw)
    unnamed_codes.extend(parse_meal_codes(residual_text))
    for segment in re.split(r"[,;\n]+", residual_text):
        code = meal_text_to_code(segment)
        if code:
            unnamed_codes.append(code)

    for name, code in named_assignments:
        rows.append(
            {
                "response_id": response_id,
                "attendee_name_if_known": name,
                "meal_code": code,
                "meal_name": meal_map.get(code, ""),
                "raw_lunch_text": raw,
                "parse_confidence": "high",
            }
        )

    used_names = {name for name, _ in named_assignments}
    remaining_names = [name for name in attendee_names if name not in used_names]
    unnamed_confidence = "medium" if len(remaining_names) == len(unnamed_codes) else "low"

    for index, code in enumerate(unnamed_codes):
        rows.append(
            {
                "response_id": response_id,
                "attendee_name_if_known": remaining_names[index] if index < len(remaining_names) else "",
                "meal_code": code,
                "meal_name": meal_map.get(code, ""),
                "raw_lunch_text": raw,
                "parse_confidence": unnamed_confidence,
            }
        )

    if len(rows) != len(attendees):
        flags.append(
            {
                "severity": "warning",
                "issue_type": "lunch_count_cannot_be_aligned_with_attendee_count",
                "field_name": "lunch_raw",
                "issue_detail": f"Parsed {len(rows)} lunch choices for {len(attendees)} attendees.",
            }
        )

    if raw and not rows:
        flags.append(
            {
                "severity": "warning",
                "issue_type": "lunch_parse_failed",
                "field_name": "lunch_raw",
                "issue_detail": f"Unable to parse lunch choices from: {raw}",
            }
        )

    return rows, flags
