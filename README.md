# Grand Bethel Registration Pipeline

Deterministic Python pipeline for turning a raw Google Forms CSV export into planning outputs for the 2026 Grand Bethel Registration Survey.

## Run

1. Create a virtual environment and install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Put the raw Google Forms CSV export into `data/raw/`.

3. Run the pipeline:

```bash
python3.12 src/main.py run
```

Or point directly at a file:

```bash
python3.12 src/main.py run --input /absolute/path/to/export.csv
```

If you omit the subcommand, the CLI still defaults to running the pipeline.

The generated website in `outputs/site/` now includes browser-side live updates. If you serve that folder over HTTP, each page will poll `site-data.json` and refresh itself when a new pipeline run regenerates the site.

One simple way to preview it locally:

```bash
cd outputs/site
python3.12 -m http.server 8000
```

Then open [http://localhost:8000/index.html](http://localhost:8000/index.html).

## GitHub Pages

This repository includes a GitHub Actions workflow at `.github/workflows/deploy-pages.yml` that can build the pipeline and publish `outputs/site/` to GitHub Pages.

To use it:

1. Push this repository to GitHub on the `main` branch.
2. In the GitHub repo settings, open `Settings -> Pages`.
3. Set the build source to `GitHub Actions`.
4. Push changes to `main` or run the workflow manually from the Actions tab.

The workflow installs dependencies, runs `python src/main.py run`, and deploys the generated site from `outputs/site/`.

## Bethel Override CLI

Use the CLI to layer Bethel-specific schedule decisions on top of the statewide preliminary program.

Show the current overrides:

```bash
python3.12 src/main.py override show
```

Print common command examples:

```bash
python3.12 src/main.py examples
```

Reset the overrides file:

```bash
python3.12 src/main.py override reset
```

Add a local event block:

```bash
python3.12 src/main.py override add-block \
  --day-label Thursday \
  --event-date 2026-06-18 \
  --time-raw 5:00pm \
  --event-title "Bethel dinner" \
  --dress-code Casual
```

Override a competition schedule:

```bash
python3.12 src/main.py competition set-override \
  --competition-type choir \
  --day-label Friday \
  --event-date 2026-06-19 \
  --time-raw 6:00pm \
  --event-title "Bethel choir warmup"
```

Show the current competition timing mappings:

```bash
python3.12 src/main.py competition show-timing
```

Update which parsed program block title(s) a competition should map to:

```bash
python3.12 src/main.py competition set-timing \
  --competition-type choir \
  --event-title "Performing Arts Competition"
```

Repeat `--event-title` if one competition should map to more than one parsed program block.

Set an explicit competition time override that does not need to match a program block:

```bash
python3.12 src/main.py competition set-time-override \
  --competition-type choir \
  --day-label Saturday \
  --event-date 2026-06-20 \
  --time-raw 10:15am \
  --event-title "Choir Competition"
```

You can also target a specific performing-arts subgroup or a single participant:

```bash
python3.12 src/main.py competition set-time-override \
  --competition-type performing_arts \
  --participant-group individual \
  --participant-name Lucia \
  --day-label Saturday \
  --event-date 2026-06-20 \
  --time-raw 10:45am \
  --event-title "Performing Arts Individual Competition"
```

If an entry is still showing up under "Unscheduled or Needs Mapping", list those rows directly:

```bash
python3.12 src/main.py competition list-unscheduled
```

And schedule one specific unscheduled entry by response id, participant, and competition type:

```bash
python3.12 src/main.py competition schedule-entry \
  --response-id R0003 \
  --participant-name Lucia \
  --competition-type librarians_report \
  --day-label Friday \
  --event-date 2026-06-19 \
  --time-raw 3:30pm \
  --event-title "Librarian's Report"
```

`competition schedule-entry` writes a participant-specific time override, so it works well for unscheduled one-off entries without changing the mapping for every entry of that competition type.

Some competition types are not live scheduled events at all. They are submitted in advance and should not appear as unscheduled. The schedule map currently treats `librarians_report` and `essay` that way, so those entries will show up as `submitted_in_advance` instead of `unscheduled_in_program`.

Add another competition type to that advance-submission list:

```bash
python3.12 src/main.py competition add-advance-submission \
  --competition-type miss_congeniality
```

Remove one from the list:

```bash
python3.12 src/main.py competition remove-advance-submission \
  --competition-type essay
```

Override an excursion day:

```bash
python3.12 src/main.py override set-excursion \
  --excursion-name "Thrifting in downtown Visalia (Any day of the session)" \
  --day-label Friday \
  --event-date 2026-06-19
```

Overrides are stored in `config/bethel_overrides.yaml` and are applied automatically on the next pipeline run.
Run the override commands one at a time because they all update the same YAML file.

## Program Patch CLI

If the raw statewide program parses into blocks that are close but not exactly how you want them shown on the dashboard, patch the parsed blocks without editing the raw markdown.

List blocks:

```bash
python3.12 src/main.py program list --day Friday
```

Update a block:

```bash
python3.12 src/main.py program update \
  --block-id B010 \
  --time-raw 8:00am \
  --event-title "Beehive open for drop off"
```

Remove a block:

```bash
python3.12 src/main.py program remove --block-id B019
```

Or remove by exact event title:

```bash
python3.12 src/main.py program remove-by-name \
  --event-title "Please do not leave the arena until the Grand Bethel Officers have retired"
```

Or remove several at once:

```bash
python3.12 src/main.py program remove-many-by-name \
  --event-title "Roll Call of Bethels" \
  --event-title "Project Presentation" \
  --event-title "Introduction of JDs to Bee"
```

Show or reset patches:

```bash
python3.12 src/main.py program show-patches
python3.12 src/main.py program reset-patches
```

Program patches are stored in `config/program_patches.yaml` and are applied automatically on the next pipeline run.

## Competition Patch CLI

If a competition entry should be removed from the operational outputs without changing the raw form export, use a competition patch.

Competition rows now also include `is_group_competition`, so group entries like `choir`, `variety_show`, and ensemble-style performing arts rows are flagged in outputs and rendered planning views.

Remove one participant from a competition:

```bash
python3.12 src/main.py competition remove \
  --participant-name Lucia \
  --competition-type choir
```

Add one participant to a competition:

```bash
python3.12 src/main.py competition add \
  --response-id R0003 \
  --participant-name Lucia \
  --competition-type choir \
  --is-group-competition true
```

Remove one specific competition entry by category:

```bash
python3.12 src/main.py competition remove \
  --participant-name Lucia \
  --competition-type performing_arts \
  --category-raw "Instrumental (Any instrument, including piano)"
```

If the same participant name appears in multiple responses, you can narrow it with `--response-id`.

Override one existing row to be explicitly group or individual:

```bash
python3.12 src/main.py competition set-group-flag \
  --response-id R0003 \
  --participant-name Lucia \
  --competition-type performing_arts \
  --category-raw "Instrumental (Any instrument, including piano)" \
  --is-group-competition false
```

Show or reset competition patches:

```bash
python3.12 src/main.py competition show-patches
python3.12 src/main.py competition reset-patches
```

Competition patches are stored in `config/competition_patches.yaml` and are applied automatically on each pipeline run.

## Assignment CLI

Assignments are written to `outputs/assignments.csv` and can be patched directly without editing generated HTML or changing the underlying program block.

List assignments:

```bash
python3.12 src/main.py assignment list
```

Add one manual assignment:

```bash
python3.12 src/main.py assignment add \
  --title "Prep guard post" \
  --day Friday \
  --time-window "6:30pm - 7:00pm" \
  --owner "Operations Lead"
```

Reassign one assignment or update its status:

```bash
python3.12 src/main.py assignment assign \
  --assignment-id assignment_b026_1234567890 \
  --owner "Registrar" \
  --status in_progress
```

Remove one assignment:

```bash
python3.12 src/main.py assignment remove \
  --assignment-id assignment_b026_1234567890
```

Show or reset assignment patches:

```bash
python3.12 src/main.py assignment show-patches
python3.12 src/main.py assignment reset-patches
```

Assignment patches are stored in `config/assignment_patches.yaml` and are applied automatically on each pipeline run.

## Attendee Patch CLI

If an attendee should be added or removed without changing the raw form export, use an attendee patch.

Add one attendee to a response:

```bash
python3.12 src/main.py attendee add \
  --response-id R0005 \
  --attendee-name "Grandma Lee" \
  --attendee-type adult
```

Add one daughter with a specific age:

```bash
python3.12 src/main.py attendee add \
  --response-id R0005 \
  --attendee-name "Sophie" \
  --attendee-type daughter \
  --attendee-age-raw 14
```

Remove one attendee:

```bash
python3.12 src/main.py attendee remove \
  --response-id R0005 \
  --attendee-name "Grandma Lee"
```

Show or reset attendee patches:

```bash
python3.12 src/main.py attendee show-patches
python3.12 src/main.py attendee reset-patches
```

Attendee patches are stored in `config/attendee_patches.yaml` and are applied automatically on each pipeline run.

## Excursion Patch CLI

If an excursion option should be accepted or denied for the whole session without changing the raw form export, use an excursion patch.

Accept one excursion for the whole session:

```bash
python3.12 src/main.py excursion accept \
  --excursion-name "Sequoia National Park (Thursday)"
```

Deny one excursion for the whole session:

```bash
python3.12 src/main.py excursion deny \
  --excursion-name "Sequoia Springs water park (Thursday)"
```

List current session-wide excursion options from the latest outputs:

```bash
python3.12 src/main.py excursion list
```

Show or reset excursion patches:

```bash
python3.12 src/main.py excursion show-patches
python3.12 src/main.py excursion reset-patches
```

Excursion patches are stored in `config/excursion_patches.yaml` and are applied automatically on each pipeline run.

Legacy flat commands still work, but the grouped `program ...`, `competition ...`, `attendee ...`, `excursion ...`, and `override ...` commands are the preferred interface.

## Outputs

The pipeline writes all derived files to `outputs/`:

- `attendees.csv`: one row per parsed attendee from the family attendance text.
- `families.csv`: one row per registration response.
- `competitions.csv`: one row per participant-entry pair where it can be inferred.
- `excursions.csv`: one row per family-per-excursion interest.
- `meals.csv`: one row per parsed lunch choice.
- `rooming.csv`: one row per attendee for rooming review.
- `validation_flags.csv`: one row per detected issue or ambiguity.
- `program_blocks.csv`: one row per parsed event block from the preliminary session program.
- `competition_event_rosters.csv`: competition entries mapped to scheduled program blocks where possible.
- `excursion_day_rosters.csv`: interested families grouped by scheduled excursion day.
- `participant_conflicts.csv`: possible same-time participant overlaps based on scheduled competition blocks.
- `daily_program_summary.csv`: per-day planning summary combining the preliminary program and registration interest.
- `summary.json`: machine-readable totals for downstream use.
- `dashboard.html`: static operational dashboard.
- `site/index.html`: website home page that keeps the current dashboard feel while splitting operations, program, competitions, and families into separate pages.
- `site/operations.html`: action-oriented operations page with immediate actions, assignments, conflicts, and validation queue.
- `site/program.html`: session program page.
- `site/competitions.html`: competition planning page, including submitted-in-advance entries.
- `site/families.html`: family page.

## Assumptions

- The raw CSV is the source of truth.
- The `Name` field from the form is not trusted for attendee rosters.
- Attendees are parsed from the free-text family attendance field.
- Boolean normalization accepts common variants such as `yes`, `y`, `true`, `no`, `n`, `false`.
- When parsing is ambiguous, the pipeline preserves raw text and emits validation flags instead of claiming certainty.
- Response IDs are generated deterministically from row order in the raw file as `R0001`, `R0002`, and so on.

## Known Limitations

- Free-text family attendance parsing is heuristic. Very irregular formatting may still require manual review via `validation_flags.csv`.
- Lunch codes can only be aligned to specific attendee names when the number of parsed meal codes matches the number of parsed attendees.
- Competition detail fields vary in structure. The parser preserves raw categories and source fields, but some rows may still need review.
- Some competition types in the registration form may not appear in the preliminary program. Those entries are preserved and marked as unscheduled in the schedule-aware outputs.
- Excursions with labels such as `Any day of the session` are grouped into a planning bucket rather than assigned to a single dated program block.
- Duplicate attendee names across different families are flagged because they may be real duplicates or simply common names.

## Maintenance Notes

- Column mapping lives in `config/field_map.yaml`.
- Meal code definitions live in `config/meal_codes.yaml`.
- Competition field definitions live in `config/competition_types.yaml`.
- Program-to-schedule mapping rules live in `config/schedule_map.yaml`.
- Competition timing mappings and advance-submission competition types inside `config/schedule_map.yaml` can be managed through the CLI.
- Bethel-specific local overrides live in `config/bethel_overrides.yaml` and can be managed through the CLI.
- Parsed program cleanup patches live in `config/program_patches.yaml` and can also be managed through the CLI.
- Competition entry cleanup patches live in `config/competition_patches.yaml` and can also be managed through the CLI.
- Excursion decision patches live in `config/excursion_patches.yaml` and can also be managed through the CLI.
- No derived files should be edited manually. Re-run the pipeline from the raw CSV instead.
