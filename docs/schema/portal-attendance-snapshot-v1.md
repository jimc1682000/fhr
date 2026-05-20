# Schema: `portal-attendance-snapshot/v1`

Versioned contract for raw attendance data scraped from the 104 EHR
Portal "全部刷卡資料" page. This is the JSON shape that
agent-browser's `eval` produces when iterating the Portal table; it
is consumed by fhr to populate `AttendanceRecord` (or the legacy
9-column tab-delimited `.txt` format).

## Version

`schema_version`: `"portal-attendance-snapshot/v1"`

Producers MUST write this exact string. Consumers MUST verify before
trusting the payload.

## Top-level shape

```jsonc
{
  "schema_version": "portal-attendance-snapshot/v1",
  "totalPages":     <int>,
  "recordCount":    <int>,
  "records":        [Record]
}
```

## `Record`

```jsonc
{
  "scheduledTime": "YYYY/MM/DD HH:mm",   // Portal-displayed schedule (e.g. "2026/04/01 09:30")
  "actualTime":    "YYYY/MM/DD HH:mm",   // actual punch, empty string if absent
  "type":          "上班" | "下班",
  "status":        "" | "遲到" | "曠職" | "早退" | "應刷未刷" | "資料不全"
}
```

Notes:
- `actualTime` is empty when no punch happened (e.g. weekend absent days). Use
  empty string `""`, not `null`.
- `status` is the Portal's own labeling; producers SHOULD pass it through
  unchanged. fhr re-derives late / overtime / WFH from the times rather than
  trusting `status`, but it is preserved for audit and downstream tools.
- Order: records SHOULD be in chronological order; consumers MUST NOT
  rely on ordering and SHOULD sort by `scheduledTime`.

## Example

```jsonc
{
  "schema_version": "portal-attendance-snapshot/v1",
  "totalPages": 4,
  "recordCount": 62,
  "records": [
    {"scheduledTime": "2026/04/01 09:30", "actualTime": "2026/04/01 11:52", "type": "上班", "status": "遲到"},
    {"scheduledTime": "2026/04/01 18:30", "actualTime": "2026/04/01 19:49", "type": "下班", "status": ""},
    {"scheduledTime": "2026/04/10 09:30", "actualTime": "",                  "type": "上班", "status": "曠職"}
  ]
}
```

## Producers

- `fhr portal fetch` (Phase A, `lib/portal/attendance.py`)
- ad-hoc agent-browser `eval` invocations during a Claude Code session

## Consumers

- `fhr import --from=portal-json` (`lib/importers/portal_json.py`):
  converts to the fhr-native tab-delimited 9-column `.txt`
  attendance file so the analyzer can ingest it.

## Mapping to fhr's 9-column `.txt`

| `Record` field | `.txt` column index | Notes |
|----------------|---------------------|-------|
| `scheduledTime` | 0 (應刷卡時段) | identity |
| `actualTime`    | 1 (當日卡鐘資料) | identity (empty stays empty) |
| `type`          | 2 (刷卡別) | identity |
| —               | 3 (卡鐘編號) | fixed `"1"` |
| —               | 4 (資料來源) | `"刷卡匯入"` if `actualTime` non-empty, else `""` |
| `status`        | 5 (異常狀態) | identity |
| —               | 6 (處理狀態) | always `""` — Portal marks "已處理" only after a form is filed; importing fresh snapshot leaves this empty so the analyzer treats the records as actionable |
| —               | 7 (異常處理作業) | always `""` |
| —               | 8 (備註) | always `""` |

The `.txt` MUST include a header row matching the column names above.
fhr's parser will silently drop any row whose `type` is not `上班` /
`下班`, which is how the header is filtered.
