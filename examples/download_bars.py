#!/usr/bin/env python3
"""
Download historical OHLCV bars from Interactive Brokers TWS

Examples:
  # Download 1-min bars for 1 day (default)
  python download_bars.py TQQQ

  # Download 5-sec bars for 2 days
  python download_bars.py TQQQ --bar-size 5s --days 2

  # Download 1-day bars for 2 years
  python download_bars.py TQQQ --bar-size 1d --years 2

  # Include extended hours
  python download_bars.py TQQQ --extended

  # Save to file
  python download_bars.py TQQQ -o bars.json
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent / "stubs"))

import grpc
import tws_pb2
import tws_pb2_grpc

EASTERN = ZoneInfo("US/Eastern")

# Bar size mapping: short name -> IB API format
BAR_SIZE_MAP = {
    "1s": "1 secs",
    "5s": "5 secs",
    "10s": "10 secs",
    "15s": "15 secs",
    "30s": "30 secs",
    "1m": "1 min",
    "2m": "2 mins",
    "3m": "3 mins",
    "5m": "5 mins",
    "10m": "10 mins",
    "15m": "15 mins",
    "20m": "20 mins",
    "30m": "30 mins",
    "1h": "1 hour",
    "2h": "2 hours",
    "3h": "3 hours",
    "4h": "4 hours",
    "8h": "8 hours",
    "1d": "1 day",
}


def connect_tws(stub):
    """Connect to TWS"""

    response = stub.Connect(
        tws_pb2.ConnectRequest(host="127.0.0.1", port=7497, client_id=1)
    )
    if not response.success:
        raise Exception(f"Failed to connect: {response.message}")
    return response.message


def get_contract_id(stub, symbol):
    """Get contract ID for a symbol"""

    try:
        response = stub.GetContractDetails(
            tws_pb2.ContractDetailsRequest(
                symbol=symbol, sec_type="STK", exchange="SMART", currency="USD"
            ),
            timeout=30,
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(
                f"Timeout looking up {symbol}."
                " TWS may be slow or disconnected."
                " Try again."
            )
        raise Exception(f"gRPC error looking up {symbol}: {e.details()}")

    if not response.contracts:
        raise ValueError(
            f"No contract found for {symbol}."
            " Check: 1) Symbol is correct,"
            " 2) TWS is connected,"
            " 3) Try again if timeout"
        )
    return response.contracts[0].con_id


def download_bars(stub, con_id, symbol, bar_size, days, years, use_rth):
    """Download historical bars"""

    if years:
        duration = f"{years} Y"
        print(
            f"Downloading {bar_size} bars for {years} year(s)...",
            file=sys.stderr,
        )
    elif days > 365:
        # IB API requires years format for durations longer than 365 days
        duration = f"{round(days / 365)} Y"
        print(
            f"Downloading {bar_size} bars for"
            f" {days} days (using {duration}"
            " IB format)...",
            file=sys.stderr,
        )
    else:
        duration = f"{days} D"
        print(f"Downloading {bar_size} bars for {days} day(s)...", file=sys.stderr)

    response = stub.GetHistoricalData(
        tws_pb2.HistoricalDataRequest(
            con_id=con_id,
            duration=duration,
            bar_size=bar_size,
            what_to_show="TRADES",
            use_rth=use_rth,
        )
    )
    if not response.bars:
        raise ValueError("No bars returned. Check service logs for IB API errors.")

    data = []
    for bar in response.bars:
        dt = datetime.fromisoformat(bar.time.replace("Z", "+00:00"))
        data.append(
            {
                "ts_s": int(dt.timestamp()),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": bar.wap,
                "trade_count": bar.bar_count,
                "source": "ibkr",
            }
        )

    return data


def main():
    parser = argparse.ArgumentParser(
        description=("Download historical OHLCV bars from Interactive Brokers TWS"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("symbol", help="Ticker symbol (e.g., TQQQ, AAPL)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--extended", action="store_true", help="Include extended hours")
    parser.add_argument("--host", default="localhost", help="gRPC host")
    parser.add_argument("--port", type=int, default=5005, help="gRPC port")
    parser.add_argument(
        "--bar-size",
        default="1m",
        choices=list(BAR_SIZE_MAP.keys()),
        help=(
            "Bar size (default: 1m). Choices:"
            " 1s,5s,10s,15s,30s,"
            " 1m,2m,3m,5m,10m,15m,20m,30m,"
            " 1h,2h,3h,4h,8h, 1d"
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to download (default: 1)",
    )
    parser.add_argument(
        "--years",
        type=int,
        help=("Number of years to download (use instead of --days for >365 days)"),
    )

    args = parser.parse_args()

    use_rth = not args.extended

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    try:
        print(connect_tws(stub), file=sys.stderr)
        con_id = get_contract_id(stub, args.symbol)
        print(f"Contract ID: {con_id}", file=sys.stderr)

        bar_size_ib = BAR_SIZE_MAP[args.bar_size]
        data = download_bars(
            stub,
            con_id,
            args.symbol,
            bar_size_ib,
            args.days,
            args.years,
            use_rth,
        )

        if data:
            start_dt = datetime.fromtimestamp(data[0]["ts_s"], tz=EASTERN)
            end_dt = datetime.fromtimestamp(data[-1]["ts_s"], tz=EASTERN)
            print(f"Retrieved {len(data)} bars", file=sys.stderr)
            print(
                f"Time range:"
                f" {start_dt.strftime('%Y-%m-%d %H:%M')}"
                f" to {end_dt.strftime('%Y-%m-%d %H:%M')}"
                " ET",
                file=sys.stderr,
            )

        if args.output:
            with open(args.output, "w") as f:
                json.dump(data, f, indent=2)
            size_kb = os.path.getsize(args.output) / 1024
            print(f"\nSaved to {args.output} ({size_kb:.2f} KB)", file=sys.stderr)
        else:
            json.dump(data, sys.stdout, indent=2)
            print()  # Newline after JSON

        stub.Disconnect(tws_pb2.DisconnectRequest())
        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
