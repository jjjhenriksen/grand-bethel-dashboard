# Data Model

## Modeling Principles

- Source-of-truth input is the normalized response DataFrame plus parsed state program blocks.
- All CSV outputs are derived artifacts.
- YAML patch and override files are operator-authored mutation layers.
- Site-only `STATE` fields are derived presentation metadata and are not written back to CSV.

## Core Runtime Objects

### Normalized response record

Produced by:

- `src/normalize_responses.py`

Key fields:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Stable generated ID `R0001`, `R0002`, ... |
| `timestamp` | string | Raw form timestamp if present |
| `contact_phone` | string | Normalized phone string; multiple numbers delimited by `; ` |
| `emergency_contact_name` | string | Cleaned free text |
| `emergency_contact_phone` | string | Normalized phone string |
| `attending_grand_bethel` | enum | `yes`, `no`, `unknown` |
| `family_room_preference` | enum | `yes`, `no`, `does_not_matter`, `unknown` |
| `girl_adult_only_room_preference` | enum | `yes`, `no`, `does_not_matter`, `unknown` |
| `bed_share_acknowledged` | enum | `yes`, `no`, `unknown` |
| `allergies_raw` | string | Cleaned free text |
| `excursions_raw` | string | Cleaned free text |
| `*_interest` | enum | Competition interest fields normalized to `yes`, `no`, `unknown` |

## Generated CSV Schemas

### `attendees.csv`

Grain:

- one row per attendee after parsing and attendee patch application

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `timestamp` | string | Response timestamp |
| `contact_phone` | string | Response contact phone |
| `emergency_contact_name` | string | Response emergency contact name |
| `emergency_contact_phone` | string | Response emergency contact phone |
| `attendee_name` | string | Parsed attendee name |
| `attendee_age_raw` | string | Raw age token from family attendance field |
| `attendee_age_normalized` | string | Numeric age or `adult` |
| `attendee_type` | enum | `adult`, `daughter`, `unknown` |
| `family_room_preference` | enum | Response-level room preference |
| `girl_adult_only_room_preference` | enum | Response-level room preference |
| `bed_share_acknowledged` | enum | Response-level value |
| `allergies_raw` | string | Response-level allergy text |
| `attending_grand_bethel` | enum | Response-level attendance value |

### `families.csv`

Grain:

- one row per response

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Stable response ID |
| `timestamp` | string | Response timestamp |
| `contact_phone` | string | Contact phone |
| `emergency_contact_name` | string | Emergency contact name |
| `emergency_contact_phone` | string | Emergency contact phone |
| `raw_family_attendance_text` | string | Original attendance text |
| `attendee_count_total` | integer | Parsed attendee count after attendee patches |
| `attendee_count_daughters` | integer | Parsed daughter count |
| `attendee_count_adults` | integer | Parsed adult count |
| `family_room_preference` | enum | `yes`, `no`, `does_not_matter`, `unknown` |
| `girl_adult_only_room_preference` | enum | `yes`, `no`, `does_not_matter`, `unknown` |
| `bed_share_acknowledged` | enum | `yes`, `no`, `unknown` |
| `allergies_raw` | string | Allergy text |
| `excursions_raw` | string | Raw excursion text |
| `lunch_raw` | string | Raw lunch text |
| `validation_flags` | string | Semicolon-delimited issue type list from response-level validation |

### `competitions.csv`

Grain:

- one row per parsed competition participant entry after competition patch application

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `participant_name` | string | Participant display name |
| `competition_type` | string | Canonical competition key |
| `category_raw` | string | Category or subtype text |
| `source_field` | string | Originating normalized field name |
| `notes` | string | Parser or patch notes |

### `excursions.csv`

Grain:

- one row per response x excursion option after excursion patch application

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `contact_phone` | string | Response contact phone |
| `excursion_name` | string | Canonical option label |
| `interested` | enum | `true`, `false` |

### `meals.csv`

Grain:

- one row per parsed meal choice

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `attendee_name_if_known` | string | Matched attendee name or label |
| `meal_code` | string | One of configured meal codes |
| `meal_name` | string | Human-readable meal label from `meal_codes.yaml` |
| `raw_lunch_text` | string | Original lunch free text |
| `parse_confidence` | enum | `high`, `medium`, `low` |

### `rooming.csv`

Grain:

- one row per attendee with rooming notes

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `attendee_name` | string | Attendee name |
| `attendee_type` | enum | `adult`, `daughter`, `unknown` |
| `family_room_preference` | enum | Response-level preference |
| `girl_adult_only_room_preference` | enum | Response-level preference |
| `bed_share_acknowledged` | enum | Response-level value |
| `allergies_raw` | string | Allergy text |
| `rooming_notes` | string | Derived notes for rooming review |

### `validation_flags.csv`

Grain:

- one row per validation issue

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Affected response |
| `severity` | enum | `error`, `warning` |
| `issue_type` | string | Canonical machine-readable issue key |
| `field_name` | string | Canonical field name implicated |
| `issue_detail` | string | Human-readable explanation |

### `program_blocks.csv`

Grain:

- one row per program block after program patches and Bethel block overrides

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `block_id` | string | Stable block ID like `B001`; local override blocks use `L###` |
| `day_label` | string | Raw day label from program source or override |
| `day_name` | string | Canonical weekday label |
| `event_date` | string | ISO date |
| `time_raw` | string | Canonical display time string for block grouping |
| `display_time_raw` | string | Explicit display time from parser |
| `start_time_raw` | string | Parsed start time or `TBA` |
| `end_time_raw` | string | Parsed end time if present |
| `event_title` | string | Event title |
| `dress_code` | string | Raw dress code text |
| `event_type` | enum | `competition_related`, `practice`, `meal_or_social`, `logistics`, `program`, `bethel_local`, or patch-specified value |
| `schedule_source` | enum | `state_program`, `program_patch`, `bethel_override` |

### `competition_event_rosters.csv`

Grain:

- one row per competition participant x mapped scheduled block, or one row per non-live entry state

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `block_id` | string | Linked program block ID if scheduled from parsed program |
| `day_label` | string | Scheduled day label |
| `event_date` | string | Scheduled date |
| `time_raw` | string | Scheduled time |
| `event_title` | string | Scheduled block title |
| `response_id` | string | Parent response ID |
| `participant_name` | string | Participant name |
| `competition_type` | string | Canonical competition key |
| `category_raw` | string | Category or subtype text |
| `schedule_status` | enum | `scheduled`, `submitted_in_advance`, `unscheduled_in_program` |
| `schedule_source` | enum | `state_program`, `bethel_override`, `advance_submission`, empty |
| `notes` | string | Mapping notes |

### `excursion_day_rosters.csv`

Grain:

- one row per interested excursion selection mapped to a session day or unresolved

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `contact_phone` | string | Contact phone |
| `excursion_name` | string | Excursion label |
| `scheduled_day_label` | string | Mapped day label |
| `scheduled_date` | string | ISO date if known |
| `schedule_status` | enum | `scheduled`, `unscheduled` |
| `schedule_source` | enum | `bethel_override`, `inferred_from_label`, empty |
| `notes` | string | Mapping notes |

### `participant_conflicts.csv`

Grain:

- one row per participant conflict derived from competition schedule overlaps

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `response_id` | string | Parent response ID |
| `participant_name` | string | Participant with conflict |
| `day_label` | string | Conflict day |
| `event_date` | string | Conflict date |
| `time_raw` | string | Conflict time window |
| `conflict_type` | string | Derived conflict category |
| `event_titles` | string | Pipe-delimited competing event titles |
| `competition_types` | string | Pipe-delimited competing competition types |
| `notes` | string | Additional conflict notes |

### `daily_program_summary.csv`

Grain:

- one row per day bucket

Columns:

| Field | Type | Description |
| --- | --- | --- |
| `day_label` | string | Day or planning bucket label |
| `event_date` | string | ISO date for real days; empty for planning buckets |
| `program_event_count` | integer | Program block count |
| `competition_block_count` | integer | Number of competition-related blocks |
| `competition_participant_count` | integer | Number of scheduled competition participant rows |
| `excursion_family_count` | integer | Number of interested excursion family rows mapped to that day |
| `excursion_options` | string | Delimited excursion labels |
| `schedule_sources` | string | Delimited schedule source labels present that day |
| `operational_highlights` | string | Delimited highlight titles chosen by `is_operational_highlight(...)` |

### `summary.json`

Grain:

- one aggregate object per run

Keys:

- `total_responses`
- `yes_attending_count`
- `total_attendees`
- `daughters_count`
- `adults_count`
- `meal_counts_by_code`
- `competition_counts_by_type`
- `excursion_counts_by_option`
- `flagged_record_counts`
- `program_block_count`
- `scheduled_competition_roster_count`
- `participant_conflict_count`

## YAML Mutation Models

### `program_patches.yaml`

Schema:

```yaml
patches:
  - action: update | remove
    block_id: B001            # optional if match_event_title provided
    match_event_title: ""     # optional if block_id provided
    fields:                   # required for update
      day_label: ""
      event_date: ""
      time_raw: ""
      event_title: ""
      dress_code: ""
      event_type: ""
```

Rules:

- first matching block only is modified
- update actions recompute day and time-derived fields
- removed blocks are dropped before output

### `bethel_overrides.yaml`

Schema:

```yaml
extra_blocks:
  - day_label: ""
    event_date: ""
    time_raw: ""
    event_title: ""
    dress_code: ""
    event_type: ""
competition_overrides:
  competition_type:
    day_label: ""
    event_date: ""
    time_raw: ""
    event_title: ""
    notes: ""
competition_time_overrides:
  - competition_type: ""
    participant_group: ""
    participant_name: ""
    response_id: ""
    day_label: ""
    event_date: ""
    time_raw: ""
    event_title: ""
    notes: ""
excursion_overrides:
  excursion_name:
    day_label: ""
    event_date: ""
    notes: ""
conflict_ignores: []
```

### `competition_patches.yaml`

Schema:

```yaml
patches:
  - action: add | remove
    response_id: ""
    participant_name: ""
    competition_type: ""
    category_raw: ""
```

### `attendee_patches.yaml`

Schema:

```yaml
patches:
  - action: add | remove
    response_id: ""
    attendee_name: ""
    attendee_type: adult | daughter
    attendee_age_raw: ""
```

### `excursion_patches.yaml`

Schema:

```yaml
patches:
  - excursion_name: ""
    decision: accept | deny
```

### `schedule_map.yaml`

Schema:

```yaml
competition_event_keywords:
  competition_type:
    - exact or partial event title keyword
advance_submission_competitions:
  - competition_type
excursion_day_aliases:
  source_label: canonical_day
```

## Site-Only Derived State

Generated in `src/build_site.py`.

### `STATE`

```python
{
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

### Derived assignment object

Current fields:

| Field | Type | Description |
| --- | --- | --- |
| `title` | string | `Prep {event_title}` |
| `day` | string | Day label |
| `time` | string | Formatted call time |
| `sort_key` | string | ISO datetime when available |
| `owner` | string | Derived owner label |
| `category` | string | Humanized event type |
| `urgency` | enum | `due_now`, `high`, `medium`, `low`, `normal` |
| `status` | enum | `planned`, `ready` |
| `notes` | string | Original event title |

### Derived conflict object

Current fields extend CSV fields with:

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | Defaults to `Unresolved` |
| `resolution_note` | string | Optional operator note |
| `chosen_event` | string | Optional chosen event placeholder |
| `resolution_type` | string | Defaults to `needs_decision` |
| `escalation_logic` | enum | `escalate` if event within 48h, else `watch` |
| `conflict_pair` | string | Concise `Competition A vs Competition B` label |

### Derived family metadata

`family_flags` is added per family:

- `missing_emergency_contact`
- `allergies_listed`
- `large_family`

### Derived program metadata

`load_density` is added per program block based on blocks-per-day:

- `high` for `>= 12`
- `medium` for `>= 6`
- `low` otherwise
