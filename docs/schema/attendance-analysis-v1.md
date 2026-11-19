# Schema: `attendance-analysis/v1`

Versioned contract for fhr's analysis output. Consumed by tools that want
to act on fhr's overtime / leave / WFH suggestions (e.g. `fhr portal-apply`).

## Purpose

fhr produces this JSON whenever it needs to hand off concrete
"apply-this-form" candidates to another system. The schema is stable
across minor bumps — adding fields is fine, renaming or removing is
a major bump.

## Version

`schema_version`: `"attendance-analysis/v1"`

Producers MUST write this exact string. Consumers MUST verify it before
trusting the payload (see [`lib/schema.py`](../../lib/schema.py)).
Unknown major versions: refuse to parse with a friendly message.

## Top-level shape

```jsonc
{
  "schema_version": "attendance-analysis/v1",
  "cutoff_date":    "YYYY/MM/DD" | null,        // last-applied-form date, or null
  "analysis_end":   "YYYY/MM/DD" | null,        // end of the analysed period (`--today`), or null
  "overtime":       [OvertimeEntry],
  "leave":          [LeaveEntry],
  "skipped":        [SkippedEntry],             // dates dropped during conversion
  "summary":        Summary
}
```

## `OvertimeEntry`

```jsonc
{
  "date":       "YYYY/MM/DD",
  "start_time": "HHMM",        // expected_checkout (e.g. "1830" or early-arrival "1810")
  "end_time":   "HHMM",        // start_time + hours, floor to whole hours
  "hours":      <int>,         // applicable overtime, minimum 1
  "location":   "在辦公室" | "在外地",
  "reason":     "<freeform>"   // HR-friendly summary
}
```

Rules:
- `hours = floor(actual_overtime_minutes / 60)`, must be `>= 1` (entries below the
  minimum are dropped to `skipped`).
- `end_time = start_time + hours * 1h`, NOT the actual punch-out time. The
  Portal recomputes the total from start/end on submit.

## `LeaveEntry`

```jsonc
{
  "date":       "YYYY/MM/DD",
  "start_time": "HHMM",
  "end_time":   "HHMM",
  "hours":      <int>,
  "type_hint":  "late" | "early_leave" | "WFH" | "sick",
  "reason":     "<freeform>"
}
```

Rules:
- `type_hint` is advisory; the consumer (or cascade allocator) decides the
  exact leave type (補休 / 特休 / 事假 / 有薪病假 / 半薪病假 / 異地辦公).
- For `late` / `early_leave`: `hours = ceil(late_minutes / 60)` with a 1-hour
  minimum. `end_time = start_time + hours * 1h`.
- For `WFH`: full-day default `start_time=0930` `end_time=1830` `hours=9`
  (matches the schedule's working window; lunch excluded by Portal).
- `type_hint="sick"` is a producer hint — consumers should suggest 有薪病假
  first, then fall back to 半薪病假 per their cascade config.

## `SkippedEntry`

```jsonc
{
  "date":   "YYYY/MM/DD",
  "type":   "加班" | "遲到" | "早退" | "WFH假",
  "reason": "<1h" | "<= cutoff" | "future" | "no time" | "<freeform>"
}
```

## `Summary`

```jsonc
{
  "overtime_count": <int>,
  "overtime_hours": <int>,
  "leave_count":    <int>,
  "leave_hours":    <int>
}
```

Counts and hours MUST equal the lengths/sums of the corresponding arrays.

## Example

```jsonc
{
  "schema_version": "attendance-analysis/v1",
  "cutoff_date": "2033/06/17",
  "analysis_end": "2033/07/19",
  "overtime": [
    {
      "date": "2033/06/22",
      "start_time": "1810",
      "end_time": "2010",
      "hours": 2,
      "location": "在辦公室",
      "reason": "工作需要"
    }
  ],
  "leave": [
    {
      "date": "2033/06/24",
      "start_time": "0930",
      "end_time": "1830",
      "hours": 9,
      "type_hint": "WFH",
      "reason": "WFH"
    },
    {
      "date": "2033/07/04",
      "start_time": "0930",
      "end_time": "1230",
      "hours": 3,
      "type_hint": "sick",
      "reason": "看診"
    }
  ],
  "skipped": [
    {"date": "2033/07/22", "type": "WFH假", "reason": "future"}
  ],
  "summary": {
    "overtime_count": 1,
    "overtime_hours": 2,
    "leave_count": 2,
    "leave_hours": 12
  }
}
```

## Producers

- `fhr export --to=analysis-v1 <attendance-file>` (`lib/exporters/analysis_v1.py`)

## Consumers

- `fhr portal apply` (Phase C, internal — uses in-memory issues
  instead of round-tripping through JSON, but exposes the same schema
  via `--export` for inspection)
