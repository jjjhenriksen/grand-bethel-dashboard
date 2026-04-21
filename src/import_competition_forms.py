from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import difflib
import re
import subprocess
import tempfile
from typing import Dict, Iterable, List

import yaml

from competition_patches import load_competition_patches, save_competition_patches
from load_raw import discover_input_csv, load_field_map, load_raw_csv
from normalize_responses import normalize_responses
from parse_family_attendance import parse_family_attendance


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
IGNORED_FILENAME_PATTERNS = ("state representative",)
OCR_SWIFT_SOURCE = """
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)
guard let image = NSImage(contentsOf: url) else {
    fputs("Could not load image\\n", stderr)
    exit(1)
}
guard let tiff = image.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let cgImage = rep.cgImage else {
    fputs("Could not rasterize image\\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])

for observation in request.results ?? [] {
    if let text = observation.topCandidates(1).first?.string {
        print(text)
    }
}
"""


@dataclass
class ImportedCompetitionEntry:
    source_file: str
    participant_name: str
    competition_type: str
    category_raw: str
    is_group_competition: str
    notes: str = ""
    response_id: str = ""
    status: str = "pending_match"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _first_name(value: str) -> str:
    parts = [part for part in _clean(value).split(" ") if part]
    return parts[0].title() if parts else ""


def _title_case_words(words: Iterable[str]) -> str:
    parts = [str(word).strip().title() for word in words if str(word).strip()]
    return " ".join(parts)


def _looks_like_name(value: str) -> bool:
    text = _clean(value)
    if not text:
        return False
    if any(char.isdigit() for char in text):
        return False
    lowered = text.lower()
    forbidden = {
        "age",
        "bethel",
        "birthdate",
        "guardian",
        "email",
        "phone",
        "address",
        "signature",
        "category",
        "title",
        "publisher",
        "arranger",
        "composer",
        "personal selection",
        "description",
        "representative",
        "committee",
        "council",
        "association",
    }
    return not any(token in lowered for token in forbidden)


def _extract_line_after_label(text: str, labels: list[str]) -> str:
    lines = [_clean(line) for line in str(text or "").splitlines()]
    for index, line in enumerate(lines):
        lowered = line.lower().rstrip(":")
        for label in labels:
            label_lower = label.lower().rstrip(":")
            if lowered == label_lower and index + 1 < len(lines):
                candidate = lines[index + 1]
                if candidate:
                    return candidate
            if lowered.startswith(label_lower + ":"):
                candidate = line.split(":", 1)[1].strip()
                if candidate:
                    return candidate
    return ""


def _render_to_image(source_path: Path, working_dir: Path) -> Path:
    if source_path.suffix.lower() == ".pdf":
        command = ["qlmanage", "-t", "-s", "2200", "-o", str(working_dir), str(source_path)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        image_path = working_dir / f"{source_path.name}.png"
        if not image_path.exists():
            raise FileNotFoundError(f"Quick Look preview was not generated for {source_path}")
        return image_path
    return source_path


def _ocr_text(source_path: Path) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = Path(temp_dir)
        image_path = _render_to_image(source_path, working_dir)
        script_path = working_dir / "ocr.swift"
        script_path.write_text(OCR_SWIFT_SOURCE, encoding="utf-8")
        result = subprocess.run(
            ["swift", str(script_path), str(image_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout


def _classify_competition_type(path: Path, text: str) -> str:
    combined = f"{path.name}\n{text}".lower()
    if "librarian" in combined:
        return "librarians_report"
    if "variety show" in combined:
        return "variety_show"
    if "choir competition" in combined:
        return "choir"
    if "arts and crafts" in combined:
        return "arts_and_crafts"
    if "performing arts entry form" in combined or "small ensemble" in combined:
        return "performing_arts"
    return ""


def _infer_arts_and_crafts_category(path: Path, text: str) -> str:
    category_match = re.search(r"(?:category of entry|digital art)[^0-9]{0,20}(\d+(?:/\d+)?)", text, re.IGNORECASE)
    if category_match:
        return category_match.group(1)

    combined = f"{path.name} {text}".lower()
    keyword_map = {
        "acrylic": "2",
        "paint": "2",
        "drawing": "2",
        "pencil": "2",
        "crochet": "3",
        "knitting": "3",
        "needle": "3",
        "photo": "4",
        "fabric": "5",
        "scrapbook": "6",
        "collage": "6",
        "digital": "7",
        "3d model": "7",
        "miscellaneous": "8",
        "pinterest": "8",
    }
    for keyword, category in keyword_map.items():
        if keyword in combined:
            return category
    return ""


def _infer_performing_arts_category(path: Path, text: str) -> str:
    combined = f"{path.name}\n{text}".lower()
    patterns = [
        ("vocal solo", "Vocal Soloist"),
        ("small ensemble", "Vocal or Instrumental Ensemble (This includes vocal duets)"),
        ("ensemble", "Vocal or Instrumental Ensemble (This includes vocal duets)"),
        ("dance", "Dance (Any Style)"),
        ("theater", "Theater (Monologue)"),
        ("instrumental", "Instrumental (Any instrument, including piano)"),
        ("sign language", "Sign Language (Individual or Ensemble) [Required Song: Forward All Job's Daughters]"),
        (
            "daughter musician",
            "Daughter Musician (Piano only) [Required Song: Now Our Work Is Over from Music Ritual]",
        ),
    ]
    for token, label in patterns:
        if token in combined:
            return label
    return ""


def _names_from_filename(path: Path) -> list[str]:
    stem = path.stem
    match = re.split(
        r"\b(entry|entries|entry forms|entry form|performing arts|arts and crafts|small ensemble|librarian'?s report|variety show|choir competition|form|google docs copy)\b",
        stem,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    candidate = match[0] if match else stem
    candidate = re.sub(r"[-_]", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate:
        return []

    if "small ensemble" in stem.lower():
        parts = [part for part in candidate.split(" ") if part and part.lower() != "and"]
        return [re.sub(r"[^A-Za-z']", "", part).title() for part in parts if re.sub(r"[^A-Za-z']", "", part)]

    first_token = re.sub(r"[^A-Za-z']", "", candidate.split(" ")[0])
    return [first_token.title()] if first_token else []


def _extract_participants(path: Path, text: str, competition_type: str) -> list[str]:
    filename_names = _names_from_filename(path)

    if competition_type == "performing_arts" and "small ensemble" in path.stem.lower():
        return filename_names

    label_candidates = {
        "choir": ["Name of Choir Representative"],
        "performing_arts": ["Bethel Daughter Name", "Name of Bethel Daughter", "Name of Ensemble Representative"],
        "arts_and_crafts": ["Name"],
        "librarians_report": ["Name"],
    }
    extracted = _extract_line_after_label(text, label_candidates.get(competition_type, ["Name"]))
    if extracted and _looks_like_name(extracted):
        participant = _first_name(extracted) if competition_type != "choir" else _title_case_words(extracted.split())
        if participant:
            return [participant]

    if filename_names and competition_type != "variety_show":
        return filename_names
    return []


def extract_entries_from_forms(forms_dir: Path) -> tuple[list[ImportedCompetitionEntry], list[str]]:
    entries: list[ImportedCompetitionEntry] = []
    issues: list[str] = []

    for path in sorted(forms_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS or path.name.startswith("."):
            continue
        lowered_name = path.name.lower()
        if any(pattern in lowered_name for pattern in IGNORED_FILENAME_PATTERNS):
            issues.append(f"Skipped non-competition form: {path.name}")
            continue

        try:
            text = _ocr_text(path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"OCR failed for {path.name}: {exc}")
            continue

        competition_type = _classify_competition_type(path, text)
        if not competition_type:
            issues.append(f"Could not classify form: {path.name}")
            continue

        if competition_type == "variety_show":
            issues.append(
                f"Could not auto-assign participant(s) for {path.name}; add a manual variety-show patch after review."
            )
            continue

        participants = _extract_participants(path, text, competition_type)
        if not participants:
            issues.append(f"Could not find participant name(s) in {path.name}")
            continue

        if competition_type == "arts_and_crafts":
            category_raw = _infer_arts_and_crafts_category(path, text)
            for participant in participants:
                entries.append(
                    ImportedCompetitionEntry(
                        source_file=path.name,
                        participant_name=participant,
                        competition_type=competition_type,
                        category_raw=category_raw,
                        is_group_competition="false",
                        notes="Imported from finalized competition form.",
                    )
                )
            continue

        if competition_type == "librarians_report":
            title = _extract_line_after_label(text, ["Title of Report"])
            for participant in participants:
                entries.append(
                    ImportedCompetitionEntry(
                        source_file=path.name,
                        participant_name=participant,
                        competition_type=competition_type,
                        category_raw=title,
                        is_group_competition="false",
                        notes="Imported from finalized competition form.",
                    )
                )
            continue

        if competition_type == "choir":
            for participant in participants:
                entries.append(
                    ImportedCompetitionEntry(
                        source_file=path.name,
                        participant_name=participant,
                        competition_type=competition_type,
                        category_raw="",
                        is_group_competition="true",
                        notes="Imported choir representative from finalized competition form.",
                    )
                )
            continue

        category_raw = _infer_performing_arts_category(path, text)
        is_group = "true" if "ensemble" in category_raw.lower() or competition_type == "choir" else "false"
        for participant in participants:
            entries.append(
                ImportedCompetitionEntry(
                    source_file=path.name,
                    participant_name=participant,
                    competition_type=competition_type,
                    category_raw=category_raw,
                    is_group_competition=is_group,
                    notes="Imported from finalized competition form.",
                )
            )

    return entries, issues


def _load_attendee_candidates(input_csv: Path, field_map_path: Path) -> list[dict]:
    field_map = load_field_map(field_map_path)
    raw_df, _ = load_raw_csv(input_csv, field_map)
    responses_df = normalize_responses(raw_df)

    attendees: list[dict] = []
    for _, row in responses_df.fillna("").iterrows():
        response = row.to_dict()
        parsed_attendees, _ = parse_family_attendance(response.get("family_attendance", ""))
        for attendee in parsed_attendees:
            attendees.append(
                {
                    "response_id": response["response_id"],
                    "attendee_name": attendee.attendee_name,
                }
            )
    return attendees


def _match_entry_to_response(entry: ImportedCompetitionEntry, attendee_candidates: list[dict]) -> ImportedCompetitionEntry:
    target = _normalize_name(entry.participant_name)
    target_first_name = _normalize_name(_first_name(entry.participant_name))
    if not target:
        entry.status = "missing_name"
        return entry

    exact_matches = [candidate for candidate in attendee_candidates if _normalize_name(candidate["attendee_name"]) == target]
    if len(exact_matches) == 1:
        entry.response_id = str(exact_matches[0]["response_id"]).strip()
        entry.status = "matched"
        return entry

    first_name_matches = [
        candidate
        for candidate in attendee_candidates
        if _normalize_name(_first_name(candidate["attendee_name"])) in {target, target_first_name}
    ]
    unique_response_ids = {str(candidate["response_id"]).strip() for candidate in first_name_matches}
    if len(unique_response_ids) == 1:
        entry.response_id = next(iter(unique_response_ids))
        entry.participant_name = _first_name(entry.participant_name)
        entry.status = "matched"
        return entry

    candidate_first_names = {_normalize_name(_first_name(candidate["attendee_name"])): candidate for candidate in attendee_candidates}
    close_matches = difflib.get_close_matches(target_first_name or target, list(candidate_first_names.keys()), n=2, cutoff=0.75)
    if len(close_matches) == 1:
        matched_candidate = candidate_first_names[close_matches[0]]
        entry.response_id = str(matched_candidate["response_id"]).strip()
        entry.participant_name = _first_name(matched_candidate["attendee_name"])
        entry.status = "matched"
        return entry

    entry.status = "ambiguous_match" if first_name_matches or exact_matches else "unmatched"
    return entry


def _patch_exists(existing_patches: list[dict], entry: ImportedCompetitionEntry) -> bool:
    for patch in existing_patches:
        if str(patch.get("action", "")).strip() != "add":
            continue
        if str(patch.get("response_id", "")).strip() != entry.response_id:
            continue
        if _normalize_name(patch.get("participant_name", "")) != _normalize_name(entry.participant_name):
            continue
        if str(patch.get("competition_type", "")).strip() != entry.competition_type:
            continue
        if _clean(patch.get("category_raw", "")) != _clean(entry.category_raw):
            continue
        return True
    return False


def _write_review_csv(review_path: Path, entries: list[ImportedCompetitionEntry]) -> None:
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "status",
                "source_file",
                "participant_name",
                "response_id",
                "competition_type",
                "category_raw",
                "is_group_competition",
                "notes",
            ],
        )
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "status": entry.status,
                    "source_file": entry.source_file,
                    "participant_name": entry.participant_name,
                    "response_id": entry.response_id,
                    "competition_type": entry.competition_type,
                    "category_raw": entry.category_raw,
                    "is_group_competition": entry.is_group_competition,
                    "notes": entry.notes,
                }
            )


def import_competition_forms(
    *,
    forms_dir: Path,
    competition_patches_path: Path,
    field_map_path: Path,
    review_path: Path,
    input_csv: Path | None = None,
    apply: bool = False,
) -> dict[str, object]:
    if not forms_dir.exists():
        raise FileNotFoundError(f"Forms directory does not exist: {forms_dir}")

    resolved_input_csv = input_csv if input_csv else discover_input_csv(field_map_path.parent.parent / "data" / "raw")
    attendee_candidates = _load_attendee_candidates(resolved_input_csv, field_map_path)
    imported_entries, issues = extract_entries_from_forms(forms_dir)
    matched_entries = [_match_entry_to_response(entry, attendee_candidates) for entry in imported_entries]

    _write_review_csv(review_path, matched_entries)

    patch_payload = load_competition_patches(competition_patches_path)
    existing_patches = patch_payload.get("patches", [])
    added_count = 0
    if apply:
        for entry in matched_entries:
            if entry.status != "matched":
                continue
            if _patch_exists(existing_patches, entry):
                continue
            existing_patches.append(
                {
                    "action": "add",
                    "participant_name": entry.participant_name,
                    "competition_type": entry.competition_type,
                    "category_raw": entry.category_raw,
                    "response_id": entry.response_id,
                    "is_group_competition": entry.is_group_competition,
                }
            )
            added_count += 1
        save_competition_patches(competition_patches_path, patch_payload)

    summary = {
        "total_entries": len(matched_entries),
        "matched_entries": sum(entry.status == "matched" for entry in matched_entries),
        "unmatched_entries": sum(entry.status != "matched" for entry in matched_entries),
        "written_patches": added_count,
        "review_path": str(review_path),
        "issues": issues,
        "entries": matched_entries,
    }
    return summary
