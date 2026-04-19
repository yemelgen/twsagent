#!/usr/bin/env python3
"""Tests for IBFormat utility class."""

from app.format import IBFormat


class TestIBFormatToDatetime:
    """Test conversion from IB API datetime format to ISO format."""

    def test_date_only(self):
        """Test conversion of date-only format."""

        assert IBFormat.to_datetime("20220101") == "2022-01-01T00:00:00+00:00"

    def test_date_with_time(self):
        """Test conversion of date with time (no timezone)."""

        assert IBFormat.to_datetime("20220101 12:00:00") == "2022-01-01T12:00:00+00:00"

    def test_date_with_time_utc(self):
        """Test conversion of date with time in UTC."""

        assert (
            IBFormat.to_datetime("20220101 12:00:00 UTC") == "2022-01-01T12:00:00+00:00"
        )

    def test_date_with_us_eastern(self):
        """Test conversion of date with US/Eastern timezone."""

        assert (
            IBFormat.to_datetime("20250226 09:30:00 US/Eastern")
            == "2025-02-26T14:30:00+00:00"
        )

    def test_date_with_us_eastern_different_time(self):
        """Test conversion matching the user's example."""

        assert (
            IBFormat.to_datetime("20260202 08:00:00 US/Eastern")
            == "2026-02-02T13:00:00+00:00"
        )

    def test_empty_string(self):
        """Test that empty string returns empty string."""

        assert IBFormat.to_datetime("") == ""

    def test_iso_format_with_timezone(self):
        """Test conversion of new ISO format with timezone offset."""

        assert (
            IBFormat.to_datetime("2026-02-27T14:30:00+00:00")
            == "2026-02-27T14:30:00+00:00"
        )

    def test_iso_format_with_z_suffix(self):
        """Test conversion of ISO format with Z suffix (Zulu time)."""

        assert IBFormat.to_datetime("2026-02-27T14:30:00Z") == "2026-02-27T14:30:00+00:00"

    def test_iso_format_with_eastern_offset(self):
        """Test conversion of ISO format with US/Eastern offset."""

        # 2026-02-27T09:30:00-05:00 is 14:30:00 UTC
        assert (
            IBFormat.to_datetime("2026-02-27T09:30:00-05:00")
            == "2026-02-27T14:30:00+00:00"
        )


class TestIBFormatFromDatetime:
    """Test conversion from ISO format to IB API datetime format."""

    def test_date_only(self):
        """Test conversion of date-only format."""

        assert IBFormat.from_datetime("2020-01-01") == "20200101 00:00:00 UTC"

    def test_datetime_no_timezone(self):
        """Test conversion of datetime without timezone."""

        assert IBFormat.from_datetime("2022-01-01T12:00:00") == "20220101 12:00:00 UTC"

    def test_datetime_utc(self):
        """Test conversion of datetime with UTC timezone."""

        assert IBFormat.from_datetime("2022-01-01T12:00:00+00") == "20220101 12:00:00 UTC"
        assert IBFormat.from_datetime("2022-01-01T12:00:00Z") == "20220101 12:00:00 UTC"

    def test_datetime_with_offset(self):
        """Test conversion of datetime with timezone offset."""

        assert (
            IBFormat.from_datetime("2025-02-26T09:30:00-05:00") == "20250226 14:30:00 UTC"
        )
        assert IBFormat.from_datetime("2022-01-01T12:00:00+03") == "20220101 09:00:00 UTC"


class TestIBFormatFromPeriod:
    """Test conversion from period to IB API duration format."""

    def test_seconds(self):
        """Test conversion of seconds."""

        assert IBFormat.from_period("60s") == "60 S"

    def test_days(self):
        """Test conversion of days."""

        assert IBFormat.from_period("30d") == "30 D"


class TestIBFormatFromInterval:
    """Test conversion from interval to IB API barSizeSetting format."""

    def test_day(self):
        """Test conversion of 1 day."""

        assert IBFormat.from_interval("1D") == "1 day"

    def test_hours(self):
        """Test conversion of multiple hours."""

        assert IBFormat.from_interval("2h") == "2 hours"

    def test_minutes(self):
        """Test conversion of minutes."""

        assert IBFormat.from_interval("3m") == "3 mins"

    def test_month(self):
        """Test conversion of month."""

        assert IBFormat.from_interval("1M") == "1 month"
