# Leave cascade allocation (`lib/cascade.py`)

`portal-apply` consults the cascade allocator to pre-fill each leave entry's `leave_type` based on the user's current Portal balances. The user can still override per entry in the interactive prompt.

## Default cascade

```python
DEFAULT_CASCADES = {
    "leave_cascade_late": ["補休假", "特休假", "事假(含家庭照顧假)"],
    "leave_cascade_sick": ["有薪病假", "半薪病假"],
    "leave_cascade_wfh":  ["異地辦公(8hr一週)"],
}

MONTHLY_CAPS_HOURS = {
    "異地辦公(8hr一週)":  40,
    "異地辦公(12hr一週)": 60,
}
```

The mapping from `type_hint` to cascade key lives in `TYPE_HINT_TO_CASCADE` (`late` / `early_leave` → late cascade; `sick` → sick cascade; `WFH` → WFH cascade).

## Algorithm

1. Sort entries chronologically.
2. For each entry, walk its cascade in order. The **first tier with enough remaining hours absorbs the entry**:
   - Tiers with a monthly cap (`異地辦公(8hr一週)` = 40h/month) get their own `(type, YYYY-MM)` budget.
   - Tiers without a cap (`事假`, `半薪病假`) accept whatever the entry asks for once the cascade reaches them.
3. **Whole-entry only** — if 補休 has 1h left and the entry needs 2h, the *entry* falls to the next tier. We never split one form into two; that would create two separate Portal submissions for one underlying day.
4. `already_applied` (typically `state.applied_forms.leave`) pre-deducts hours so re-runs of `portal-apply` don't double-spend.

## Tuning per user

Override the defaults in `lib/config.py` (the dataclass exposes
`leave_cascade_late`, `leave_cascade_sick`, `leave_cascade_wfh`,
and `weekend_ot_default_location`) and a `config.json` overlay if
your company prefers a different order or has different monthly caps.

## Result shape

`allocate()` returns an `AllocationResult` with:

- `decisions`: one `AllocationDecision` per input entry
  - `.leave_type` — picked name, or `None` if no tier had room
  - `.reason` — human-readable explanation (shown in the interactive prompt)
  - `.insufficient` — True only when nothing fit
- `remaining` — leftover hours per tier after allocation
- `monthly_used` — `{(leave_type, "YYYY-MM"): hours}` for capped tiers

`summarize(result)` returns a one-line-per-entry plaintext block that `portal-apply` prints before the interactive phase so the user knows where each entry landed.
