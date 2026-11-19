# Portal Replay Fixtures (v1)

Used by `test/test_e2e_portal_replay.py` via `tools/fake_agent_browser.py`.

`tools/fake_agent_browser.py` understands these subdirs:
- `open/<slug>.txt` — optional canned stdout per URL
- `eval/<sha1-10>.json` — keyed JS responses; sha = sha1(js)[:10]
- `eval/_default.json` — fallback for un-keyed eval calls (overrides
  the built-in `{"success": true, "ok": true, "matched": 1}` default)
- `snapshot/*.txt` — sequential snapshot outputs
- `screenshot.png` — canned PNG copied for every `screenshot <path>`
- `state/<session>.json` — runtime state (auto-managed, do not edit)

The dry-run E2E test only needs:
- `screenshot.png` for the dry-run capture step
- (Optional) hand-keyed eval fixtures if a specific JS call needs a
  non-default response. The built-in default
  `{"success": true, "ok": true, "matched": 1}` works for the entire
  current dry-run code path.

To re-record real Portal responses later, see `tools/record_portal_fixtures.py`
(planned for v2.1 Tier 3 follow-up).
