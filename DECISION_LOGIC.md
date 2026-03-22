# Decision Logic

## Purpose

This document defines the explicit rules used to transform raw registration input into derived operational outputs and site/dashboard presentation state.

## 1. Input Normalization Rules

### Header normalization

Module:

- `src/load_raw.py`

Rules:

- trim surrounding whitespace
- normalize en dash and em dash to `-`
- normalize curly quotes to straight quotes
- remove double quotes
- collapse repeated whitespace

Failure mode:

- if any field listed in `field_map.yaml` is absent after normalization, the run fails with `ValueError`

### Boolean normalization

Module:

- `src/normalize_responses.py`

Rules for `normalize_bool(...)`:

- `yes`, `y`, `true`, `1`, `attending`, or strings starting with `yes` -> `yes`
- `no`, `n`, `false`, `0`, `not attending`, or strings starting with `no` -> `no`
- empty or unrecognized -> `unknown`

Rules for `normalize_preference(...)`:

- same yes/no normalization as above
- `doesn't matter`, `doesnt matter`, `does not matter`, `either` -> `does_not_matter`
- otherwise `unknown`

### Phone normalization

Rules:

- split on `;`, `,`, `/`, or wide whitespace gaps
- extract digits
- 10-digit values become `###-###-####`
- 11-digit values beginning with `1` become `###-###-####`
- multiple valid numbers are deduplicated and joined with `; `
- if no valid pattern is found, return cleaned original text

### Response ID assignment

Rule:

- response ID is assigned strictly by row order in the input CSV
- format: `R{index+1:04d}`

Consequence:

- inserting, reordering, or removing rows in the source CSV changes downstream `response_id` assignments

## 2. Family Attendance Parsing Rules

Module:

- `src/parse_family_attendance.py`

### Primary parse strategy

The parser searches for repeated `name + age/adult marker` pairs.

Accepted age tokens:

- `adult`
- integer ages
- integer ages with parenthetical note

Normalization:

- daughters are first-name-only in the parsed output
- adults retain cleaned full names
- numeric ages `< 18` -> `daughter`
- numeric ages `>= 18` -> `adult`

### Fallback strategy

If no structured pairs are found:

- split on newline, comma, semicolon, or ampersand
- if names are present, treat each as an adult attendee
- emit warning `attendee_parsing_ambiguity` when more than one name is defaulted

### Error rules

- blank input -> `blank_family_attendance_field`
- no parse and no name-only fallback -> `attendee_parsing_failed`
- residual unparsed text after extracting matches -> `attendee_parsing_ambiguity`
- token contains `adult` and a numeric age -> parse row plus ambiguity warning

## 3. Competition Parsing Rules

Module:

- `src/parse_competitions.py`

### Source configuration

Competition parsing is driven by `config/competition_types.yaml`.

Each competition config may specify:

- `interest_field`
- `names_field`
- `detail_field`
- `categories_field`

### Record creation rules

For each configured competition type:

1. Read `interest_field`.
2. Parse participant pairs from `detail_field` if present.
3. If no detail pairs exist, parse names from `names_field`.
4. If category detail is absent, fall back to `categories_field`.

### Validation rules

- interest `yes` with no parsed participants -> emit a placeholder row with empty `participant_name` and note
- interest not `yes` but participant detail exists -> emit warning `competition_yes_no_mismatch`

### Name normalization

- participant names are reduced to first name only

## 4. Meal Parsing Rules

Module:

- `src/parse_meals.py`

### Parse order

1. parse named assignments of the form `Name - Meal`
2. strip named assignments from the text
3. parse remaining meal codes
4. parse remaining free-text meal labels

### Matching logic

- single-letter code must exist in `meal_map`
- free-text meal labels are matched against alias table
- attendee labels are matched exactly first, then by unique initial

### Confidence assignment

- named assignments -> `high`
- unnamed codes matching the remaining attendee count exactly -> `medium`
- otherwise -> `low`

### Validation rules

- number of parsed meals != attendee count -> warning `lunch_count_cannot_be_aligned_with_attendee_count`
- raw lunch text present but nothing parsed -> warning `lunch_parse_failed`

## 5. Program Parsing Rules

Module:

- `src/parse_program.py`

### Source format assumptions

- input is markdown table-style text
- day header may appear in its own row or in an event-title cell
- time may appear in the time column or be embedded at the start of the event title

### Time parsing

Accepted patterns:

- `H:MMam`
- `H:MMpm`
- `H:MMam-H:MMpm`
- `TBA`

### Block creation

For each parseable event row:

- assign sequential block ID `B###`
- carry forward current day and current time when omitted in subsequent grouped rows
- derive `day_name` from the weekday at the start of `day_label`
- classify event type using `classify_event_type(...)`

### Event type classification

- title contains `competition`, `awards`, `fashion show`, or `variety show` -> `competition_related`
- title contains `practice` -> `practice`
- title contains `luncheon` or `festivities` -> `meal_or_social`
- title contains `registration`, `pick up`, `turn in`, or `drop off` -> `logistics`
- otherwise -> `program`

## 6. Patch and Override Decision Rules

### Program patches

Module:

- `src/program_patches.py`

Matching:

- by exact `block_id`
- or normalized event title match
- includes a short-title equivalence table for selected common labels

Actions:

- `remove` -> drop the first matching block
- `update` -> set `fields`, recompute time/day-derived fields, mark `schedule_source = program_patch`

### Bethel extra blocks

Module:

- `src/bethel_overrides.py`

Rule:

- each extra block is converted into a synthetic program block using `build_override_block(...)`
- synthetic block IDs use `L###`

### Competition patching

Module:

- `src/competition_patches.py`

Matching rules for removal:

- all supplied selectors must match
- match is tolerant to case, punctuation, `&` vs `and`, and subset token overlap

Addition rules:

- row is added only if an equivalent row does not already exist
- participant name is canonicalized against attendees in the same response when possible

### Attendee patching

Module:

- `src/attendee_patches.py`

Rules:

- remove matches on `response_id + normalized attendee_name`
- add requires `response_id` and `attendee_name`
- added rows inherit template fields from the first attendee in the same response when available
- age/type are normalized from patch values

### Excursion patching

Module:

- `src/excursion_patches.py`

Rules:

- decisions are session-wide, not per response
- normalized excursion-name equality controls the patch target
- `accept` forces `interested = true` on all matching rows
- `deny` forces `interested = false` on all matching rows

## 7. Competition Scheduling Rules

Module:

- `src/enrich_schedule.py`

### Participant grouping for manual overrides

For competition time overrides:

- `choir` -> group `choir`
- `performing_arts` with `ensemble` or `sign language` in category -> group `ensemble`
- other `performing_arts` -> group `individual`
- all others -> empty group

### Override match scoring

When multiple manual override rules could apply:

- `response_id` match contributes highest specificity
- `participant_name` contributes medium specificity
- `participant_group` contributes lowest specificity
- the highest specificity score wins

### Schedule resolution precedence

1. matching manual competition time override
2. competition-type-level override
3. advance-submission competition type
4. keyword-based block mapping
5. unresolved fallback

### Result states

- `scheduled`
- `submitted_in_advance`
- `unscheduled_in_program`

### Advance-submission rule

Competitions listed in `schedule_map.yaml: advance_submission_competitions` are emitted with:

- no day
- no date
- no time
- no event title
- `schedule_status = submitted_in_advance`
- `schedule_source = advance_submission`

## 8. Excursion Scheduling Rules

Module:

- `src/enrich_schedule.py`

Resolution:

1. if a Bethel excursion override exists, use it
2. else inspect parenthetical text in the excursion name
3. map that text through `excursion_day_aliases`
4. if mapped day exists, emit `scheduled`
5. otherwise emit `unscheduled`

Day/date mapping:

- fixed date map exists for Wednesday through Sunday 2026 session dates

## 9. Validation Rules

Module:

- `src/validate.py`

### Response-level validation

The system emits flags when:

- attendee, competition, or meal parser emitted flags
- attendance is `no` but attendees were parsed
- attendance is `yes` but no attendees were parsed
- emergency contact name is missing
- emergency contact phone is missing
- contact phone is missing
- both family-room and girl/adult-only-room preferences are `yes`

### Cross-response validation

The system emits `duplicate_attendee_name_across_rows` when the same normalized attendee name appears in multiple responses.

## 10. Conflict Derivation Rules

Source:

- `build_participant_conflicts(...)` from `src/enrich_schedule.py`
- site-level conflict enrichment in `src/build_site.py`

Current site-level rules:

- default `status` -> `Unresolved`
- default `resolution_type` -> `needs_decision`
- `conflict_pair` is the first two competition labels joined by `vs`
- `escalation_logic = escalate` when the conflict event time is within 48 hours of generation time
- otherwise `escalation_logic = watch`

## 11. Site Summary Logic

Module:

- `src/build_site.py`

### Context derivation

Function:

- `getCurrentContext(now, program_blocks)`

Derived fields:

- `current_block`
- `next_block`
- `deadlines`
- `state`
- `program_start`
- `program_end`

State rules:

- no windows -> `unknown`
- `now < earliest_start` -> `before`
- `now > latest_end` -> `after`
- any window containing `now` -> `active`
- otherwise -> `between`

Deadline rules:

- use the next 48 hours from `now` for `before`, `active`, and `between`
- use the final program end time as baseline when `after`
- cap list at 3 blocks

### Presentation messaging rules

- `before` -> planning-state language
- `after` -> concluded language
- `between` or no active block during session -> no-active-block language
- if no current block but not after event, show nearest-upcoming schedule note

## 12. Site-Derived Metadata Rules

Module:

- `src/build_site.py`

### Assignment urgency

Current thresholds:

- missing event datetime -> `normal`
- event already started or passed -> `due_now`
- within 24h -> `high`
- within 72h -> `medium`
- later -> `low`

### Assignment status

Current rules:

- event in the future -> `planned`
- event at or before generation time -> `ready`

### Program load density

Count per `day_label`:

- `>= 12` blocks -> `high`
- `>= 6` blocks -> `medium`
- otherwise -> `low`

### Family flags

- missing emergency contact name -> `missing_emergency_contact`
- allergy text present and not `no`/`none` -> `allergies_listed`
- attendee count total `>= 5` -> `large_family`
