"""Browser-driven 104 EHR Portal integration.

All modules in this package shell out to the `agent-browser` CLI; the
binary is an optional dependency. Each
caller that needs it imports lazily and surfaces a friendly error when
the tool is missing.

Public entry points live in `lib/commands/portal_*.py`.
"""
