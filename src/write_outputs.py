from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd

from build_dashboard import build_dashboard
from build_site import build_site


def write_csv(df: pd.DataFrame, output_dir: Path, name: str) -> None:
    df.to_csv(output_dir / name, index=False)


def write_outputs(output_dir: Path, dataframes: Dict[str, pd.DataFrame], summary: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in dataframes.items():
        write_csv(df, output_dir, name)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    build_dashboard(
        output_dir / "dashboard.html",
        summary,
        dataframes["families.csv"],
        dataframes["attendees.csv"],
        dataframes["validation_flags.csv"],
        dataframes["competitions.csv"],
        dataframes["meals.csv"],
        dataframes["excursions.csv"],
        dataframes.get("program_blocks.csv", pd.DataFrame()),
        dataframes.get("competition_event_rosters.csv", pd.DataFrame()),
        dataframes.get("excursion_day_rosters.csv", pd.DataFrame()),
        dataframes.get("participant_conflicts.csv", pd.DataFrame()),
        dataframes.get("daily_program_summary.csv", pd.DataFrame()),
    )
    build_site(
        output_dir / "site",
        summary,
        dataframes.get("assignments.csv", pd.DataFrame()),
        dataframes["families.csv"],
        dataframes["attendees.csv"],
        dataframes["validation_flags.csv"],
        dataframes["competitions.csv"],
        dataframes["meals.csv"],
        dataframes["excursions.csv"],
        dataframes.get("program_blocks.csv", pd.DataFrame()),
        dataframes.get("competition_event_rosters.csv", pd.DataFrame()),
        dataframes.get("excursion_day_rosters.csv", pd.DataFrame()),
        dataframes.get("participant_conflicts.csv", pd.DataFrame()),
        dataframes.get("daily_program_summary.csv", pd.DataFrame()),
    )
