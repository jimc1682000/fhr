"""Exporters convert fhr's in-memory analysis results into versioned
interop payloads consumable by external tools.

Each exporter sits behind a stable schema (see `docs/schema/`). The
canonical entry point is the matching `fhr export --to=<target>`
subcommand."""
