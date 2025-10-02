"""Helpers for cleaning up generated export files."""

import os
import re

_TIMESTAMP_RE = re.compile(r"\d{8}_\d{6}$")


def _match_timestamped_filename(stem: str, ext: str, candidate: str) -> bool:
    if not candidate.startswith(stem + '_'):
        return False
    if ext and not candidate.endswith(ext):
        return False
    if ext:
        end = len(candidate) - len(ext)
        middle = candidate[len(stem) + 1 : end]
    else:
        middle = candidate[len(stem) + 1 :]
    return bool(_TIMESTAMP_RE.fullmatch(middle))


def list_backups(filepath: str) -> list[str]:
    directory, filename = os.path.split(filepath)
    directory = directory or '.'
    stem, ext = os.path.splitext(filename)
    backups: list[str] = []

    try:
        for candidate in os.listdir(directory):
            if _match_timestamped_filename(stem, ext, candidate):
                backups.append(os.path.join(directory, candidate))
    except FileNotFoundError:
        return []

    return backups


def cleanup_exports(filepath: str, include_canonical: bool = False) -> list[str]:
    """Remove timestamped backups for the given export path.

    If include_canonical is True, the canonical export file is also deleted.
    Returns a list of removed file paths.
    """

    removed: list[str] = []
    for backup in list_backups(filepath):
        try:
            os.remove(backup)
        except FileNotFoundError:
            continue
        removed.append(backup)

    if include_canonical and os.path.exists(filepath):
        os.remove(filepath)
        removed.append(filepath)

    return removed
