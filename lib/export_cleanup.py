"""Helpers for cleaning up generated export files."""

import logging
import os
import re

logger = logging.getLogger(__name__)

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
    """List timestamped backup files for the given export path.

    Args:
        filepath: Path to the canonical export file

    Returns:
        List of absolute paths to timestamped backup files

    Raises:
        ValueError: If filepath contains path traversal attempts
    """
    # Normalize and validate path to prevent directory traversal
    filepath = os.path.normpath(filepath)
    if '..' in filepath.split(os.sep):
        raise ValueError(f"Invalid filepath with directory traversal: {filepath}")

    directory, filename = os.path.split(filepath)
    directory = directory or '.'

    # Validate directory exists and is accessible
    if not os.path.isdir(directory):
        return []

    stem, ext = os.path.splitext(filename)
    backups: list[str] = []

    try:
        for candidate in os.listdir(directory):
            # Only consider files in the same directory (no subdirectories)
            if os.sep in candidate or candidate in ('.', '..'):
                continue

            if _match_timestamped_filename(stem, ext, candidate):
                backup_path = os.path.join(directory, candidate)
                # Double-check the resolved path is within the expected directory
                if os.path.dirname(os.path.abspath(backup_path)) == os.path.abspath(directory):
                    backups.append(backup_path)
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
            removed.append(backup)
        except FileNotFoundError:
            # File was already deleted, skip silently
            continue
        except (PermissionError, OSError) as e:
            # Log but don't fail - allow partial cleanup
            logger.warning(f"Failed to remove backup {backup}: {e}")
            continue

    if include_canonical and os.path.exists(filepath):
        try:
            os.remove(filepath)
            removed.append(filepath)
        except (PermissionError, OSError) as e:
            logger.error(f"Failed to remove canonical file {filepath}: {e}")
            # Re-raise for canonical file as this is more critical
            raise

    return removed
