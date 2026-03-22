from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path
from typing import List


TIME_RANGE_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}\s*(?:am|pm)|TBA)\s*(?:-\s*(?P<end>\d{1,2}:\d{2}\s*(?:am|pm)))?$",
    re.IGNORECASE,
)


def _strip_md(text: str) -> str:
    cleaned = text.replace("\\", "")
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"~~(.*?)~~", r"\1", cleaned)
    cleaned = re.sub(r"~(.*?)~", r"\1", cleaned)
    cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned)
    cleaned = re.sub(r"\[(.*?)\]", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _split_row(line: str) -> list[str]:
    return [_strip_md(cell) for cell in line.strip().strip("|").split("|")]


def _parse_day_header(cells: list[str]) -> tuple[str, str] | None:
    for cell in cells:
        cleaned = _strip_md(cell)
        if re.match(r"^(Wednesday|Thursday|Friday|Saturday|Sunday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}$", cleaned):
            parsed = datetime.strptime(cleaned, "%A, %B %d, %Y")
            return cleaned, parsed.date().isoformat()
    return None


def _parse_time_range(raw_time: str) -> tuple[str, str]:
    text = _strip_md(raw_time)
    if not text:
        return "", ""
    match = TIME_RANGE_RE.match(text)
    if not match:
        return text, ""
    start = match.group("start") or ""
    end = match.group("end") or ""
    return start, end


def canonical_day_label(day_label: str) -> str:
    return _strip_md(day_label).split(",")[0].strip()


def parse_program_blocks(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: List[dict] = []
    current_day_label = ""
    current_event_date = ""
    current_time_raw = ""
    current_start_time = ""
    current_end_time = ""
    block_counter = 0

    for line in lines:
        if not line.strip().startswith("|"):
            continue

        cells = _split_row(line)
        if len(cells) < 4:
            continue

        if all(re.fullmatch(r"[:\- ]+", cell or "") for cell in cells):
            continue

        day_header = _parse_day_header(cells)
        if day_header:
            current_day_label, current_event_date = day_header
            current_time_raw = ""
            current_start_time = ""
            current_end_time = ""
            continue

        if cells[0].lower() == "time":
            continue

        time_raw = cells[0]
        event_title = cells[1]
        dress_code = cells[3]

        if not event_title:
            continue

        if _parse_day_header([event_title]):
            day_label, event_date = _parse_day_header([event_title])  # type: ignore[assignment]
            current_day_label = day_label
            current_event_date = event_date
            current_time_raw = ""
            current_start_time = ""
            current_end_time = ""
            continue

        if time_raw:
            current_time_raw = time_raw
            current_start_time, current_end_time = _parse_time_range(time_raw)
            display_time_raw = time_raw
        elif not time_raw:
            display_time_raw = ""
            embedded_time_match = re.match(
                r"^(?P<time>\d{1,2}:\d{2}\s*(?:am|pm)(?:\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm))?)\s+(?P<title>.+)$",
                event_title,
                re.IGNORECASE,
            )
            if embedded_time_match:
                current_time_raw = embedded_time_match.group("time")
                current_start_time, current_end_time = _parse_time_range(current_time_raw)
                event_title = embedded_time_match.group("title").strip()
                display_time_raw = current_time_raw

        block_counter += 1
        blocks.append(
            {
                "block_id": f"B{block_counter:03d}",
                "day_label": current_day_label,
                "day_name": canonical_day_label(current_day_label),
                "event_date": current_event_date,
                "time_raw": current_time_raw,
                "display_time_raw": display_time_raw,
                "start_time_raw": current_start_time,
                "end_time_raw": current_end_time,
                "event_title": event_title,
                "dress_code": dress_code,
                "event_type": classify_event_type(event_title),
                "schedule_source": "state_program",
            }
        )

    return blocks


def build_override_block(block_id: str, block: dict) -> dict:
    start_time_raw, end_time_raw = _parse_time_range(block.get("time_raw", ""))
    day_label = block["day_label"]
    return {
        "block_id": block_id,
        "day_label": day_label,
        "day_name": canonical_day_label(day_label),
        "event_date": block["event_date"],
        "time_raw": block.get("time_raw", ""),
        "display_time_raw": block.get("time_raw", ""),
        "start_time_raw": start_time_raw,
        "end_time_raw": end_time_raw,
        "event_title": block["event_title"],
        "dress_code": block.get("dress_code", ""),
        "event_type": block.get("event_type", "bethel_local"),
        "schedule_source": "bethel_override",
    }


def recompute_block_fields(block: dict) -> dict:
    start_time_raw, end_time_raw = _parse_time_range(block.get("time_raw", ""))
    day_label = block.get("day_label", "")
    block["day_name"] = canonical_day_label(day_label) if day_label else block.get("day_name", "")
    block["start_time_raw"] = start_time_raw
    block["end_time_raw"] = end_time_raw
    if "display_time_raw" not in block:
        block["display_time_raw"] = block.get("time_raw", "")
    return block


def classify_event_type(event_title: str) -> str:
    lowered = event_title.lower()
    if "competition" in lowered or "awards" in lowered or "fashion show" in lowered or "variety show" in lowered:
        return "competition_related"
    if "practice" in lowered:
        return "practice"
    if "luncheon" in lowered or "festivities" in lowered:
        return "meal_or_social"
    if "registration" in lowered or "pick up" in lowered or "turn in" in lowered or "drop off" in lowered:
        return "logistics"
    return "program"
