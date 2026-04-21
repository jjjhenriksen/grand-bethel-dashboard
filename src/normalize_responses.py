from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd


YES_VALUES = {"yes", "y", "true", "1", "attending"}
NO_VALUES = {"no", "n", "false", "0", "not attending"}
DOESNT_MATTER_VALUES = {"doesn't matter", "doesnt matter", "does not matter", "either"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_bool(value: str) -> str:
    text = clean_text(value).lower()
    if not text:
        return "unknown"
    if text in YES_VALUES or text.startswith("yes"):
        return "yes"
    if text in NO_VALUES or text.startswith("no"):
        return "no"
    return "unknown"


def normalize_preference(value: str) -> str:
    text = clean_text(value).lower()
    if not text:
        return "unknown"
    if text in YES_VALUES or text.startswith("yes"):
        return "yes"
    if text in NO_VALUES or text.startswith("no"):
        return "no"
    if text in DOESNT_MATTER_VALUES:
        return "does_not_matter"
    return "unknown"


def normalize_phone(value: str) -> str:
    text = str(value or "")
    raw_parts = re.split(r"[;,/]|(?:\s{2,})", text)
    candidates = [part.strip() for part in raw_parts if part.strip()]

    if len(candidates) == 1:
        all_digits = re.sub(r"\D+", "", text)
        if len(all_digits) in {20, 22}:
            chunk_size = 10 if len(all_digits) == 20 else 11
            candidates = [all_digits[i : i + chunk_size] for i in range(0, len(all_digits), chunk_size)]

    normalized_numbers: list[str] = []
    for candidate in candidates:
        digits = re.sub(r"\D+", "", candidate)
        if len(digits) == 10:
            normalized_numbers.append(f"{digits[:3]}-{digits[3:6]}-{digits[6:]}")
        elif len(digits) == 11 and digits.startswith("1"):
            normalized_numbers.append(f"{digits[1:4]}-{digits[4:7]}-{digits[7:]}")

    if normalized_numbers:
        deduped = list(dict.fromkeys(normalized_numbers))
        return "; ".join(deduped)

    return clean_text(value)


def response_id_for_index(index: int) -> str:
    return f"R{index + 1:04d}"


def normalize_response_record(record: Dict[str, str], response_id: str) -> Dict[str, str]:
    normalized = {column: str(value).strip() for column, value in record.items()}
    normalized["response_id"] = str(response_id).strip()
    normalized["contact_phone"] = normalize_phone(normalized.get("contact_phone", ""))
    normalized["emergency_contact_name"] = clean_text(normalized.get("emergency_contact_name", ""))
    normalized["emergency_contact_phone"] = normalize_phone(normalized.get("emergency_contact_phone", ""))
    normalized["attending_grand_bethel"] = normalize_bool(normalized.get("attending_grand_bethel", ""))
    normalized["family_room_preference"] = normalize_preference(normalized.get("family_room_preference", ""))
    normalized["girl_adult_only_room_preference"] = normalize_preference(
        normalized.get("girl_adult_only_room_preference", "")
    )
    normalized["bed_share_acknowledged"] = normalize_bool(normalized.get("bed_share_acknowledged", ""))
    normalized["allergies_raw"] = clean_text(normalized.get("allergies_raw", ""))
    normalized["excursions_raw"] = clean_text(normalized.get("excursions_raw", ""))
    for field in [
        "variety_show_interest",
        "choir_interest",
        "performing_arts_interest",
        "arts_and_crafts_interest",
        "librarians_report_interest",
        "essay_interest",
        "ritual_interest",
        "sew_and_show_interest",
    ]:
        normalized[field] = normalize_bool(normalized.get(field, ""))
    return normalized


def normalize_responses(raw_df: pd.DataFrame) -> pd.DataFrame:
    records: List[Dict[str, str]] = []
    for index, row in raw_df.fillna("").iterrows():
        raw_record = {column: str(value).strip() for column, value in row.items()}
        records.append(normalize_response_record(raw_record, response_id_for_index(index)))
    return pd.DataFrame(records)
