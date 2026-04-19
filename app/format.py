#!/usr/bin/env python3
"""Utility class for formatting IB API parameters."""

from datetime import datetime, timezone

from zoneinfo import ZoneInfo


class IBFormat:
    """Utility class for formatting IB API parameters."""

    UNITS = {
        "s": "secs",
        "m": "mins",
        "h": "hours",
        "d": "days",
        "D": "days",
        "W": "weeks",
        "M": "months",
        "Y": "years",
    }

    @staticmethod
    def from_string(v: str) -> str:
        """Format the string for the IB API."""

        return v.upper()

    @staticmethod
    def from_datetime(v: str) -> str:
        """Convert the datetime string to the IB API format UTC.

        Examples:
        >>> IBFormat.from_datetime("2020-01-01")
        '20200101 00:00:00 UTC'
        >>> IBFormat.from_datetime("2022-01-01T12:00:00")
        '20220101 12:00:00 UTC'
        >>> IBFormat.from_datetime("2022-01-01T12:00:00+00")
        '20220101 12:00:00 UTC'
        >>> IBFormat.from_datetime("2022-01-01T12:00:00Z")
        '20220101 12:00:00 UTC'
        >>> IBFormat.from_datetime("2025-02-26T09:30:00-05:00")
        '20250226 14:30:00 UTC'
        >>> IBFormat.from_datetime("2022-01-01T12:00:00+03")
        '20220101 09:00:00 UTC'
        """

        if not v:
            return ""
        # Ensure proper ISO format (handle space in timezone offset)
        v = v.replace(" ", "+") if len(v) > 19 and v[19] == " " else v
        dt = datetime.fromisoformat(v).replace(microsecond=0)
        if dt.tzinfo:
            # convert to utc
            dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y%m%d %H:%M:%S UTC")
        elif dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            return dt.strftime("%Y%m%d 00:00:00 UTC")
        else:
            return dt.strftime("%Y%m%d %H:%M:%S UTC")

    @staticmethod
    def from_period(v: str) -> str:
        """Convert the period string to the IB API duration format.

        Example:
        >>> IBFormat.from_period("60s")
        '60 S'
        >>> IBFormat.from_period("30d")
        '30 D'
        """

        # Assume duration is in a format where the last character is the unit.
        return f"{v[:-1]} {v[-1].upper()}"

    @classmethod
    def from_interval(cls, v: str) -> str:
        """Convert the interval string to the IB API barSizeSetting format.

        Example:
        >>> IBFormat.from_interval("1D")
        '1 day'
        >>> IBFormat.from_interval("2h")
        '2 hours'
        >>> IBFormat.from_interval("3m")
        '3 mins'
        >>> IBFormat.from_interval("1M")
        '1 month'
        """

        # If a unit key isn't found, fall back to the unit itself.
        unit = cls.UNITS.get(v[-1], v[-1])
        value = int(v[:-1])
        formatted_unit = unit[:-1] if value == 1 else unit

        return f"{v[:-1]} {formatted_unit}"

    @staticmethod
    def to_datetime(v: str) -> str:
        """Convert the IB API datetime string to a ISO datetime UTC.

        Supports both old IB format and new ISO format (auto-detects).

        Examples:
        >>> IBFormat.to_datetime("20220101")
        '2022-01-01T00:00:00+00:00'
        >>> IBFormat.to_datetime("20220101 12:00:00")
        '2022-01-01T12:00:00+00:00'
        >>> IBFormat.to_datetime("20220101 12:00:00 UTC")
        '2022-01-01T12:00:00+00:00'
        >>> IBFormat.to_datetime("20250226 09:30:00 US/Eastern")
        '2025-02-26T14:30:00+00:00'
        >>> IBFormat.to_datetime("2026-02-27T14:30:00+00:00")
        '2026-02-27T14:30:00+00:00'
        >>> IBFormat.to_datetime("2026-02-27T14:30:00Z")
        '2026-02-27T14:30:00+00:00'
        """

        if not v:
            return ""

        # Try new ISO format first (TWS may have switched to ISO/UTC format)
        if "T" in v or "-" in v[:10]:
            try:
                v_normalized = v.replace("Z", "+00:00")
                dt = datetime.fromisoformat(v_normalized)
                if dt.tzinfo:
                    dt = dt.astimezone(timezone.utc)
                else:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass  # Fall through to old format parsing

        # Parse old IB format
        parts = v.split(maxsplit=2)  # Limit to 3 parts

        try:
            if len(parts) == 1:  # '20220101' or '202201'
                fmt = "%Y%m" if len(v) == 6 else "%Y%m%d"
                dt = datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
            elif len(parts) == 2:  # '20220101 12:00:00'
                dt = datetime.strptime(v, "%Y%m%d %H:%M:%S").replace(tzinfo=timezone.utc)
            elif (
                len(parts) == 3
            ):  # '20220101 12:00:00 UTC' or '20220101 12:00:00 US/Eastern'
                dt = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y%m%d %H:%M:%S")
                try:
                    tz = ZoneInfo(parts[2])  # Convert timezone name to tzinfo
                except Exception:
                    raise ValueError(f"Unknown timezone: {parts[2]}")
                dt = dt.replace(tzinfo=tz).astimezone(timezone.utc)
            else:
                raise ValueError(f"Invalid datetime string: {v}")
        except ValueError as e:
            raise ValueError(f"Invalid datetime string: '{v}': {e}")

        return dt.isoformat()
