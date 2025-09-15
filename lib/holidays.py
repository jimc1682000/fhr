import logging
import os
import ssl
import urllib.request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
import json as _json
import random
import socket
import time
from datetime import datetime


logger = logging.getLogger(__name__)


class HolidayProvider:
    def load(self, year: int) -> set[datetime.date]:  # pragma: no cover (interface)
        return set()


class Hardcoded2025Provider(HolidayProvider):
    def load(self, year: int) -> set[datetime.date]:
        if year != 2025:
            return set()
        dates = [
            # 元旦連假
            "2025/01/01",
            # 農曆春節
            "2025/01/25", "2025/01/26", "2025/01/27", "2025/01/28", "2025/01/29", "2025/01/30", "2025/01/31", "2025/02/01", "2025/02/02",
            # 和平紀念日
            "2025/02/28", "2025/03/01", "2025/03/02",
            # 兒童節/清明節
            "2025/04/03", "2025/04/04", "2025/04/05", "2025/04/06",
            # 端午節
            "2025/05/30", "2025/05/31", "2025/06/01",
            # 中秋節
            "2025/10/04", "2025/10/05", "2025/10/06",
            # 國慶日
            "2025/10/10", "2025/10/11", "2025/10/12",
        ]
        out: set[datetime.date] = set()
        for s in dates:
            try:
                out.add(datetime.strptime(s, "%Y/%m/%d").date())
            except ValueError:
                logger.warning("無效的日期: %s", s)
        return out


class BasicFixedProvider(HolidayProvider):
    def load(self, year: int) -> set[datetime.date]:
        out: set[datetime.date] = set()
        for s in (f"{year}/01/01", f"{year}/10/10"):
            try:
                out.add(datetime.strptime(s, "%Y/%m/%d").date())
            except ValueError:
                logger.warning("無效的日期: %s", s)
        return out


class TaiwanGovOpenDataProvider(HolidayProvider):
    def __init__(self):
        try:
            self.max_retries = int(os.getenv("HOLIDAY_API_MAX_RETRIES", "3"))
        except ValueError:
            self.max_retries = 3
        try:
            self.base_backoff = float(os.getenv("HOLIDAY_API_BACKOFF_BASE", "0.5"))
        except ValueError:
            self.base_backoff = 0.5
        try:
            self.max_backoff = float(os.getenv("HOLIDAY_API_MAX_BACKOFF", "8"))
        except ValueError:
            self.max_backoff = 8.0

    def load(self, year: int) -> set[datetime.date]:
        url = (
            "https://data.gov.tw/api/v1/rest/datastore_search?"
            f"resource_id=W2&filters={{\"date\":\"{year}\"}}"
        )
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            logger.warning("不支援的 URL scheme: %s", parsed.scheme)
            return set()
        context = ssl.create_default_context()

        attempt = 0
        while attempt <= self.max_retries:
            attempt += 1
            try:
                logger.info("資訊: 嘗試載入 %d 年假日 (第 %d/%d 次)...", year, attempt, self.max_retries)
                with urllib.request.urlopen(url, timeout=10, context=context) as resp:  # nosec B310
                    data = _json.loads(resp.read().decode('utf-8'))
                    out: set[datetime.date] = set()
                    if 'result' in data and 'records' in data['result']:
                        for record in data['result']['records']:
                            if record.get('isHoliday', 0) == 1:
                                date_str = record.get('date', '')
                                if date_str:
                                    try:
                                        out.add(datetime.strptime(date_str, "%Y-%m-%d").date())
                                    except ValueError as e:
                                        logger.warning("跳過無效的日期格式 %r: %s", date_str, e)
                        if out:
                            return out
                        logger.warning("API 回傳資料但沒有有效的假日記錄")
                        raise RuntimeError("empty holiday records")
            except HTTPError as e:
                status = getattr(e, 'code', None)
                if status in (429, 500, 502, 503, 504):
                    err_desc = f"HTTP {status}"
                else:
                    logger.warning("無法從API載入 %d 年假日資料: HTTP %s — 不重試。", year, status)
                    return set()
            except (URLError, socket.timeout, TimeoutError, _json.JSONDecodeError, ValueError) as e:
                err_desc = f"連線/解析錯誤: {e}"
            except Exception as e:
                err_desc = f"一般錯誤: {e}"

            if attempt > self.max_retries:
                logger.error("錯誤: 嘗試 %d 次後仍無法載入 %d 年假日資料。回退到基本假日。", self.max_retries, year)
                break

            sleep_s = min(self.max_backoff, self.base_backoff * (2 ** (attempt - 1)))
            jitter = sleep_s * random.uniform(-0.1, 0.1)
            time.sleep(max(0.0, sleep_s + jitter))

        return set()


class HolidayService:
    def __init__(self):
        self.hardcoded = Hardcoded2025Provider()
        self.gov = TaiwanGovOpenDataProvider()
        self.basic = BasicFixedProvider()

    def load_year(self, year: int) -> set[datetime.date]:
        if year == 2025:
            return self.hardcoded.load(year)
        # try gov, fallback basic
        out = self.gov.load(year)
        if out:
            return out
        logger.warning("無法取得 %d 年完整假日資料，僅載入基本固定假日", year)
        return self.basic.load(year)

    def load_years(self, years: set) -> set[datetime.date]:
        out: set[datetime.date] = set()
        for y in years:
            out |= self.load_year(y)
        return out

