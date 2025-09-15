import unittest
from datetime import datetime
from unittest import mock

import lib.holidays as H
from test.test_helpers import temp_env

"""DummyResp is imported from shared test helpers."""


class TestHolidaysExtraCoverage(unittest.TestCase):
    def test_base_interface_load(self):
        # Exercise HolidayProvider.load default implementation
        # (pragma comment not honored by stdlib trace)
        self.assertEqual(H.HolidayProvider().load(2025), set())

    def test_hardcoded_2025_handles_value_error(self):
        real_dt = H.datetime

        class DTProxy:
            calls = 0
            @classmethod
            def strptime(cls, s, fmt):
                cls.calls += 1
                if cls.calls == 1:
                    raise ValueError('boom')
                return real_dt.strptime(s, fmt)

        with mock.patch('lib.holidays.datetime', new=DTProxy):
            out = H.Hardcoded2025Provider().load(2025)
        # still returns a set (with first date skipped)
        self.assertTrue(any(d.year == 2025 for d in out))

    def test_basic_fixed_handles_value_error(self):
        real_dt = H.datetime
        class DTProxy:
            calls = 0
            @classmethod
            def strptime(cls, s, fmt):
                cls.calls += 1
                if cls.calls == 1:
                    raise ValueError('bad-basic')
                return real_dt.strptime(s, fmt)
        with mock.patch('lib.holidays.datetime', new=DTProxy):
            out = H.BasicFixedProvider().load(2027)
        self.assertTrue(any(d.year == 2027 for d in out))

    def test_service_returns_gov_when_nonempty(self):
        with temp_env(
            HOLIDAY_API_MAX_RETRIES='0',
            HOLIDAY_API_BACKOFF_BASE='0',
            HOLIDAY_API_MAX_BACKOFF='0'
        ):
            svc = H.HolidayService()
            fake_set = {datetime(2026, 1, 1).date()}
            with mock.patch.object(H.TaiwanGovOpenDataProvider, 'load', return_value=fake_set):
                out = svc.load_year(2026)
        self.assertEqual(out, fake_set)


if __name__ == '__main__':
    unittest.main()
"""Category: Holidays/Providers
Purpose: Provider edge handling and service behavior when gov returns data."""
