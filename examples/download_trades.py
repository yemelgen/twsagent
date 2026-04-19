#!/usr/bin/env python3
"""
Download historical tick data from Interactive Brokers TWS

Retrieves individual trade ticks for a time window of arbitrary length.
Automatically paginates at 1,000 ticks per request with a 6-second delay
between requests to respect IB API pacing limits.

Examples:
  # Get ticks for a 1-minute bar window
  python download_trades.py TQQQ --ts 1772205420 --duration 60

  # Get a full trading day of ticks (86400 seconds)
  python download_trades.py TQQQ --ts 1772160000 --duration 86400

  # Include extended hours
  python download_trades.py TQQQ --ts 1772160000 --duration 86400 --extended

  # Save to file
  python download_trades.py TQQQ --ts 1772160000 --duration 86400 -o trades.json
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent / "stubs"))

import grpc
import tws_pb2
import tws_pb2_grpc

TICKS_PER_REQUEST = 1000
PACING_DELAY_S = 6


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


def download_trades(stub, con_id, symbol, start_ts, duration, use_rth):
    """Download all ticks for a time window.

    Paginates to respect IB API limits.

    IB allows at most TICKS_PER_REQUEST ticks per reqHistoricalTicks call.
    For large windows (e.g. a full day) this function issues multiple requests,
    advancing the start time to the last seen tick and sleeping PACING_DELAY_S
    seconds between calls.
    """

    eastern = ZoneInfo("US/Eastern")
    end_ts = start_ts + duration
    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc).astimezone(eastern)

    start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc).astimezone(eastern)
    print(
        f"Downloading ticks {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"→ {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} ...",
        file=sys.stderr,
    )

    end_time = end_dt.strftime("%Y%m%d %H:%M:%S US/Eastern")

    all_data = []
    seen_keys = set()  # (time_s, price, size, exchange)
    current_start_ts = start_ts
    request_num = 0

    while current_start_ts < end_ts:
        if request_num > 0:
            time.sleep(PACING_DELAY_S)
        request_num += 1

        current_start_dt = datetime.fromtimestamp(
            current_start_ts, tz=timezone.utc
        ).astimezone(eastern)
        start_time = current_start_dt.strftime("%Y%m%d %H:%M:%S US/Eastern")

        print(
            f"  [{request_num}] from {current_start_dt.strftime('%H:%M:%S')} ...",
            file=sys.stderr,
            end=" ",
            flush=True,
        )

        try:
            response = stub.GetHistoricalTicks(
                tws_pb2.HistoricalTicksRequest(
                    con_id=con_id,
                    start_date_time=start_time,
                    end_date_time=end_time,
                    number_of_ticks=TICKS_PER_REQUEST,
                    what_to_show="TRADES",
                    use_rth=use_rth,
                    ignore_size=True,
                )
            )
        except grpc.RpcError as e:
            raise Exception(f"gRPC error on request {request_num}: {e.details()}")

        ticks = response.ticks_last
        if not ticks:
            print("0 ticks - done", file=sys.stderr)
            break

        last_tick_ts = current_start_ts
        page_new = 0
        for tick in ticks:
            if tick.time < start_ts or tick.time >= end_ts:
                continue
            key = (tick.time, tick.price, tick.size, tick.exchange)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            dt = datetime.fromtimestamp(tick.time, tz=timezone.utc).astimezone(eastern)
            flags = tick.special_conditions.strip()
            hour, minute = dt.hour, dt.minute
            is_regular = 1 if (hour == 9 and minute >= 30) or (10 <= hour < 16) else 0

            all_data.append(
                {
                    "ts_nano": tick.time * 1_000_000_000,
                    "price": tick.price,
                    "size": tick.size,
                    "is_regular": is_regular,
                    "is_extended": 1 - is_regular,
                    "is_odd_lot": 1 if "I" in flags else 0,
                    "is_out_sequence": 1 if "O" in flags else 0,
                    "is_cancel": 1 if "C" in flags else 0,
                    "exchange": tick.exchange,
                    "source": "ibkr",
                    "raw_flags": flags,
                }
            )
            page_new += 1
            if tick.time > last_tick_ts:
                last_tick_ts = tick.time

        print(f"{page_new} new ticks (total: {len(all_data)})", file=sys.stderr)

        # Fewer than the max means we've reached the end of available data
        if len(ticks) < TICKS_PER_REQUEST:
            break

        # Advance start to the last tick's second;
        # deduplication handles any overlap
        current_start_ts = last_tick_ts

    return all_data


def main():
    parser = argparse.ArgumentParser(
        description=("Download historical tick data from Interactive Brokers TWS"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("symbol", help="Ticker symbol (e.g., TQQQ, AAPL)")
    parser.add_argument(
        "--ts", type=int, required=True, help="Start timestamp (Unix seconds)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        required=True,
        help="Window duration in seconds (e.g., 60 for 1-min bar)",
    )
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("--extended", action="store_true", help="Include extended hours")
    parser.add_argument("--host", default="localhost", help="gRPC host")
    parser.add_argument("--port", type=int, default=5005, help="gRPC port")

    args = parser.parse_args()

    use_rth = not args.extended

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    try:
        print(connect_tws(stub), file=sys.stderr)
        con_id = get_contract_id(stub, args.symbol)
        print(f"Contract ID: {con_id}", file=sys.stderr)

        data = download_trades(stub, con_id, args.symbol, args.ts, args.duration, use_rth)

        if data:
            total_volume = sum(t["size"] for t in data)
            first_dt = datetime.fromtimestamp(data[0]["ts_nano"] / 1e9, tz=timezone.utc)
            last_dt = datetime.fromtimestamp(data[-1]["ts_nano"] / 1e9, tz=timezone.utc)
            print(
                f"\nRetrieved {len(data):,} ticks, {total_volume:,} shares",
                file=sys.stderr,
            )
            print(
                f"Time range:"
                f" {first_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                " to"
                f" {last_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                " UTC",
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
