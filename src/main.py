from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
from typing import Dict, List

import pandas as pd
import yaml

from bethel_overrides import (
    add_extra_block,
    load_overrides,
    reset_overrides,
    set_block_assignment,
    set_competition_override,
    set_competition_time_override,
    set_excursion_override,
    summarize_overrides,
)
from attendee_patches import (
    add_attendee_patch,
    apply_attendee_patches,
    load_attendee_patches,
    reset_attendee_patches,
    summarize_attendee_patches,
)
from assignment_logic import apply_assignment_patches, build_assignment_rows
from assignment_patches import (
    add_assignment_patch,
    load_assignment_patches,
    reset_assignment_patches,
    summarize_assignment_patches,
)
from competition_patches import (
    add_competition_patch,
    apply_competition_patches,
    load_competition_patches,
    reset_competition_patches,
    summarize_competition_patches,
)
from excursion_patches import (
    add_excursion_patch,
    apply_excursion_patches,
    load_excursion_patches,
    reset_excursion_patches,
    summarize_excursion_patches,
)
from derive_rooming import build_rooming_rows
from enrich_schedule import (
    build_daily_program_summary,
    build_participant_conflicts,
    merge_program_with_overrides,
    map_competitions_to_blocks,
    map_excursions_to_days,
)
from import_competition_forms import import_competition_forms
from load_raw import discover_input_csv, load_field_map, load_raw_csv
from normalize_responses import normalize_responses
from parse_competitions import build_competition_rows
from parse_excursions import build_excursion_rows, derive_excursion_options
from parse_family_attendance import parse_family_attendance
from parse_meals import build_meal_rows
from parse_program import parse_program_blocks
from program_patches import (
    add_patch,
    apply_program_patches,
    load_program_patches,
    reset_program_patches,
    summarize_program_patches,
)
from respondent_patches import (
    add_respondent_patch,
    apply_respondent_patches,
    load_respondent_patches,
    reset_respondent_patches,
    summarize_respondent_patches,
)
from schedule_config import (
    add_advance_submission_competition,
    load_schedule_map,
    remove_advance_submission_competition,
    set_competition_timing_keywords,
    summarize_competition_timing,
)
from validate import flag_duplicate_attendee_names, validate_response
from write_outputs import write_outputs


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "outputs"
BETHEL_OVERRIDES_PATH = CONFIG_DIR / "bethel_overrides.yaml"
PROGRAM_PATCHES_PATH = CONFIG_DIR / "program_patches.yaml"
COMPETITION_PATCHES_PATH = CONFIG_DIR / "competition_patches.yaml"
ATTENDEE_PATCHES_PATH = CONFIG_DIR / "attendee_patches.yaml"
EXCURSION_PATCHES_PATH = CONFIG_DIR / "excursion_patches.yaml"
SCHEDULE_MAP_PATH = CONFIG_DIR / "schedule_map.yaml"
ASSIGNMENT_PATCHES_PATH = CONFIG_DIR / "assignment_patches.yaml"
RESPONDENT_PATCHES_PATH = CONFIG_DIR / "respondent_patches.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def attendee_row(response_row: Dict[str, str], attendee: object) -> Dict[str, str]:
    return {
        "response_id": response_row["response_id"],
        "timestamp": response_row.get("timestamp", ""),
        "contact_phone": response_row.get("contact_phone", ""),
        "emergency_contact_name": response_row.get("emergency_contact_name", ""),
        "emergency_contact_phone": response_row.get("emergency_contact_phone", ""),
        "attendee_name": attendee.attendee_name,
        "attendee_age_raw": attendee.attendee_age_raw,
        "attendee_age_normalized": attendee.attendee_age_normalized,
        "attendee_type": attendee.attendee_type,
        "family_room_preference": response_row.get("family_room_preference", ""),
        "girl_adult_only_room_preference": response_row.get("girl_adult_only_room_preference", ""),
        "bed_share_acknowledged": response_row.get("bed_share_acknowledged", ""),
        "allergies_raw": response_row.get("allergies_raw", ""),
        "attending_grand_bethel": response_row.get("attending_grand_bethel", ""),
    }


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    return df.loc[:, columns]


def normalize_density_tag(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "": "",
        "none": "",
        "off": "",
        "clear": "",
        "low": "",
        "watch": "medium",
        "medium": "medium",
        "high": "high",
        "high_density": "high",
    }
    return mapping.get(normalized, normalized)


def build_summary(
    responses_df: pd.DataFrame,
    attendees_df: pd.DataFrame,
    competitions_df: pd.DataFrame,
    excursions_df: pd.DataFrame,
    meals_df: pd.DataFrame,
    flags_df: pd.DataFrame,
    program_blocks_df: pd.DataFrame,
    competition_event_rosters_df: pd.DataFrame,
    participant_conflicts_df: pd.DataFrame,
) -> dict:
    selected_excursions = excursions_df[excursions_df["interested"] == "true"] if not excursions_df.empty else excursions_df
    return {
        "total_responses": int(len(responses_df)),
        "yes_attending_count": int((responses_df["attending_grand_bethel"] == "yes").sum()),
        "total_attendees": int(len(attendees_df)),
        "daughters_count": int((attendees_df["attendee_type"] == "daughter").sum()),
        "adults_count": int((attendees_df["attendee_type"] == "adult").sum()),
        "meal_counts_by_code": dict(sorted(Counter(meals_df["meal_code"]).items())) if not meals_df.empty else {},
        "competition_counts_by_type": dict(sorted(Counter(competitions_df["competition_type"]).items())) if not competitions_df.empty else {},
        "excursion_counts_by_option": dict(sorted(Counter(selected_excursions["excursion_name"]).items())) if not selected_excursions.empty else {},
        "flagged_record_counts": int(flags_df["response_id"].nunique()) if not flags_df.empty else 0,
        "program_block_count": int(len(program_blocks_df)),
        "scheduled_competition_roster_count": int(
            (competition_event_rosters_df["schedule_status"] == "scheduled").sum()
        )
        if not competition_event_rosters_df.empty
        else 0,
        "participant_conflict_count": int(len(participant_conflicts_df)),
    }


def load_output_csv(name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run the pipeline first.")
    return pd.read_csv(path).fillna("")


def print_table(df: pd.DataFrame, columns: list[str]) -> None:
    if df.empty:
        print("No rows.")
        return
    trimmed = df.loc[:, [column for column in columns if column in df.columns]].copy()
    for _, row in trimmed.iterrows():
        print(" | ".join(str(row.get(column, "")) for column in trimmed.columns))


def _bool_label(value: str) -> str:
    return "Group" if str(value).strip().lower() == "true" else "Individual"


def _source_label(value: str) -> str:
    source = str(value or "").strip()
    labels = {
        "arts_and_crafts_participant_categories": "Participant categories",
        "performing_arts_participant_categories": "Participant categories",
        "variety_show_names": "Submitted names",
        "choir_names": "Submitted names",
        "librarians_report_names": "Submitted names",
        "competition_patch": "Manual patch",
    }
    return labels.get(source, source.replace("_", " ").strip().title())


def _compact_category(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "No category detail"

    numbered_categories = re.findall(r"Category\s+(\d+)", text, re.IGNORECASE)
    if numbered_categories:
        unique_numbers: list[str] = []
        for number in numbered_categories:
            if number not in unique_numbers:
                unique_numbers.append(number)
        return "Categories " + ", ".join(unique_numbers)

    if re.fullmatch(r"\d+(?:/\d+)+", text):
        return "Categories " + ", ".join(text.split("/"))

    if re.fullmatch(r"\d+", text):
        return f"Category {text}"

    cleaned = re.sub(r"\s+", " ", text)
    return cleaned


def print_competition_list(df: pd.DataFrame) -> None:
    if df.empty:
        print("No rows.")
        return

    ordered = df.astype(
        {
            "competition_type": "string",
            "participant_name": "string",
            "response_id": "string",
            "category_raw": "string",
        },
        copy=True,
    ).sort_values(["competition_type", "participant_name", "response_id", "category_raw"])

    grouped = ordered.groupby("competition_type", sort=False)
    first_group = True
    for competition_type, group_df in grouped:
        if not first_group:
            print()
        first_group = False
        print(str(competition_type).replace("_", " ").title())

        names = [
            str(name).strip() or "Unnamed participant"
            for name in group_df["participant_name"].tolist()
        ]
        compact_names = ", ".join(names)
        all_group = (
            not group_df.empty
            and group_df["is_group_competition"].astype(str).str.lower().eq("true").all()
        )
        has_detail = any(
            _compact_category(value) != "No category detail" or str(note).strip()
            for value, note in zip(group_df["category_raw"].tolist(), group_df["notes"].tolist())
        )
        if all_group and not has_detail:
            print(f"{len(names)} participants: {compact_names}")
            continue

        for _, row in group_df.iterrows():
            participant_name = str(row.get("participant_name", "")).strip() or "Unnamed participant"
            response_id = str(row.get("response_id", "")).strip()
            category = _compact_category(row.get("category_raw", ""))
            source = _source_label(row.get("source_field", ""))
            notes = str(row.get("notes", "")).strip()
            summary = f"- {participant_name} ({response_id}) [{_bool_label(row.get('is_group_competition', 'false'))}]"
            print(summary)
            detail_parts: list[str] = []
            if category != "No category detail":
                detail_parts.append(category)
            if source and source not in {"Submitted names"}:
                detail_parts.append(source)
            if notes:
                detail_parts.append(notes)
            if detail_parts:
                print(f"  {' | '.join(detail_parts)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grand Bethel registration and schedule planning CLI.")
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="{run,program,respondent,override,competition,attendee,assignment,excursion,examples}",
    )

    run_parser = subparsers.add_parser("run", help="Run the registration and schedule pipeline.")
    run_parser.set_defaults(route="run")
    run_parser.add_argument("--input", type=Path, help="Path to the raw CSV export. Defaults to the only CSV in data/raw.")

    program_parser = subparsers.add_parser("program", help="Manage parsed program blocks and program patches.")
    program_subparsers = program_parser.add_subparsers(dest="program_command")

    program_list_parser = program_subparsers.add_parser("list", help="List parsed program blocks.")
    program_list_parser.set_defaults(route="program.list")
    program_list_parser.add_argument("--day", default="", help="Optional day filter like Thursday or Friday.")

    program_update_parser = program_subparsers.add_parser("update", help="Patch a parsed program block.")
    program_update_parser.set_defaults(route="program.update")
    program_update_parser.add_argument("--block-id", required=True)
    program_update_parser.add_argument("--day-label")
    program_update_parser.add_argument("--event-date")
    program_update_parser.add_argument("--time-raw")
    program_update_parser.add_argument("--event-title")
    program_update_parser.add_argument("--dress-code")
    program_update_parser.add_argument("--event-type")
    program_update_parser.add_argument("--audience-tag")
    program_update_parser.add_argument("--density-tag")

    program_remove_parser = program_subparsers.add_parser("remove", help="Remove a parsed program block from outputs.")
    program_remove_parser.set_defaults(route="program.remove")
    program_remove_parser.add_argument("--block-id", required=True)

    program_remove_by_name_parser = program_subparsers.add_parser(
        "remove-by-name",
        help="Remove parsed program block(s) by exact event title match.",
    )
    program_remove_by_name_parser.set_defaults(route="program.remove_by_name")
    program_remove_by_name_parser.add_argument("--event-title", required=True)

    program_remove_many_parser = program_subparsers.add_parser(
        "remove-many-by-name",
        help="Remove multiple parsed program block(s) by exact event title match.",
    )
    program_remove_many_parser.set_defaults(route="program.remove_many_by_name")
    program_remove_many_parser.add_argument(
        "--event-title",
        action="append",
        required=True,
        help="Repeat this flag for each exact event title you want to remove.",
    )

    program_show_parser = program_subparsers.add_parser("show-patches", help="Print the current program patch file.")
    program_show_parser.set_defaults(route="program.show_patches")
    program_reset_parser = program_subparsers.add_parser("reset-patches", help="Reset program patches back to an empty template.")
    program_reset_parser.set_defaults(route="program.reset_patches")

    respondent_parser = subparsers.add_parser("respondent", help="Manage synthetic respondent rows without editing the raw CSV.")
    respondent_subparsers = respondent_parser.add_subparsers(dest="respondent_command")

    respondent_add_parser = respondent_subparsers.add_parser("add", help="Add one synthetic respondent row.")
    respondent_add_parser.set_defaults(route="respondent.add")
    respondent_add_parser.add_argument("--response-id", required=True, help="Unique synthetic id such as MANUAL001.")
    respondent_add_parser.add_argument("--timestamp", default="")
    respondent_add_parser.add_argument("--respondent-name", required=True)
    respondent_add_parser.add_argument("--attending-grand-bethel", default="yes")
    respondent_add_parser.add_argument("--family-attendance", required=True)
    respondent_add_parser.add_argument("--contact-phone", default="")
    respondent_add_parser.add_argument("--emergency-contact-name", default="")
    respondent_add_parser.add_argument("--emergency-contact-phone", default="")
    respondent_add_parser.add_argument("--family-room-preference", default="")
    respondent_add_parser.add_argument("--girl-adult-only-room-preference", default="")
    respondent_add_parser.add_argument("--bed-share-acknowledged", default="")
    respondent_add_parser.add_argument("--allergies-raw", default="")
    respondent_add_parser.add_argument("--lunch-raw", default="")
    respondent_add_parser.add_argument("--excursions-raw", default="")
    respondent_add_parser.add_argument("--variety-show-interest", default="")
    respondent_add_parser.add_argument("--variety-show-names", default="")
    respondent_add_parser.add_argument("--variety-show-participant-categories", default="")
    respondent_add_parser.add_argument("--choir-interest", default="")
    respondent_add_parser.add_argument("--choir-names", default="")
    respondent_add_parser.add_argument("--performing-arts-interest", default="")
    respondent_add_parser.add_argument("--performing-arts-categories", default="")
    respondent_add_parser.add_argument("--performing-arts-participants", default="")
    respondent_add_parser.add_argument("--performing-arts-participant-categories", default="")
    respondent_add_parser.add_argument("--arts-and-crafts-interest", default="")
    respondent_add_parser.add_argument("--arts-and-crafts-categories", default="")
    respondent_add_parser.add_argument("--arts-and-crafts-participant-categories", default="")
    respondent_add_parser.add_argument("--librarians-report-interest", default="")
    respondent_add_parser.add_argument("--librarians-report-names", default="")
    respondent_add_parser.add_argument("--essay-interest", default="")
    respondent_add_parser.add_argument("--essay-names", default="")
    respondent_add_parser.add_argument("--ritual-interest", default="")
    respondent_add_parser.add_argument("--ritual-participant-categories", default="")
    respondent_add_parser.add_argument("--sew-and-show-interest", default="")
    respondent_add_parser.add_argument("--sew-and-show-names", default="")

    respondent_remove_parser = respondent_subparsers.add_parser("remove", help="Remove one synthetic respondent row by response id.")
    respondent_remove_parser.set_defaults(route="respondent.remove")
    respondent_remove_parser.add_argument("--response-id", required=True)

    respondent_show_parser = respondent_subparsers.add_parser("show-patches", help="Print the current respondent patch file.")
    respondent_show_parser.set_defaults(route="respondent.show_patches")

    respondent_reset_parser = respondent_subparsers.add_parser("reset-patches", help="Reset respondent patches back to an empty template.")
    respondent_reset_parser.set_defaults(route="respondent.reset_patches")

    override_parser = subparsers.add_parser("override", help="Manage Bethel-specific schedule overrides.")
    override_subparsers = override_parser.add_subparsers(dest="override_command")

    override_show_parser = override_subparsers.add_parser("show", help="Print the current Bethel overrides file.")
    override_show_parser.set_defaults(route="override.show")
    override_reset_parser = override_subparsers.add_parser("reset", help="Reset Bethel overrides back to an empty template.")
    override_reset_parser.set_defaults(route="override.reset")

    override_block_parser = override_subparsers.add_parser("add-block", help="Add a Bethel-specific local schedule block.")
    override_block_parser.set_defaults(route="override.add_block")
    override_block_parser.add_argument("--day-label", required=True, help="Day label, for example 'Thursday'.")
    override_block_parser.add_argument("--event-date", required=True, help="ISO date, for example 2026-06-18.")
    override_block_parser.add_argument("--time-raw", required=True, help="Display time, for example '5:00pm' or '7:00pm-8:00pm'.")
    override_block_parser.add_argument("--event-title", required=True, help="Local event title.")
    override_block_parser.add_argument("--dress-code", default="", help="Optional dress code.")
    override_block_parser.add_argument("--event-type", default="bethel_local", help="Optional event type label.")

    override_excursion_parser = override_subparsers.add_parser(
        "set-excursion",
        help="Map an excursion option to a Bethel-specific scheduled day.",
    )
    override_excursion_parser.set_defaults(route="override.set_excursion")
    override_excursion_parser.add_argument("--excursion-name", required=True)
    override_excursion_parser.add_argument("--day-label", required=True)
    override_excursion_parser.add_argument("--event-date", required=True)
    override_excursion_parser.add_argument("--notes", default="")

    override_block_assignment_parser = override_subparsers.add_parser(
        "set-block-assignment",
        help="Assign a full session block to an operational duty override such as guard duty.",
    )
    override_block_assignment_parser.set_defaults(route="override.set_block_assignment")
    override_block_assignment_parser.add_argument("--block-id", required=True)
    override_block_assignment_parser.add_argument("--assignment", required=True, choices=["guard_duty"])
    override_block_assignment_parser.add_argument(
        "--person",
        action="append",
        default=[],
        help="Repeat for each assigned person to show on the program and personal-duty view.",
    )

    competition_group_parser = subparsers.add_parser("competition", help="Manage competition entries and scheduling.")
    competition_subparsers = competition_group_parser.add_subparsers(dest="competition_command")

    competition_add_parser = competition_subparsers.add_parser(
        "add",
        help="Add a competition entry without editing the raw form export.",
    )
    competition_add_parser.set_defaults(route="competition.add")
    competition_add_parser.add_argument("--response-id", required=True)
    competition_add_parser.add_argument("--participant-name", required=True)
    competition_add_parser.add_argument("--competition-type", required=True)
    competition_add_parser.add_argument("--category-raw", default="")
    competition_add_parser.add_argument("--is-group-competition", choices=["true", "false"], default="")

    competition_remove_parser = competition_subparsers.add_parser(
        "remove",
        help="Remove a participant from a competition entry on reruns.",
    )
    competition_remove_parser.set_defaults(route="competition.remove")
    competition_remove_parser.add_argument("--participant-name", required=True)
    competition_remove_parser.add_argument("--competition-type", required=True)
    competition_remove_parser.add_argument("--category-raw", default="")
    competition_remove_parser.add_argument("--response-id", default="")

    competition_list_parser = competition_subparsers.add_parser(
        "list",
        help="List competition entries from the latest outputs.",
    )
    competition_list_parser.set_defaults(route="competition.list")
    competition_list_parser.add_argument("--response-id", default="")
    competition_list_parser.add_argument("--participant-name", default="")
    competition_list_parser.add_argument("--competition-type", default="")
    competition_list_parser.add_argument("--is-group-competition", choices=["true", "false"], default="")

    competition_set_group_parser = competition_subparsers.add_parser(
        "set-group-flag",
        help="Explicitly mark one competition row as group or individual.",
    )
    competition_set_group_parser.set_defaults(route="competition.set_group_flag")
    competition_set_group_parser.add_argument("--response-id", required=True)
    competition_set_group_parser.add_argument("--participant-name", required=True)
    competition_set_group_parser.add_argument("--competition-type", required=True)
    competition_set_group_parser.add_argument("--category-raw", default="")
    competition_set_group_parser.add_argument("--is-group-competition", required=True, choices=["true", "false"])

    competition_show_parser = competition_subparsers.add_parser("show-patches", help="Print the current competition patch file.")
    competition_show_parser.set_defaults(route="competition.show_patches")
    competition_import_forms_parser = competition_subparsers.add_parser(
        "import-forms",
        help="OCR finalized competition entry forms and convert them into competition patches.",
    )
    competition_import_forms_parser.set_defaults(route="competition.import_forms")
    competition_import_forms_parser.add_argument("--forms-dir", type=Path, required=True)
    competition_import_forms_parser.add_argument(
        "--review-path",
        type=Path,
        default=OUTPUT_DIR / "competition_form_import_review.csv",
        help="Where to write the import review CSV.",
    )
    competition_import_forms_parser.add_argument(
        "--input",
        type=Path,
        help="Optional raw registration CSV override. Defaults to the CSV in data/raw/.",
    )
    competition_import_forms_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write matched imports into config/competition_patches.yaml.",
    )
    competition_reset_parser = competition_subparsers.add_parser("reset-patches", help="Reset competition patches back to an empty template.")
    competition_reset_parser.set_defaults(route="competition.reset_patches")

    competition_show_timing_parser = competition_subparsers.add_parser(
        "show-timing",
        help="Print the current competition-to-program timing mappings.",
    )
    competition_show_timing_parser.set_defaults(route="competition.show_timing")

    competition_add_advance_parser = competition_subparsers.add_parser(
        "add-advance-submission",
        help="Mark a competition type as submitted in advance rather than live-scheduled.",
    )
    competition_add_advance_parser.set_defaults(route="competition.add_advance_submission")
    competition_add_advance_parser.add_argument("--competition-type", required=True)

    competition_remove_advance_parser = competition_subparsers.add_parser(
        "remove-advance-submission",
        help="Remove a competition type from the advance-submission list.",
    )
    competition_remove_advance_parser.set_defaults(route="competition.remove_advance_submission")
    competition_remove_advance_parser.add_argument("--competition-type", required=True)

    competition_set_timing_parser = competition_subparsers.add_parser(
        "set-timing",
        help="Set which parsed program block title(s) a competition should map to.",
    )
    competition_set_timing_parser.set_defaults(route="competition.set_timing")
    competition_set_timing_parser.add_argument("--competition-type", required=True)
    competition_set_timing_parser.add_argument(
        "--event-title",
        action="append",
        required=True,
        help="Repeat this flag for each exact program block title to map.",
    )

    attendee_parser = subparsers.add_parser("attendee", help="Manage attendee rows without editing the raw form export.")
    attendee_subparsers = attendee_parser.add_subparsers(dest="attendee_command")

    attendee_add_parser = attendee_subparsers.add_parser("add", help="Add one attendee to a response on reruns.")
    attendee_add_parser.set_defaults(route="attendee.add")
    attendee_add_parser.add_argument("--response-id", required=True)
    attendee_add_parser.add_argument("--attendee-name", required=True)
    attendee_add_parser.add_argument("--attendee-type", required=True, choices=["adult", "daughter"])
    attendee_add_parser.add_argument("--attendee-age-raw", default="")

    attendee_remove_parser = attendee_subparsers.add_parser("remove", help="Remove one attendee from a response on reruns.")
    attendee_remove_parser.set_defaults(route="attendee.remove")
    attendee_remove_parser.add_argument("--response-id", required=True)
    attendee_remove_parser.add_argument("--attendee-name", required=True)

    attendee_show_parser = attendee_subparsers.add_parser("show-patches", help="Print the current attendee patch file.")
    attendee_show_parser.set_defaults(route="attendee.show_patches")

    attendee_reset_parser = attendee_subparsers.add_parser("reset-patches", help="Reset attendee patches back to an empty template.")
    attendee_reset_parser.set_defaults(route="attendee.reset_patches")

    assignment_parser = subparsers.add_parser("assignment", help="Manage operational assignments.")
    assignment_subparsers = assignment_parser.add_subparsers(dest="assignment_command")

    assignment_list_parser = assignment_subparsers.add_parser("list", help="List assignments from the latest outputs.")
    assignment_list_parser.set_defaults(route="assignment.list")
    assignment_list_parser.add_argument("--day", default="")
    assignment_list_parser.add_argument("--status", default="")
    assignment_list_parser.add_argument("--owner", default="")

    assignment_add_parser = assignment_subparsers.add_parser("add", help="Add a manual assignment.")
    assignment_add_parser.set_defaults(route="assignment.add")
    assignment_add_parser.add_argument("--title", required=True)
    assignment_add_parser.add_argument("--day", required=True)
    assignment_add_parser.add_argument("--time-window", default="")
    assignment_add_parser.add_argument("--owner", required=True)
    assignment_add_parser.add_argument("--backup-owner", default="")
    assignment_add_parser.add_argument("--category", default="operations")
    assignment_add_parser.add_argument("--trigger-event", default="")
    assignment_add_parser.add_argument("--status", default="pending")
    assignment_add_parser.add_argument("--urgency", default="later")
    assignment_add_parser.add_argument("--dependencies", default="")
    assignment_add_parser.add_argument("--notes", default="")

    assignment_remove_parser = assignment_subparsers.add_parser("remove", help="Remove one assignment by id.")
    assignment_remove_parser.set_defaults(route="assignment.remove")
    assignment_remove_parser.add_argument("--assignment-id", required=True)

    assignment_assign_parser = assignment_subparsers.add_parser("assign", help="Update owner or status on one assignment.")
    assignment_assign_parser.set_defaults(route="assignment.assign")
    assignment_assign_parser.add_argument("--assignment-id", required=True)
    assignment_assign_parser.add_argument("--owner", default="")
    assignment_assign_parser.add_argument("--backup-owner", default="")
    assignment_assign_parser.add_argument("--status", default="")
    assignment_assign_parser.add_argument("--urgency", default="")
    assignment_assign_parser.add_argument("--notes", default="")

    assignment_clear_owner_parser = assignment_subparsers.add_parser(
        "clear-owner",
        help="Remove one person from all assignment owner fields where they currently appear.",
    )
    assignment_clear_owner_parser.set_defaults(route="assignment.clear_owner")
    assignment_clear_owner_parser.add_argument("--owner", required=True)
    assignment_clear_owner_parser.add_argument(
        "--include-backup-owner",
        action="store_true",
        help="Also clear matching backup owner fields.",
    )

    assignment_transfer_owner_parser = assignment_subparsers.add_parser(
        "transfer-owner",
        help="Move all assignment owner fields from one person to another.",
    )
    assignment_transfer_owner_parser.set_defaults(route="assignment.transfer_owner")
    assignment_transfer_owner_parser.add_argument("--from", dest="from_owner", required=True)
    assignment_transfer_owner_parser.add_argument("--to", dest="to_owner", required=True)
    assignment_transfer_owner_parser.add_argument(
        "--include-backup-owner",
        action="store_true",
        help="Also move matching backup owner fields.",
    )

    assignment_clear_all_owners_parser = assignment_subparsers.add_parser(
        "clear-all-owners",
        help="Clear all assignment owners across all assignments.",
    )
    assignment_clear_all_owners_parser.set_defaults(route="assignment.clear_all_owners")
    assignment_clear_all_owners_parser.add_argument(
        "--include-backup-owner",
        action="store_true",
        help="Also clear all backup owner fields.",
    )

    assignment_show_parser = assignment_subparsers.add_parser("show-patches", help="Print the current assignment patch file.")
    assignment_show_parser.set_defaults(route="assignment.show_patches")
    assignment_reset_parser = assignment_subparsers.add_parser("reset-patches", help="Reset assignment patches back to an empty template.")
    assignment_reset_parser.set_defaults(route="assignment.reset_patches")

    excursion_group_parser = subparsers.add_parser("excursion", help="Manage excursion interest decisions without editing the raw form export.")
    excursion_subparsers = excursion_group_parser.add_subparsers(dest="excursion_command")

    excursion_list_parser = excursion_subparsers.add_parser("list", help="List session-wide excursion options from the latest outputs.")
    excursion_list_parser.set_defaults(route="excursion.list")
    excursion_list_parser.add_argument("--excursion-name", default="")

    excursion_accept_parser = excursion_subparsers.add_parser("accept", help="Mark one excursion as accepted for the whole session.")
    excursion_accept_parser.set_defaults(route="excursion.accept")
    excursion_accept_parser.add_argument("--excursion-name", required=True)

    excursion_deny_parser = excursion_subparsers.add_parser("deny", help="Mark one excursion as denied for the whole session.")
    excursion_deny_parser.set_defaults(route="excursion.deny")
    excursion_deny_parser.add_argument("--excursion-name", required=True)

    excursion_show_parser = excursion_subparsers.add_parser("show-patches", help="Print the current excursion patch file.")
    excursion_show_parser.set_defaults(route="excursion.show_patches")

    excursion_reset_parser = excursion_subparsers.add_parser("reset-patches", help="Reset excursion patches back to an empty template.")
    excursion_reset_parser.set_defaults(route="excursion.reset_patches")


    competition_override_parser = competition_subparsers.add_parser(
        "set-override",
        help="Map a competition type to a Bethel-specific scheduled block.",
    )
    competition_override_parser.set_defaults(route="competition.set_override")
    competition_override_parser.add_argument("--competition-type", required=True)
    competition_override_parser.add_argument("--day-label", required=True)
    competition_override_parser.add_argument("--event-date", required=True)
    competition_override_parser.add_argument("--time-raw", required=True)
    competition_override_parser.add_argument("--event-title", required=True)
    competition_override_parser.add_argument("--notes", default="")

    competition_time_override_parser = competition_subparsers.add_parser(
        "set-time-override",
        help="Set an explicit time slot for a competition or performing-arts subgroup.",
    )
    competition_time_override_parser.set_defaults(route="competition.set_time_override")
    competition_time_override_parser.add_argument("--competition-type", required=True)
    competition_time_override_parser.add_argument(
        "--participant-group",
        default="",
        help="Optional subgroup, for example individual, ensemble, or choir.",
    )
    competition_time_override_parser.add_argument(
        "--participant-name",
        default="",
        help="Optional specific participant name, usually first name as shown in outputs.",
    )
    competition_time_override_parser.add_argument(
        "--response-id",
        default="",
        help="Optional specific response id to disambiguate duplicate participant names.",
    )
    competition_time_override_parser.add_argument("--day-label", required=True)
    competition_time_override_parser.add_argument("--event-date", required=True)
    competition_time_override_parser.add_argument("--time-raw", required=True)
    competition_time_override_parser.add_argument("--event-title", required=True)
    competition_time_override_parser.add_argument("--notes", default="")

    competition_list_unscheduled_parser = competition_subparsers.add_parser(
        "list-unscheduled",
        help="List competition entries that do not currently map to a scheduled block.",
    )
    competition_list_unscheduled_parser.set_defaults(route="competition.list_unscheduled")
    competition_list_unscheduled_parser.add_argument("--competition-type", default="")
    competition_list_unscheduled_parser.add_argument("--participant-name", default="")

    competition_schedule_entry_parser = competition_subparsers.add_parser(
        "schedule-entry",
        help="Schedule one specific competition entry, including unscheduled entries.",
    )
    competition_schedule_entry_parser.set_defaults(route="competition.schedule_entry")
    competition_schedule_entry_parser.add_argument("--response-id", required=True)
    competition_schedule_entry_parser.add_argument("--participant-name", required=True)
    competition_schedule_entry_parser.add_argument("--competition-type", required=True)
    competition_schedule_entry_parser.add_argument(
        "--participant-group",
        default="",
        help="Optional subgroup, for example individual, ensemble, or choir.",
    )
    competition_schedule_entry_parser.add_argument("--day-label", required=True)
    competition_schedule_entry_parser.add_argument("--event-date", required=True)
    competition_schedule_entry_parser.add_argument("--time-raw", required=True)
    competition_schedule_entry_parser.add_argument("--event-title", required=True)
    competition_schedule_entry_parser.add_argument("--notes", default="")

    block_parser = subparsers.add_parser("add-local-block", help=argparse.SUPPRESS)
    block_parser.set_defaults(route="override.add_block")
    block_parser.add_argument("--day-label", required=True, help="Day label, for example 'Thursday'.")
    block_parser.add_argument("--event-date", required=True, help="ISO date, for example 2026-06-18.")
    block_parser.add_argument("--time-raw", required=True, help="Display time, for example '5:00pm' or '7:00pm-8:00pm'.")
    block_parser.add_argument("--event-title", required=True, help="Local event title.")
    block_parser.add_argument("--dress-code", default="", help="Optional dress code.")
    block_parser.add_argument("--event-type", default="bethel_local", help="Optional event type label.")

    competition_parser = subparsers.add_parser(
        "set-competition-override",
        help=argparse.SUPPRESS,
    )
    competition_parser.set_defaults(route="competition.set_override")
    competition_parser.add_argument("--competition-type", required=True)
    competition_parser.add_argument("--day-label", required=True)
    competition_parser.add_argument("--event-date", required=True)
    competition_parser.add_argument("--time-raw", required=True)
    competition_parser.add_argument("--event-title", required=True)
    competition_parser.add_argument("--notes", default="")

    competition_time_parser = subparsers.add_parser(
        "set-competition-time-override",
        help=argparse.SUPPRESS,
    )
    competition_time_parser.set_defaults(route="competition.set_time_override")
    competition_time_parser.add_argument("--competition-type", required=True)
    competition_time_parser.add_argument(
        "--participant-group",
        default="",
        help="Optional subgroup, for example individual, ensemble, or choir.",
    )
    competition_time_parser.add_argument(
        "--participant-name",
        default="",
        help="Optional specific participant name, usually first name as shown in outputs.",
    )
    competition_time_parser.add_argument("--response-id", default="")
    competition_time_parser.add_argument("--day-label", required=True)
    competition_time_parser.add_argument("--event-date", required=True)
    competition_time_parser.add_argument("--time-raw", required=True)
    competition_time_parser.add_argument("--event-title", required=True)
    competition_time_parser.add_argument("--notes", default="")

    excursion_parser = subparsers.add_parser(
        "set-excursion-override",
        help=argparse.SUPPRESS,
    )
    excursion_parser.set_defaults(route="override.set_excursion")
    excursion_parser.add_argument("--excursion-name", required=True)
    excursion_parser.add_argument("--day-label", required=True)
    excursion_parser.add_argument("--event-date", required=True)
    excursion_parser.add_argument("--notes", default="")

    subparsers.add_parser("show-overrides", help=argparse.SUPPRESS).set_defaults(route="override.show")
    subparsers.add_parser("reset-overrides", help=argparse.SUPPRESS).set_defaults(route="override.reset")
    subparsers.add_parser(
        "show-competition-timing",
        help=argparse.SUPPRESS,
    ).set_defaults(route="competition.show_timing")

    set_competition_timing_parser = subparsers.add_parser(
        "set-competition-timing",
        help=argparse.SUPPRESS,
    )
    set_competition_timing_parser.set_defaults(route="competition.set_timing")
    set_competition_timing_parser.add_argument("--competition-type", required=True)
    set_competition_timing_parser.add_argument(
        "--event-title",
        action="append",
        required=True,
        help="Repeat this flag for each exact program block title to map.",
    )

    subparsers.add_parser("show-program-patches", help=argparse.SUPPRESS).set_defaults(route="program.show_patches")
    subparsers.add_parser("reset-program-patches", help=argparse.SUPPRESS).set_defaults(route="program.reset_patches")
    subparsers.add_parser("show-competition-patches", help=argparse.SUPPRESS).set_defaults(route="competition.show_patches")
    subparsers.add_parser("reset-competition-patches", help=argparse.SUPPRESS).set_defaults(route="competition.reset_patches")
    subparsers.add_parser("show-excursion-patches", help=argparse.SUPPRESS).set_defaults(route="excursion.show_patches")
    subparsers.add_parser("reset-excursion-patches", help=argparse.SUPPRESS).set_defaults(route="excursion.reset_patches")

    remove_competition_parser = subparsers.add_parser(
        "remove-competition-entry",
        help=argparse.SUPPRESS,
    )
    remove_competition_parser.set_defaults(route="competition.remove")
    remove_competition_parser.add_argument("--participant-name", required=True)
    remove_competition_parser.add_argument("--competition-type", required=True)
    remove_competition_parser.add_argument("--category-raw", default="")
    remove_competition_parser.add_argument("--response-id", default="")

    add_competition_parser = subparsers.add_parser(
        "add-competition-entry",
        help=argparse.SUPPRESS,
    )
    add_competition_parser.set_defaults(route="competition.add")
    add_competition_parser.add_argument("--response-id", required=True)
    add_competition_parser.add_argument("--participant-name", required=True)
    add_competition_parser.add_argument("--competition-type", required=True)
    add_competition_parser.add_argument("--category-raw", default="")

    list_blocks_parser = subparsers.add_parser("list-program-blocks", help=argparse.SUPPRESS)
    list_blocks_parser.set_defaults(route="program.list")
    list_blocks_parser.add_argument("--day", default="", help="Optional day filter like Thursday or Friday.")

    update_block_parser = subparsers.add_parser("update-program-block", help=argparse.SUPPRESS)
    update_block_parser.set_defaults(route="program.update")
    update_block_parser.add_argument("--block-id", required=True)
    update_block_parser.add_argument("--day-label")
    update_block_parser.add_argument("--event-date")
    update_block_parser.add_argument("--time-raw")
    update_block_parser.add_argument("--event-title")
    update_block_parser.add_argument("--dress-code")
    update_block_parser.add_argument("--event-type")

    remove_block_parser = subparsers.add_parser("remove-program-block", help=argparse.SUPPRESS)
    remove_block_parser.set_defaults(route="program.remove")
    remove_block_parser.add_argument("--block-id", required=True)

    remove_by_name_parser = subparsers.add_parser(
        "remove-program-block-by-name",
        help=argparse.SUPPRESS,
    )
    remove_by_name_parser.set_defaults(route="program.remove_by_name")
    remove_by_name_parser.add_argument("--event-title", required=True)

    remove_many_by_name_parser = subparsers.add_parser(
        "remove-program-blocks-by-name",
        help=argparse.SUPPRESS,
    )
    remove_many_by_name_parser.set_defaults(route="program.remove_many_by_name")
    remove_many_by_name_parser.add_argument(
        "--event-title",
        action="append",
        required=True,
        help="Repeat this flag for each exact event title you want to remove.",
    )
    subparsers.add_parser("examples", help="Print common command examples.").set_defaults(route="examples")
    subparsers._choices_actions = [
        action for action in subparsers._choices_actions if action.help != argparse.SUPPRESS
    ]
    return parser


def run_pipeline(input_override: Path | None) -> None:

    field_map = load_field_map(CONFIG_DIR / "field_map.yaml")
    meal_map = load_yaml(CONFIG_DIR / "meal_codes.yaml")
    competition_config = load_yaml(CONFIG_DIR / "competition_types.yaml")
    schedule_map = load_yaml(SCHEDULE_MAP_PATH)
    bethel_overrides = load_overrides(BETHEL_OVERRIDES_PATH)
    attendee_patches = load_attendee_patches(ATTENDEE_PATCHES_PATH)
    excursion_patches = load_excursion_patches(EXCURSION_PATCHES_PATH)
    assignment_patches = load_assignment_patches(ASSIGNMENT_PATCHES_PATH)
    respondent_patches = load_respondent_patches(RESPONDENT_PATCHES_PATH)
    schedule_map["bethel_overrides"] = bethel_overrides
    program_patches = load_program_patches(PROGRAM_PATCHES_PATH)
    competition_patches = load_competition_patches(COMPETITION_PATCHES_PATH)

    input_csv = input_override if input_override else discover_input_csv(DATA_RAW_DIR)
    raw_df, _ = load_raw_csv(input_csv, field_map)
    responses_df = normalize_responses(raw_df)
    responses_df = apply_respondent_patches(responses_df, respondent_patches)
    response_rows = [response.to_dict() for _, response in responses_df.iterrows()]
    excursion_options = derive_excursion_options(response_rows)
    program_blocks = parse_program_blocks(DATA_RAW_DIR / "2026 GB Prelim Program.md")
    program_blocks = apply_program_patches(program_blocks, program_patches)
    program_blocks = merge_program_with_overrides(program_blocks, bethel_overrides)

    attendees_rows: List[dict] = []
    family_rows: List[dict] = []
    competition_rows: List[dict] = []
    excursion_rows: List[dict] = []
    meal_rows: List[dict] = []
    rooming_rows: List[dict] = []
    validation_flags: List[dict] = []

    for response_row in response_rows:
        parsed_attendees, attendee_flags = parse_family_attendance(response_row.get("family_attendance", ""))
        attendee_dicts = [attendee_row(response_row, attendee) for attendee in parsed_attendees]
        attendee_dicts = apply_attendee_patches(
            attendee_dicts,
            {
                "patches": [
                    patch
                    for patch in attendee_patches.get("patches", [])
                    if str(patch.get("response_id", "")).strip() == str(response_row["response_id"]).strip()
                ]
            },
        )
        attendees_rows.extend(attendee_dicts)

        competition_for_response, competition_flags = build_competition_rows(response_row, competition_config)
        competition_rows.extend(competition_for_response)

        meals_for_response, meal_flags = build_meal_rows(
            response_row["response_id"], attendee_dicts, response_row.get("lunch_raw", ""), meal_map
        )
        meal_rows.extend(meals_for_response)

        excursion_rows.extend(build_excursion_rows(response_row, excursion_options))
        rooming_rows.extend(build_rooming_rows(response_row, attendee_dicts))

        response_flags = validate_response(
            response_row,
            attendee_dicts,
            attendee_flags,
            competition_flags,
            meal_flags,
        )
        validation_flags.extend(response_flags)

        family_rows.append(
            {
                "response_id": response_row["response_id"],
                "timestamp": response_row.get("timestamp", ""),
                "contact_phone": response_row.get("contact_phone", ""),
                "emergency_contact_name": response_row.get("emergency_contact_name", ""),
                "emergency_contact_phone": response_row.get("emergency_contact_phone", ""),
                "raw_family_attendance_text": response_row.get("family_attendance", ""),
                "attendee_count_total": len(attendee_dicts),
                "attendee_count_daughters": sum(attendee["attendee_type"] == "daughter" for attendee in attendee_dicts),
                "attendee_count_adults": sum(attendee["attendee_type"] == "adult" for attendee in attendee_dicts),
                "family_room_preference": response_row.get("family_room_preference", ""),
                "girl_adult_only_room_preference": response_row.get("girl_adult_only_room_preference", ""),
                "bed_share_acknowledged": response_row.get("bed_share_acknowledged", ""),
                "allergies_raw": response_row.get("allergies_raw", ""),
                "excursions_raw": response_row.get("excursions_raw", ""),
                "lunch_raw": response_row.get("lunch_raw", ""),
                "validation_flags": "; ".join(flag["issue_type"] for flag in response_flags),
            }
        )

    competition_rows = apply_competition_patches(competition_rows, competition_patches, attendees_rows)
    excursion_rows = apply_excursion_patches(excursion_rows, excursion_patches)
    validation_flags.extend(flag_duplicate_attendee_names(attendees_rows))

    competition_event_roster_rows = map_competitions_to_blocks(competition_rows, program_blocks, schedule_map)
    excursion_day_roster_rows = map_excursions_to_days(excursion_rows, schedule_map)
    participant_conflict_rows = build_participant_conflicts(competition_event_roster_rows)
    daily_program_summary_rows = build_daily_program_summary(
        program_blocks,
        competition_event_roster_rows,
        excursion_day_roster_rows,
    )
    assignment_rows = apply_assignment_patches(
        build_assignment_rows(pd.DataFrame(program_blocks), datetime.now()),
        assignment_patches,
    )

    attendees_df = ensure_columns(
        pd.DataFrame(attendees_rows),
        [
            "response_id",
            "timestamp",
            "contact_phone",
            "emergency_contact_name",
            "emergency_contact_phone",
            "attendee_name",
            "attendee_age_raw",
            "attendee_age_normalized",
            "attendee_type",
            "family_room_preference",
            "girl_adult_only_room_preference",
            "bed_share_acknowledged",
            "allergies_raw",
            "attending_grand_bethel",
        ],
    )
    families_df = ensure_columns(
        pd.DataFrame(family_rows),
        [
            "response_id",
            "timestamp",
            "contact_phone",
            "emergency_contact_name",
            "emergency_contact_phone",
            "raw_family_attendance_text",
            "attendee_count_total",
            "attendee_count_daughters",
            "attendee_count_adults",
            "family_room_preference",
            "girl_adult_only_room_preference",
            "bed_share_acknowledged",
            "allergies_raw",
            "excursions_raw",
            "lunch_raw",
            "validation_flags",
        ],
    )
    competitions_df = ensure_columns(
        pd.DataFrame(competition_rows),
        ["response_id", "participant_name", "competition_type", "is_group_competition", "category_raw", "source_field", "notes"],
    )
    excursions_df = ensure_columns(
        pd.DataFrame(excursion_rows),
        ["response_id", "contact_phone", "excursion_name", "interested"],
    )
    meals_df = ensure_columns(
        pd.DataFrame(meal_rows),
        ["response_id", "attendee_name_if_known", "meal_code", "meal_name", "raw_lunch_text", "parse_confidence"],
    )
    rooming_df = ensure_columns(
        pd.DataFrame(rooming_rows),
        [
            "response_id",
            "attendee_name",
            "attendee_type",
            "family_room_preference",
            "girl_adult_only_room_preference",
            "bed_share_acknowledged",
            "allergies_raw",
            "rooming_notes",
        ],
    )
    flags_df = ensure_columns(
        pd.DataFrame(validation_flags),
        ["response_id", "severity", "issue_type", "field_name", "issue_detail"],
    )
    program_blocks_df = ensure_columns(
        pd.DataFrame(program_blocks),
        [
            "block_id",
            "day_label",
            "day_name",
            "event_date",
            "time_raw",
            "display_time_raw",
            "start_time_raw",
            "end_time_raw",
            "event_title",
            "dress_code",
            "event_type",
            "audience_tag",
            "risk_level",
            "schedule_source",
        ],
    )
    competition_event_rosters_df = ensure_columns(
        pd.DataFrame(competition_event_roster_rows),
        [
            "block_id",
            "day_label",
            "event_date",
            "time_raw",
            "event_title",
            "response_id",
            "participant_name",
            "competition_type",
            "is_group_competition",
            "category_raw",
            "schedule_status",
            "schedule_source",
            "notes",
        ],
    )
    assignments_df = ensure_columns(
        pd.DataFrame(assignment_rows),
        [
            "assignment_id",
            "program_block_id",
            "title",
            "category",
            "owner",
            "backup_owner",
            "day",
            "time_window",
            "trigger_event",
            "status",
            "dependencies",
            "notes",
            "urgency",
            "sort_key",
        ],
    )
    excursion_day_rosters_df = ensure_columns(
        pd.DataFrame(excursion_day_roster_rows),
        [
            "response_id",
            "contact_phone",
            "excursion_name",
            "scheduled_day_label",
            "scheduled_date",
            "schedule_status",
            "schedule_source",
            "notes",
        ],
    )
    participant_conflicts_df = ensure_columns(
        pd.DataFrame(participant_conflict_rows),
        ["response_id", "participant_name", "day_label", "event_date", "time_raw", "conflict_type", "event_titles", "competition_types", "notes"],
    )
    daily_program_summary_df = ensure_columns(
        pd.DataFrame(daily_program_summary_rows),
        [
            "day_label",
            "event_date",
            "program_event_count",
            "competition_block_count",
            "competition_participant_count",
            "excursion_family_count",
            "excursion_options",
            "schedule_sources",
            "operational_highlights",
        ],
    )

    summary = build_summary(
        responses_df,
        attendees_df,
        competitions_df,
        excursions_df,
        meals_df,
        flags_df,
        program_blocks_df,
        competition_event_rosters_df,
        participant_conflicts_df,
    )

    write_outputs(
        OUTPUT_DIR,
        {
            "attendees.csv": attendees_df,
            "families.csv": families_df,
            "competitions.csv": competitions_df,
            "excursions.csv": excursions_df,
            "meals.csv": meals_df,
            "rooming.csv": rooming_df,
            "validation_flags.csv": flags_df,
            "program_blocks.csv": program_blocks_df,
            "competition_event_rosters.csv": competition_event_rosters_df,
            "excursion_day_rosters.csv": excursion_day_rosters_df,
            "participant_conflicts.csv": participant_conflicts_df,
            "daily_program_summary.csv": daily_program_summary_df,
            "assignments.csv": assignments_df,
        },
        summary,
    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    route = getattr(args, "route", args.command)

    if not args.command:
        run_pipeline(None)
        return

    if route == "run":
        run_pipeline(args.input)
        return

    if route == "respondent.add":
        fields = {
            "timestamp": args.timestamp,
            "respondent_name": args.respondent_name,
            "attending_grand_bethel": args.attending_grand_bethel,
            "family_attendance": args.family_attendance,
            "contact_phone": args.contact_phone,
            "emergency_contact_name": args.emergency_contact_name,
            "emergency_contact_phone": args.emergency_contact_phone,
            "family_room_preference": args.family_room_preference,
            "girl_adult_only_room_preference": args.girl_adult_only_room_preference,
            "bed_share_acknowledged": args.bed_share_acknowledged,
            "allergies_raw": args.allergies_raw,
            "lunch_raw": args.lunch_raw,
            "excursions_raw": args.excursions_raw,
            "variety_show_interest": args.variety_show_interest,
            "variety_show_names": args.variety_show_names,
            "variety_show_participant_categories": args.variety_show_participant_categories,
            "choir_interest": args.choir_interest,
            "choir_names": args.choir_names,
            "performing_arts_interest": args.performing_arts_interest,
            "performing_arts_categories": args.performing_arts_categories,
            "performing_arts_participants": args.performing_arts_participants,
            "performing_arts_participant_categories": args.performing_arts_participant_categories,
            "arts_and_crafts_interest": args.arts_and_crafts_interest,
            "arts_and_crafts_categories": args.arts_and_crafts_categories,
            "arts_and_crafts_participant_categories": args.arts_and_crafts_participant_categories,
            "librarians_report_interest": args.librarians_report_interest,
            "librarians_report_names": args.librarians_report_names,
            "essay_interest": args.essay_interest,
            "essay_names": args.essay_names,
            "ritual_interest": args.ritual_interest,
            "ritual_participant_categories": args.ritual_participant_categories,
            "sew_and_show_interest": args.sew_and_show_interest,
            "sew_and_show_names": args.sew_and_show_names,
        }
        patches = add_respondent_patch(
            RESPONDENT_PATCHES_PATH,
            {
                "action": "add",
                "response_id": args.response_id,
                "fields": fields,
            },
        )
        print(f"Saved {RESPONDENT_PATCHES_PATH}")
        print(summarize_respondent_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "respondent.remove":
        patches = add_respondent_patch(
            RESPONDENT_PATCHES_PATH,
            {
                "action": "remove",
                "response_id": args.response_id,
            },
        )
        print(f"Saved {RESPONDENT_PATCHES_PATH}")
        print(summarize_respondent_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "respondent.show_patches":
        patches = load_respondent_patches(RESPONDENT_PATCHES_PATH)
        print(summarize_respondent_patches(patches))
        if RESPONDENT_PATCHES_PATH.exists():
            with RESPONDENT_PATCHES_PATH.open("r", encoding="utf-8") as handle:
                print(handle.read().rstrip())
        return

    if route == "respondent.reset_patches":
        patches = reset_respondent_patches(RESPONDENT_PATCHES_PATH)
        print(f"Saved {RESPONDENT_PATCHES_PATH}")
        print(summarize_respondent_patches(patches))
        return

    if route == "override.add_block":
        overrides = add_extra_block(
            BETHEL_OVERRIDES_PATH,
            day_label=args.day_label,
            event_date=args.event_date,
            time_raw=args.time_raw,
            event_title=args.event_title,
            dress_code=args.dress_code,
            event_type=args.event_type,
        )
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        return

    if route == "competition.set_override":
        overrides = set_competition_override(
            BETHEL_OVERRIDES_PATH,
            competition_type=args.competition_type,
            day_label=args.day_label,
            event_date=args.event_date,
            time_raw=args.time_raw,
            event_title=args.event_title,
            notes=args.notes,
        )
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        return

    if route == "competition.set_time_override":
        overrides = set_competition_time_override(
            BETHEL_OVERRIDES_PATH,
            competition_type=args.competition_type,
            participant_group=args.participant_group,
            participant_name=args.participant_name,
            response_id=args.response_id,
            day_label=args.day_label,
            event_date=args.event_date,
            time_raw=args.time_raw,
            event_title=args.event_title,
            notes=args.notes,
        )
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        return

    if route == "competition.list_unscheduled":
        df = load_output_csv("competition_event_rosters.csv")
        df = df[df["schedule_status"] == "unscheduled_in_program"].copy()
        if args.competition_type:
            df = df[df["competition_type"].str.lower() == args.competition_type.lower()]
        if args.participant_name:
            df = df[df["participant_name"].str.lower().str.contains(args.participant_name.lower(), regex=False)]
        print_table(
            df.sort_values(["competition_type", "participant_name", "response_id"]),
            ["response_id", "participant_name", "competition_type", "is_group_competition", "category_raw", "schedule_status", "notes"],
        )
        return

    if route == "competition.list":
        df = load_output_csv("competitions.csv")
        if args.response_id:
            df = df[df["response_id"].astype(str).str.lower() == str(args.response_id).lower()]
        if args.participant_name:
            df = df[df["participant_name"].astype(str).str.contains(str(args.participant_name), case=False, regex=False)]
        if args.competition_type:
            df = df[df["competition_type"].astype(str).str.lower() == str(args.competition_type).lower()]
        if args.is_group_competition:
            df = df[df["is_group_competition"].astype(str).str.lower() == str(args.is_group_competition).lower()]
        print_competition_list(df)
        return

    if route == "competition.schedule_entry":
        overrides = set_competition_time_override(
            BETHEL_OVERRIDES_PATH,
            competition_type=args.competition_type,
            participant_group=args.participant_group,
            participant_name=args.participant_name,
            response_id=args.response_id,
            day_label=args.day_label,
            event_date=args.event_date,
            time_raw=args.time_raw,
            event_title=args.event_title,
            notes=args.notes,
        )
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "override.set_excursion":
        overrides = set_excursion_override(
            BETHEL_OVERRIDES_PATH,
            excursion_name=args.excursion_name,
            day_label=args.day_label,
            event_date=args.event_date,
            notes=args.notes,
        )
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        return

    if route == "override.set_block_assignment":
        overrides = set_block_assignment(
            BETHEL_OVERRIDES_PATH,
            block_id=args.block_id,
            assignment=args.assignment,
            people=args.person,
        )
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "override.show":
        overrides = load_overrides(BETHEL_OVERRIDES_PATH)
        print(summarize_overrides(overrides))
        with BETHEL_OVERRIDES_PATH.open("r", encoding="utf-8") as handle:
            print(handle.read().rstrip())
        return

    if route == "override.reset":
        overrides = reset_overrides(BETHEL_OVERRIDES_PATH)
        print(f"Saved {BETHEL_OVERRIDES_PATH}")
        print(summarize_overrides(overrides))
        return

    if route == "competition.show_timing":
        schedule_map = load_schedule_map(SCHEDULE_MAP_PATH)
        print(summarize_competition_timing(schedule_map))
        with SCHEDULE_MAP_PATH.open("r", encoding="utf-8") as handle:
            print(handle.read().rstrip())
        return

    if route == "competition.add_advance_submission":
        schedule_map = add_advance_submission_competition(
            SCHEDULE_MAP_PATH,
            competition_type=args.competition_type,
        )
        print(f"Saved {SCHEDULE_MAP_PATH}")
        print(summarize_competition_timing(schedule_map))
        return

    if route == "competition.remove_advance_submission":
        schedule_map = remove_advance_submission_competition(
            SCHEDULE_MAP_PATH,
            competition_type=args.competition_type,
        )
        print(f"Saved {SCHEDULE_MAP_PATH}")
        print(summarize_competition_timing(schedule_map))
        return

    if route == "competition.set_timing":
        schedule_map = set_competition_timing_keywords(
            SCHEDULE_MAP_PATH,
            competition_type=args.competition_type,
            event_titles=args.event_title,
        )
        print(f"Saved {SCHEDULE_MAP_PATH}")
        print(summarize_competition_timing(schedule_map))
        return

    if route == "program.show_patches":
        patches = load_program_patches(PROGRAM_PATCHES_PATH)
        print(summarize_program_patches(patches))
        with PROGRAM_PATCHES_PATH.open("r", encoding="utf-8") as handle:
            print(handle.read().rstrip())
        return

    if route == "program.reset_patches":
        patches = reset_program_patches(PROGRAM_PATCHES_PATH)
        print(f"Saved {PROGRAM_PATCHES_PATH}")
        print(summarize_program_patches(patches))
        return

    if route == "competition.show_patches":
        patches = load_competition_patches(COMPETITION_PATCHES_PATH)
        print(summarize_competition_patches(patches))
        with COMPETITION_PATCHES_PATH.open("r", encoding="utf-8") as handle:
            print(handle.read().rstrip())
        return

    if route == "competition.import_forms":
        summary = import_competition_forms(
            forms_dir=args.forms_dir,
            competition_patches_path=COMPETITION_PATCHES_PATH,
            field_map_path=CONFIG_DIR / "field_map.yaml",
            review_path=args.review_path,
            input_csv=args.input,
            apply=args.apply,
        )
        print(f"entries={summary['total_entries']}")
        print(f"matched={summary['matched_entries']}")
        print(f"unmatched={summary['unmatched_entries']}")
        print(f"written_patches={summary['written_patches']}")
        print(f"review_csv={summary['review_path']}")
        for issue in summary["issues"]:
            print(f"- {issue}")
        return

    if route == "competition.reset_patches":
        patches = reset_competition_patches(COMPETITION_PATCHES_PATH)
        print(f"Saved {COMPETITION_PATCHES_PATH}")
        print(summarize_competition_patches(patches))
        return

    if route == "attendee.add":
        patches = add_attendee_patch(
            ATTENDEE_PATCHES_PATH,
            {
                "action": "add",
                "response_id": args.response_id,
                "attendee_name": args.attendee_name,
                "attendee_type": args.attendee_type,
                "attendee_age_raw": args.attendee_age_raw,
            },
        )
        print(f"Saved {ATTENDEE_PATCHES_PATH}")
        print(summarize_attendee_patches(patches))
        return

    if route == "excursion.list":
        excursions_df = load_output_csv("excursions.csv")
        if args.excursion_name:
            excursions_df = excursions_df[
                excursions_df["excursion_name"].astype(str).str.contains(str(args.excursion_name), case=False, regex=False)
            ]
        if excursions_df.empty:
            print("No rows.")
            return
        summary_rows = []
        grouped = excursions_df.fillna("").groupby("excursion_name", sort=True)
        for excursion_name, rows in grouped:
            interested = rows["interested"].astype(str).str.strip().str.lower()
            summary_rows.append(
                {
                    "excursion_name": excursion_name,
                    "accepted_count": int((interested == "true").sum()),
                    "denied_count": int((interested == "false").sum()),
                }
            )
        print_table(pd.DataFrame(summary_rows), ["excursion_name", "accepted_count", "denied_count"])
        return

    if route in {"excursion.accept", "excursion.deny"}:
        patches = add_excursion_patch(
            EXCURSION_PATCHES_PATH,
            {
                "excursion_name": args.excursion_name,
                "decision": "accept" if route == "excursion.accept" else "deny",
            },
        )
        print(f"Saved {EXCURSION_PATCHES_PATH}")
        print(summarize_excursion_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "excursion.show_patches":
        patches = load_excursion_patches(EXCURSION_PATCHES_PATH)
        print(summarize_excursion_patches(patches))
        with EXCURSION_PATCHES_PATH.open("r", encoding="utf-8") as handle:
            print(handle.read().rstrip())
        return

    if route == "excursion.reset_patches":
        patches = reset_excursion_patches(EXCURSION_PATCHES_PATH)
        print(f"Saved {EXCURSION_PATCHES_PATH}")
        print(summarize_excursion_patches(patches))
        return

    if route == "attendee.remove":
        patches = add_attendee_patch(
            ATTENDEE_PATCHES_PATH,
            {
                "action": "remove",
                "response_id": args.response_id,
                "attendee_name": args.attendee_name,
            },
        )
        print(f"Saved {ATTENDEE_PATCHES_PATH}")
        print(summarize_attendee_patches(patches))
        return

    if route == "attendee.show_patches":
        patches = load_attendee_patches(ATTENDEE_PATCHES_PATH)
        print(summarize_attendee_patches(patches))
        if ATTENDEE_PATCHES_PATH.exists():
            with ATTENDEE_PATCHES_PATH.open("r", encoding="utf-8") as handle:
                print(handle.read().rstrip())
        return

    if route == "attendee.reset_patches":
        patches = reset_attendee_patches(ATTENDEE_PATCHES_PATH)
        print(f"Saved {ATTENDEE_PATCHES_PATH}")
        print(summarize_attendee_patches(patches))
        return

    if route == "assignment.list":
        df = load_output_csv("assignments.csv")
        if args.day:
            df = df[df["day"].astype(str).str.lower() == str(args.day).lower()]
        if args.status:
            df = df[df["status"].astype(str).str.lower() == str(args.status).lower()]
        if args.owner:
            df = df[df["owner"].astype(str).str.contains(str(args.owner), case=False, regex=False)]
        print_table(
            df.sort_values(["day", "time_window", "title"]),
            ["assignment_id", "title", "day", "time_window", "owner", "status", "urgency"],
        )
        return

    if route == "assignment.add":
        patches = add_assignment_patch(
            ASSIGNMENT_PATCHES_PATH,
            {
                "action": "add",
                "title": args.title,
                "day": args.day,
                "time_window": args.time_window,
                "owner": args.owner,
                "backup_owner": args.backup_owner,
                "category": args.category,
                "trigger_event": args.trigger_event,
                "status": args.status,
                "urgency": args.urgency,
                "dependencies": args.dependencies,
                "notes": args.notes,
            },
        )
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "assignment.remove":
        patches = add_assignment_patch(
            ASSIGNMENT_PATCHES_PATH,
            {
                "action": "remove",
                "assignment_id": args.assignment_id,
            },
        )
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "assignment.assign":
        patch = {
            "action": "assign",
            "assignment_id": args.assignment_id,
        }
        if args.owner != "":
            patch["owner"] = args.owner
        if args.backup_owner != "":
            patch["backup_owner"] = args.backup_owner
        if args.status != "":
            patch["status"] = args.status
        if args.urgency != "":
            patch["urgency"] = args.urgency
        if args.notes != "":
            patch["notes"] = args.notes
        patches = add_assignment_patch(
            ASSIGNMENT_PATCHES_PATH,
            patch,
        )
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "assignment.clear_owner":
        patch = {
            "action": "bulk_assign",
            "match_owner": args.owner,
            "owner": "",
        }
        if args.include_backup_owner:
            patch["backup_owner"] = ""
        patches = add_assignment_patch(
            ASSIGNMENT_PATCHES_PATH,
            patch,
        )
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "assignment.transfer_owner":
        patch = {
            "action": "bulk_assign",
            "match_owner": args.from_owner,
            "owner": args.to_owner,
        }
        if args.include_backup_owner:
            patch["backup_owner"] = args.to_owner
        patches = add_assignment_patch(
            ASSIGNMENT_PATCHES_PATH,
            patch,
        )
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "assignment.clear_all_owners":
        patch = {
            "action": "clear_all_owners",
            "owner": "",
        }
        if args.include_backup_owner:
            patch["backup_owner"] = ""
        patches = add_assignment_patch(
            ASSIGNMENT_PATCHES_PATH,
            patch,
        )
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "assignment.show_patches":
        patches = load_assignment_patches(ASSIGNMENT_PATCHES_PATH)
        print(summarize_assignment_patches(patches))
        if ASSIGNMENT_PATCHES_PATH.exists():
            with ASSIGNMENT_PATCHES_PATH.open("r", encoding="utf-8") as handle:
                print(handle.read().rstrip())
        return

    if route == "assignment.reset_patches":
        patches = reset_assignment_patches(ASSIGNMENT_PATCHES_PATH)
        print(f"Saved {ASSIGNMENT_PATCHES_PATH}")
        print(summarize_assignment_patches(patches))
        return

    if route == "competition.remove":
        patches = add_competition_patch(
            COMPETITION_PATCHES_PATH,
            {
                "action": "remove",
                "participant_name": args.participant_name,
                "competition_type": args.competition_type,
                "category_raw": args.category_raw,
                "response_id": args.response_id,
            },
        )
        print(f"Saved {COMPETITION_PATCHES_PATH}")
        print(summarize_competition_patches(patches))
        return

    if route == "competition.add":
        patches = add_competition_patch(
            COMPETITION_PATCHES_PATH,
            {
                "action": "add",
                "participant_name": args.participant_name,
                "competition_type": args.competition_type,
                "category_raw": args.category_raw,
                "response_id": args.response_id,
                "is_group_competition": args.is_group_competition,
            },
        )
        print(f"Saved {COMPETITION_PATCHES_PATH}")
        print(summarize_competition_patches(patches))
        return

    if route == "competition.set_group_flag":
        patches = add_competition_patch(
            COMPETITION_PATCHES_PATH,
            {
                "action": "set_group_flag",
                "response_id": args.response_id,
                "participant_name": args.participant_name,
                "competition_type": args.competition_type,
                "category_raw": args.category_raw,
                "is_group_competition": args.is_group_competition,
            },
        )
        print(f"Saved {COMPETITION_PATCHES_PATH}")
        print(summarize_competition_patches(patches))
        print("Run `grand-bethel run` to regenerate outputs.")
        return

    if route == "program.list":
        blocks = apply_program_patches(
            parse_program_blocks(DATA_RAW_DIR / "2026 GB Prelim Program.md"),
            load_program_patches(PROGRAM_PATCHES_PATH),
        )
        for block in blocks:
            if args.day and block.get("day_name", "").lower() != args.day.lower():
                continue
            print(
                f"{block['block_id']} | {block.get('day_name', '')} | {block.get('time_raw', '')} | "
                f"{block.get('event_title', '')} | {block.get('dress_code', '')} | {block.get('schedule_source', '')}"
            )
        return

    if route == "program.update":
        fields = {}
        for field in ["day_label", "event_date", "time_raw", "event_title", "dress_code", "event_type", "audience_tag"]:
            value = getattr(args, field)
            if value is not None:
                fields[field] = value
        if args.density_tag is not None:
            fields["risk_level"] = normalize_density_tag(args.density_tag)
        patches = add_patch(PROGRAM_PATCHES_PATH, {"block_id": args.block_id, "action": "update", "fields": fields})
        print(f"Saved {PROGRAM_PATCHES_PATH}")
        print(summarize_program_patches(patches))
        return

    if route == "program.remove":
        patches = add_patch(PROGRAM_PATCHES_PATH, {"block_id": args.block_id, "action": "remove"})
        print(f"Saved {PROGRAM_PATCHES_PATH}")
        print(summarize_program_patches(patches))
        return

    if route == "program.remove_by_name":
        patches = add_patch(
            PROGRAM_PATCHES_PATH,
            {"match_event_title": args.event_title, "action": "remove"},
        )
        print(f"Saved {PROGRAM_PATCHES_PATH}")
        print(summarize_program_patches(patches))
        return

    if route == "program.remove_many_by_name":
        patches = load_program_patches(PROGRAM_PATCHES_PATH)
        for event_title in args.event_title:
            patches = add_patch(
                PROGRAM_PATCHES_PATH,
                {"match_event_title": event_title, "action": "remove"},
            )
        print(f"Saved {PROGRAM_PATCHES_PATH}")
        print(summarize_program_patches(patches))
        return

    if route == "examples":
        print(
            "\n".join(
                [
                    "Run the pipeline:",
                    "  grand-bethel run",
                    "",
                    "Show current program patches:",
                    "  grand-bethel program show-patches",
                    "",
                    "List Friday program blocks:",
                    "  grand-bethel program list --day Friday",
                    "",
                    "Update a program block:",
                    '  grand-bethel program update --block-id B039 --dress-code "Formal"',
                    "",
                    "Remove one program block by name:",
                    '  grand-bethel program remove-by-name --event-title "Beehive open for drop off"',
                    "",
                    "Remove several program blocks by name:",
                    '  grand-bethel program remove-many-by-name --event-title "Roll Call of Bethels" --event-title "Project Presentation"',
                    "",
                    "Remove a competition entry:",
                    '  grand-bethel competition remove --participant-name Lucia --competition-type choir',
                    "",
                    "Add a competition entry:",
                    '  grand-bethel competition add --response-id R0005 --participant-name Megan --competition-type choir --is-group-competition true',
                    "",
                    "Add a synthetic respondent without editing the raw CSV:",
                    '  grand-bethel respondent add --response-id MANUAL001 --respondent-name "Jane Doe" --family-attendance "Jane Doe - Adult Sophie Doe - 14" --contact-phone "555-123-4567"',
                    "",
                    "Mark one existing competition row as group or individual:",
                    '  grand-bethel competition set-group-flag --response-id R0003 --participant-name Lucia --competition-type performing_arts --category-raw "Instrumental (Any instrument, including piano)" --is-group-competition false',
                    "",
                    "Add an attendee to a response:",
                    '  grand-bethel attendee add --response-id R0005 --attendee-name "Grandma Lee" --attendee-type adult',
                    "",
                    "Remove an attendee from a response:",
                    '  grand-bethel attendee remove --response-id R0005 --attendee-name "Grandma Lee"',
                    "",
                    "List assignments:",
                    "  grand-bethel assignment list",
                    "",
                    "Add a manual assignment:",
                    '  grand-bethel assignment add --title "Prep guard post" --day Friday --time-window "6:30pm - 7:00pm" --owner "Operations Lead"',
                    "",
                    "Reassign one assignment:",
                    '  grand-bethel assignment assign --assignment-id assignment_b026_1234567890 --owner "Registrar" --status in_progress',
                    "",
                    "Remove one assignment:",
                    '  grand-bethel assignment remove --assignment-id assignment_b026_1234567890',
                    "",
                    "Accept one excursion for the whole session:",
                    '  grand-bethel excursion accept --excursion-name "Sequoia National Park (Thursday)"',
                    "",
                    "Deny one excursion for the whole session:",
                    '  grand-bethel excursion deny --excursion-name "Sequoia Springs water park (Thursday)"',
                    "",
                    "Remove one specific competition category entry:",
                    '  grand-bethel competition remove --participant-name Lucia --competition-type performing_arts --category-raw "Instrumental (Any instrument, including piano)"',
                    "",
                    "Add a Bethel-local block:",
                    '  grand-bethel override add-block --day-label Friday --event-date 2026-06-19 --time-raw 6:00pm --event-title "Bethel dinner" --dress-code Casual',
                    "",
                    "Set a competition override:",
                    '  grand-bethel competition set-override --competition-type choir --day-label Friday --event-date 2026-06-19 --time-raw 6:00pm --event-title "Bethel choir warmup"',
                    "",
                    "Set an explicit competition time override:",
                    '  grand-bethel competition set-time-override --competition-type choir --day-label Saturday --event-date 2026-06-20 --time-raw 10:15am --event-title "Choir Competition"',
                    "",
                    "Set an explicit performing arts individual slot:",
                    '  grand-bethel competition set-time-override --competition-type performing_arts --participant-group individual --day-label Saturday --event-date 2026-06-20 --time-raw 12:45pm --event-title "Performing Arts Individual Competition"',
                    "",
                    "Set a participant-specific individual slot:",
                    '  grand-bethel competition set-time-override --competition-type performing_arts --participant-group individual --participant-name Lucia --response-id R0003 --day-label Saturday --event-date 2026-06-20 --time-raw 10:45am --event-title "Performing Arts Individual Competition"',
                    "",
                    "List currently unscheduled competition entries:",
                    "  grand-bethel competition list-unscheduled",
                    "",
                    "Schedule one unscheduled entry:",
                    '  grand-bethel competition schedule-entry --response-id R0003 --participant-name Lucia --competition-type librarians_report --day-label Friday --event-date 2026-06-19 --time-raw 3:30pm --event-title "Librarian\'s Report"',
                    "",
                    "Show competition timing mappings:",
                    "  grand-bethel competition show-timing",
                    "",
                    "Preview finalized competition form imports:",
                    '  grand-bethel competition import-forms --forms-dir "/Users/you/Desktop/Grand Bethel Competition Entry Forms"',
                    "",
                    "Write matched finalized form imports into competition patches:",
                    '  grand-bethel competition import-forms --forms-dir "/Users/you/Desktop/Grand Bethel Competition Entry Forms" --apply',
                    "",
                    "Add another advance-submitted competition type:",
                    "  grand-bethel competition add-advance-submission --competition-type miss_congeniality",
                    "",
                    "Remove a competition type from the advance-submission list:",
                    "  grand-bethel competition remove-advance-submission --competition-type essay",
                    "",
                    "Map choir to one or more parsed program blocks:",
                    '  grand-bethel competition set-timing --competition-type choir --event-title "Performing Arts Competition"',
                ]
            )
        )
        return


if __name__ == "__main__":
    main()
