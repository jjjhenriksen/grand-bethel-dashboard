# System Architecture

## Scope

This system ingests a single Grand Bethel registration CSV export plus static configuration, derives normalized operational datasets, and emits:

- CSV outputs in `outputs`
- a static multi-page site in `outputs/site`
- CLI-managed patch and override files in `config`

The runtime model is file-based and stateless between runs except for persisted YAML patch/override files.

## Top-Level Components

### 1. Entry point

File: `src/main.py`

Responsibilities:

- defines the CLI
- loads raw input and config
- runs the full transformation pipeline
- applies patch/override layers
- materializes pandas DataFrames with fixed column order
- computes summary metrics
- delegates output generation

Primary callable:

- `main()`
- `run_pipeline(input_override: Path | None)`

### 2. Raw input loading

Files:

- `src/load_raw.py`
- `src/normalize_responses.py`

Responsibilities:

- locate the input CSV
- normalize raw column headers using `config/field_map.yaml`
- normalize phone fields, boolean-style fields, and preferences
- assign stable `response_id` values of the form `R0001`

### 3. Domain parsers

Files:

- `src/parse_family_attendance.py`
- `src/parse_competitions.py`
- `src/parse_excursions.py`
- `src/parse_meals.py`
- `src/parse_program.py`
- `src/derive_rooming.py`

Responsibilities:

- parse family attendance text into attendee records
- parse competition interest/detail fields into competition entry rows
- normalize excursion selections into boolean interest rows
- parse lunch selections into meal rows
- parse the state program markdown into program blocks
- derive rooming rows from attendee and response data

### 4. Validation

File:

- `src/validate.py`

Responsibilities:

- emit response-level validation flags
- emit duplicate-attendee-name warnings across responses

### 5. Schedule enrichment

File:

- `src/enrich_schedule.py`

Responsibilities:

- merge local Bethel blocks into parsed program blocks
- map competition entries to scheduled program blocks or non-live states
- map excursion interests to scheduled days
- derive participant conflict rows
- derive daily program summary rows

### 6. Mutable patch and override layers

Files:

- `src/program_patches.py`
- `src/bethel_overrides.py`
- `src/competition_patches.py`
- `src/attendee_patches.py`
- `src/excursion_patches.py`
- `src/schedule_config.py`

Responsibilities:

- persist operator edits as YAML
- modify parsed program data without editing source markdown
- add/remove attendees and competition entries without editing the raw CSV
- map competitions and excursions to local schedule decisions
- configure advance-submission contest types and keyword-based competition mapping

### 7. Output renderers

Files:

- `src/write_outputs.py`
- `src/build_dashboard.py`
- `src/build_site.py`

Responsibilities:

- write canonical CSV outputs
- generate `summary.json`
- generate the multi-page static site

## Runtime Data Flow

### Pipeline sequence

1. Load configuration:
   - `field_map.yaml`
   - `meal_codes.yaml`
   - `competition_types.yaml`
   - `schedule_map.yaml`
   - YAML patch/override files
2. Discover or accept an input CSV path.
3. Load and rename CSV columns to canonical field names.
4. Normalize response-level fields.
5. Parse the state program markdown into `program_blocks`.
6. Apply `program_patches`.
7. Merge Bethel local schedule overrides into `program_blocks`.
8. For each response:
   - parse attendees
   - apply attendee patches scoped to that response
   - parse competition entries
   - parse meal selections
   - parse excursion interest
   - derive rooming rows
   - validate the response
   - assemble one family row
9. Apply competition patches across all competition rows.
10. Apply excursion patches across all excursion rows.
11. Add duplicate-attendee warnings.
12. Map competitions to program blocks.
13. Map excursions to days.
14. Build participant conflicts.
15. Build daily program summary.
16. Normalize DataFrame schemas with `ensure_columns(...)`.
17. Compute summary metrics.
18. Write CSV outputs, JSON summary, dashboard HTML, and site HTML.

## Authoritative Inputs

### Raw source inputs

- one CSV file in `data/raw`
- state program markdown:
  `data/raw/2026 GB Prelim Program.md`

### Config and operator-controlled inputs

- `config/field_map.yaml`
- `config/meal_codes.yaml`
- `config/competition_types.yaml`
- `config/schedule_map.yaml`
- `config/program_patches.yaml`
- `config/bethel_overrides.yaml`
- `config/competition_patches.yaml`
- `config/attendee_patches.yaml`
- `config/excursion_patches.yaml`

## Output Surfaces

### Canonical machine-readable outputs

Written by `write_outputs(...)`:

- `attendees.csv`
- `families.csv`
- `competitions.csv`
- `excursions.csv`
- `meals.csv`
- `rooming.csv`
- `validation_flags.csv`
- `program_blocks.csv`
- `competition_event_rosters.csv`
- `excursion_day_rosters.csv`
- `participant_conflicts.csv`
- `daily_program_summary.csv`
- `summary.json`

### Presentation outputs

- `outputs/site/index.html`
- `outputs/site/operations.html`
- `outputs/site/program.html`
- `outputs/site/competitions.html`
- `outputs/site/families.html`

## Shared State and Site Rendering

File:

- `src/build_site.py`

The multi-page site uses an in-memory canonical `STATE` object:

```python
STATE = {
  "now": datetime,
  "program_blocks": list[dict],
  "families": list[dict],
  "competitions": {
    "entries": list[dict],
    "rosters": list[dict],
  },
  "conflicts": list[dict],
  "assignments": list[dict],
}
```

Current shared rendering primitives:

- `_build_state(...)`
- `getCurrentContext(now, program_blocks)`
- `renderNowNextCritical(context, include_owner=False)`

These functions drive the shared summary strip used on `index.html`, `operations.html`, and `program.html`.

## Override and Patch Precedence

### Program blocks

Order of application:

1. parse state program markdown
2. apply `program_patches.yaml`
3. append `bethel_overrides.yaml: extra_blocks`

Implication:

- program patches can update/remove source blocks
- Bethel override blocks are additive and appended after patched source blocks

### Competition scheduling

Resolution precedence in `map_competitions_to_blocks(...)`:

1. specific manual competition time override in `bethel_overrides.yaml`
2. competition-type-level override in `bethel_overrides.yaml`
3. advance-submission classification from `schedule_map.yaml`
4. keyword-based match against program blocks
5. fallback status `unscheduled_in_program`

### Excursion scheduling

Resolution precedence in `map_excursions_to_days(...)`:

1. excursion override in `bethel_overrides.yaml`
2. day inferred from parenthetical text in the excursion label using `schedule_map.yaml: excursion_day_aliases`
3. fallback status `unscheduled`

### Parsed response entities

- attendee patches apply immediately after attendee parsing, before family counts and downstream derivations
- competition patches apply after competition parsing and before schedule mapping
- excursion patches apply after excursion parsing and before excursion day mapping

## CLI Architecture

All CLI commands are implemented in `src/main.py`.

Primary command groups:

- `run`
- `program`
- `override`
- `competition`
- `attendee`
- `excursion`
- `examples`

CLI commands mutate YAML patch/override files only. They do not directly edit generated CSV outputs. After a mutation, the system requires a pipeline rerun to regenerate downstream outputs.

## Non-Goals and Constraints

Current system characteristics:

- no database
- no backend API
- no incremental recomputation cache
- no client-side persistence in the site
- static HTML only
- pandas DataFrames are the canonical processing containers during generation

Operational consequence:

- every material change is realized by rerunning the full pipeline
- generated outputs must be treated as derived artifacts, not edited by hand
