import os
import re
from datetime import datetime, timedelta


def parse_range_and_user(filepath: str) -> tuple[str | None, str | None, str | None]:
    """Parse user name and date range from file name.

    Supports: {YYYYMM}[-{YYYYMM}]-{NAME}-出勤資料.txt

    Returns:
        (user_name, start_date 'YYYY-MM-DD', end_date 'YYYY-MM-DD')
    """
    filename = os.path.basename(filepath)
    pattern = r'(\d{6})(?:-(\d{6}))?-(.+?)-出勤資料\.txt$'
    match = re.match(pattern, filename)
    if not match:
        return None, None, None

    start_month_str = match.group(1)
    end_month_str = match.group(2)
    user_name = match.group(3)

    try:
        start_year = int(start_month_str[:4])
        start_month = int(start_month_str[4:6])
        start_date = datetime(start_year, start_month, 1).strftime("%Y-%m-%d")
    except ValueError:
        return None, None, None

    # end date
    if end_month_str:
        try:
            end_year = int(end_month_str[:4])
            end_month = int(end_month_str[4:6])
            next_year = end_year + (1 if end_month == 12 else 0)
            next_month_num = 1 if end_month == 12 else end_month + 1
            next_month = datetime(next_year, next_month_num, 1)
            end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            return None, None, None
    else:
        try:
            next_year = start_year + (1 if start_month == 12 else 0)
            next_month_num = 1 if start_month == 12 else start_month + 1
            next_month = datetime(next_year, next_month_num, 1)
            end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            return None, None, None

    return user_name, start_date, end_date

