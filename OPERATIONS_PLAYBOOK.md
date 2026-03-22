# Operations Playbook

## Purpose

This playbook defines the safe operational workflow for maintaining the pipeline and static site without editing derived artifacts manually.

## 1. Operating Rules

- Never edit files in `outputs/` by hand.
- Make changes through source data, config, or YAML patch files.
- After any patch/config change, rerun the pipeline.
- Treat `response_id` as stable only relative to the current raw CSV row order.
- If the raw CSV changes row order, revalidate every response-specific patch.
- Assume raw exports and derived outputs may contain sensitive information.

## 2. Standard Run Procedure

### Full regeneration

Command:

```bash
python3.12 src/main.py run
```

Alternate:

```bash
python3.12 src/main.py run --input /path/to/export.csv
```

Expected effects:

- all CSV outputs are rewritten
- `summary.json` is rewritten
- `dashboard.html` is regenerated
- `outputs/site/*.html` is regenerated

## 3. Operational Change Surfaces

### A. Program corrections

Use when:

- a source block title is wrong
- a program time/date needs adjustment
- a source block should be removed

Commands:

```bash
python3.12 src/main.py program list --day Thursday
python3.12 src/main.py program update --block-id B012 --time-raw "3:30pm" --event-title "Updated Title"
python3.12 src/main.py program update --block-id B012 --audience-tag "Families"
python3.12 src/main.py program update --block-id B012 --density-tag high
python3.12 src/main.py program remove --block-id B012
python3.12 src/main.py program remove-by-name --event-title "Exact Title"
```

Storage:

- `config/program_patches.yaml`

### B. Add Bethel-local blocks

Use when:

- the state program does not contain a Bethel-specific obligation

Command:

```bash
python3.12 src/main.py override add-block --day-label Thursday --event-date 2026-06-18 --time-raw "5:00pm" --event-title "Bethel 337 Dinner" --dress-code "Casual" --event-type bethel_local
```

Storage:

- `config/bethel_overrides.yaml`

### C. Add or remove attendees

Use when:

- a person was omitted from or wrongly included in the raw CSV export

Commands:

```bash
python3.12 src/main.py attendee add --response-id R0003 --attendee-name "Jane Doe" --attendee-type daughter --attendee-age-raw "15"
python3.12 src/main.py attendee remove --response-id R0003 --attendee-name "Jane Doe"
```

Storage:

- `config/attendee_patches.yaml`

Operational note:

- attendee patches affect family counts, meals alignment, rooming rows, and downstream displays

### D. Add or remove competition entries

Use when:

- a contestant is missing
- a contestant was entered in error

Commands:

```bash
python3.12 src/main.py competition add --response-id R0003 --participant-name Lucia --competition-type librarians_report
python3.12 src/main.py competition remove --response-id R0003 --participant-name Lucia --competition-type librarians_report
```

Storage:

- `config/competition_patches.yaml`

### E. Configure competition timing behavior

Use when:

- a competition should map to a different program block
- a competition is advance-submitted and should not be treated as unscheduled

Commands:

```bash
python3.12 src/main.py competition show-timing
python3.12 src/main.py competition set-timing --competition-type ritual --event-title "Ritual Competition"
python3.12 src/main.py competition add-advance-submission --competition-type essay
python3.12 src/main.py competition remove-advance-submission --competition-type essay
```

Storage:

- `config/schedule_map.yaml`

### F. Force a specific competition schedule slot

Use when:

- one participant or subgroup must be assigned a specific block
- a previously unscheduled competition entry needs a manual slot

Commands:

```bash
python3.12 src/main.py competition set-time-override --competition-type performing_arts --participant-group ensemble --day-label Friday --event-date 2026-06-19 --time-raw "3:30pm" --event-title "Performing Arts Competition"
python3.12 src/main.py competition schedule-entry --response-id R0003 --participant-name Lucia --competition-type librarians_report --day-label Friday --event-date 2026-06-19 --time-raw "3:30pm" --event-title "Special Slot"
```

Storage:

- `config/bethel_overrides.yaml`

### G. Accept or deny excursions session-wide

Use when:

- an excursion option is approved or removed for the entire session

Commands:

```bash
python3.12 src/main.py excursion list
python3.12 src/main.py excursion accept --excursion-name "Sequoia National Park (Thursday)"
python3.12 src/main.py excursion deny --excursion-name "Sequoia Springs water park (Thursday)"
```

Storage:

- `config/excursion_patches.yaml`

## 4. Regeneration Checklist After Any Change

1. Apply the CLI change.
2. Run the pipeline.
3. Inspect these outputs:
   - `outputs/summary.json`
   - `outputs/program_blocks.csv`
   - `outputs/competition_event_rosters.csv`
   - `outputs/participant_conflicts.csv`
   - `outputs/site/index.html`
   - `outputs/site/operations.html`
4. Confirm that the intended entity moved into the correct schedule/status bucket.

## 5. Troubleshooting Guide

### Problem: run fails with missing columns

Likely cause:

- input CSV headers do not match `field_map.yaml`

Action:

1. inspect the new export headers
2. update `config/field_map.yaml`
3. rerun

### Problem: a participant appears unscheduled

Likely causes:

- competition type has no matching keyword in `schedule_map.yaml`
- competition is actually advance-submitted but not configured
- the participant needs a manual schedule override

Actions:

1. run `competition list-unscheduled`
2. run `competition show-timing`
3. choose one of:
   - `competition add-advance-submission`
   - `competition set-timing`
   - `competition schedule-entry`

### Problem: conflicts seem wrong

Likely causes:

- a competition mapped to multiple blocks
- manual timing overrides are too broad
- same participant appears in multiple competition entries

Actions:

1. inspect `outputs/competition_event_rosters.csv`
2. inspect `config/bethel_overrides.yaml`
3. tighten time overrides by `response_id` and participant name where possible

### Problem: family counts or meal rows are off

Likely causes:

- family attendance parsing ambiguity
- attendee patch mismatch
- lunch text parse mismatch

Actions:

1. inspect `validation_flags.csv` for the `response_id`
2. inspect `attendees.csv` and `meals.csv`
3. add/remove attendee patches if the raw export cannot be corrected

### Problem: a program row disappeared unexpectedly

Likely cause:

- a `remove` action exists in `program_patches.yaml`

Action:

1. run `program show-patches`
2. remove or reset the patch
3. rerun

## 6. Validation and Review Routine

After each regeneration, review at minimum:

- `validation_flags.csv`
- `competition_event_rosters.csv`
- `participant_conflicts.csv`
- `daily_program_summary.csv`

Priority interpretation:

- `error` in validation flags should be treated as blocking data quality issues
- `warning` should be reviewed before publishing the site externally
- `unscheduled_in_program` competition rows should be resolved or intentionally accepted
- empty emergency contact fields should be escalated to registration follow-up

## 7. Safe Editing Rules for Developers

- Edit source modules in `src/`; do not hand-edit generated HTML.
- Preserve the entrypoint `src/main.py`.
- Preserve `write_outputs(...)` as the single output orchestration path unless a deliberate architecture change is approved.
- If changing schema, update all of:
  - DataFrame construction in `main.py`
  - renderers that consume those fields
  - this documentation

## 8. Release Readiness Checklist

Before sharing outputs:

1. run the pipeline from a clean working tree or known state
2. verify there is exactly one intended raw CSV input or pass `--input`
3. review all YAML patch files for stale test data
4. confirm no obviously placeholder notes remain in outputs
5. verify site pages render:
   - home
   - operations
   - program
   - competitions
   - families

## 9. Recovery Procedure

If patch state becomes untrustworthy:

1. back up all YAML files in `config`
2. inspect with:
   - `program show-patches`
   - `competition show-patches`
   - `attendee show-patches`
   - `excursion show-patches`
   - `override show`
3. selectively reset the affected patch file
4. rerun the pipeline
5. reapply only validated changes
