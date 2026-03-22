from __future__ import annotations

import re
from typing import Dict, List, Tuple


DETAIL_PAIR_RE = re.compile(
    r"([A-Za-z][A-Za-z' ]*[A-Za-z])\s*(?:-|:)?\s*(category\s*\d+(?:/\d+)?|\d+(?:/\d+)?|[A-Za-z][^,;\n]*)?",
    re.IGNORECASE,
)
SEQUENTIAL_CATEGORY_RE = re.compile(
    r"([A-Za-z][A-Za-z' ]*[A-Za-z])\s*(?:category\s*)?(\d+(?:/\d+)?)?(?=(?:\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*(?:category\s*\d+(?:/\d+)?|\d+(?:/\d+)?)?)|$)",
    re.IGNORECASE,
)
INLINE_CATEGORY_RE = re.compile(
    r"([A-Za-z][A-Za-z' ]*?[A-Za-z])\s+(?:category\s+)?(\d+(?:/\d+)?)",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _first_name(value: str) -> str:
    parts = [part for part in _clean(value).split(" ") if part]
    return parts[0].title() if parts else ""


def _split_names(value: str) -> List[str]:
    parts = re.split(r"[\n,;&]+", str(value or ""))
    return [_first_name(part) for part in parts if _clean(part)]


def _parse_detail_pairs(value: str) -> List[Tuple[str, str]]:
    text = str(value or "").replace("\r", "\n").strip()
    if not text:
        return []

    if "---" in text:
        name, category = re.split(r"\s*-{2,}\s*", text, maxsplit=1)
        return [(_first_name(name), _clean(category))]

    if " and " in text.lower() and not re.search(r"\d", text):
        return [(name, "") for name in _split_names(text.replace(" and ", ","))]

    parts = re.split(r"[\n,;]+", text)
    if len(parts) > 1:
        pairs: List[Tuple[str, str]] = []
        for part in parts:
            cleaned = _clean(part)
            if not cleaned:
                continue
            if "-" in cleaned or ":" in cleaned:
                name, category = re.split(r"\s*[-:]\s*", cleaned, maxsplit=1)
                pairs.append((_first_name(name), category.strip()))
            else:
                match = DETAIL_PAIR_RE.fullmatch(cleaned)
                if match:
                    pairs.append((_first_name(match.group(1)), _clean(match.group(2))))
                else:
                    pairs.append((_first_name(cleaned), ""))
        return pairs

    if "category" in text.lower():
        pairs = [(_first_name(match.group(1)), _clean(match.group(2))) for match in INLINE_CATEGORY_RE.finditer(text)]
        if pairs:
            return pairs

    if re.search(r"\d", text):
        pairs = []
        for match in SEQUENTIAL_CATEGORY_RE.finditer(text):
            name = _first_name(match.group(1))
            category = _clean(match.group(2))
            if name:
                pairs.append((name, category))
        if pairs:
            return pairs

    return [(_first_name(match.group(1)), _clean(match.group(2))) for match in DETAIL_PAIR_RE.finditer(text)]


def build_competition_rows(row: Dict[str, str], competition_config: Dict[str, dict]) -> Tuple[List[dict], List[dict]]:
    rows: List[dict] = []
    flags: List[dict] = []

    for competition_type, config in competition_config.items():
        configured_group_competition = bool(config.get("is_group_competition", False))
        interest_field = config.get("interest_field", "")
        interest = row.get(interest_field, "unknown")
        names_raw = row.get(config.get("names_field", ""), "")
        detail_raw = row.get(config.get("detail_field", ""), "")
        categories_raw = row.get(config.get("categories_field", ""), "")

        pairs = _parse_detail_pairs(detail_raw) if detail_raw else []
        if not pairs and names_raw:
            pairs = [(name, "") for name in _split_names(names_raw)]

        if interest == "yes" and not pairs:
            rows.append(
                {
                    "response_id": row["response_id"],
                    "participant_name": "",
                    "competition_type": competition_type,
                    "is_group_competition": "true" if configured_group_competition else "false",
                    "category_raw": categories_raw,
                    "source_field": detail_raw and config.get("detail_field", "") or interest_field,
                    "notes": "Interest marked yes but no participant detail provided.",
                }
            )

        if interest != "yes" and pairs:
            flags.append(
                {
                    "severity": "warning",
                    "issue_type": "competition_yes_no_mismatch",
                    "field_name": interest_field,
                    "issue_detail": f"{competition_type} has participant detail but interest field is {interest}.",
                }
            )

        for participant_name, category in pairs:
            is_group_competition = configured_group_competition
            if competition_type == "performing_arts" and category:
                lowered_category = str(category).lower()
                if "ensemble" in lowered_category or "sign language" in lowered_category:
                    is_group_competition = True
            rows.append(
                {
                    "response_id": row["response_id"],
                    "participant_name": participant_name,
                    "competition_type": competition_type,
                    "is_group_competition": "true" if is_group_competition else "false",
                    "category_raw": category or categories_raw,
                    "source_field": config.get("detail_field", "") if detail_raw else config.get("names_field", ""),
                    "notes": "" if category else ("Using family-level categories." if categories_raw else ""),
                }
            )

    return rows, flags
