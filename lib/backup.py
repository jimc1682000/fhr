import os
from datetime import datetime
from typing import Optional


def backup_with_timestamp(filepath: str) -> Optional[str]:
    """If file exists, move it to a timestamped backup alongside original.

    Returns the backup path if a backup was created, otherwise None.
    """
    if not os.path.exists(filepath):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name, ext = os.path.splitext(filepath)
    backup_filepath = f"{base_name}_{timestamp}{ext}"
    os.rename(filepath, backup_filepath)
    return backup_filepath
