#!/usr/bin/env python3
"""
Download corporate events from Interactive Brokers Wall Street Horizon

Retrieves corporate event data including earnings, dividends, splits,
conferences, and other company events.

NOTE: WSH corporate events require a subscription with Interactive Brokers.
      If you see error 10276 "News feed is not allowed", you need to subscribe
      to the WSH data feed through your IBKR account settings.

Examples:
  # Get all events for a symbol
  python download_events.py AAPL

  # Get only earnings events
  python download_events.py AAPL --filter Earnings

  # Get events for a date range
  python download_events.py AAPL --start 20240101 --end 20241231

  # Get events for multiple symbols
  python download_events.py AAPL MSFT GOOGL

  # Save to file
  python download_events.py AAPL -o events.json

  # Limit number of results
  python download_events.py AAPL --limit 100
"""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "stubs"))

import grpc
import tws_pb2
import tws_pb2_grpc


def connect_tws(stub):
    """Connect to TWS"""

    response = stub.Connect(
        tws_pb2.ConnectRequest(host="127.0.0.1", port=7497, client_id=1)
    )
    if not response.success:
        raise Exception(f"Failed to connect: {response.message}")
    return response.message


def get_contract_id(stub, symbol, sec_type="STK"):
    """Get contract ID for a symbol"""

    try:
        response = stub.GetContractDetails(
            tws_pb2.ContractDetailsRequest(
                symbol=symbol,
                sec_type=sec_type,
                exchange="SMART",
                currency="USD",
            ),
            timeout=30,
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(f"Timeout looking up {symbol}")
        raise Exception(f"gRPC error: {e.details()}")

    if not response.contracts:
        return None

    return response.contracts[0].con_id


def get_wsh_events(
    stub,
    con_id,
    filter="",
    start_date="",
    end_date="",
    fill_watchlist=False,
    fill_portfolio=False,
    fill_competitors=False,
    total_limit=0,
):
    """Get WSH event data for a contract"""

    try:
        response = stub.GetWshEventData(
            tws_pb2.WshEventDataRequest(
                con_id=con_id,
                filter=filter,
                fill_watchlist=fill_watchlist,
                fill_portfolio=fill_portfolio,
                fill_competitors=fill_competitors,
                start_date=start_date,
                end_date=end_date,
                total_limit=total_limit,
            ),
            timeout=30,
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(f"Timeout getting events for contract {con_id}")
        raise Exception(f"gRPC error: {e.details()}")

    if not response.json_data:
        return []

    try:
        events = json.loads(response.json_data)
        return events if isinstance(events, list) else [events]
    except json.JSONDecodeError:
        print("Warning: Failed to parse JSON response", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Download corporate events from Interactive Brokers WSH",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("symbols", nargs="*", help="Ticker symbols (e.g., AAPL MSFT)")
    parser.add_argument("-f", "--file", help="Read symbols from file (one per line)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument(
        "--filter",
        default="",
        help="Event type filter (e.g., Earnings, Dividends, Splits)",
    )
    parser.add_argument(
        "--start",
        default="",
        help="Start date in YYYYMMDD format (e.g., 20240101)",
    )
    parser.add_argument(
        "--end", default="", help="End date in YYYYMMDD format (e.g., 20241231)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of events to return (0 = no limit)",
    )
    parser.add_argument(
        "--watchlist", action="store_true", help="Include watchlist events"
    )
    parser.add_argument(
        "--portfolio", action="store_true", help="Include portfolio events"
    )
    parser.add_argument(
        "--competitors", action="store_true", help="Include competitor events"
    )
    parser.add_argument("--sec-type", default="STK", help="Security type (default: STK)")
    parser.add_argument("--host", default="localhost", help="gRPC host")
    parser.add_argument("--port", type=int, default=5005, help="gRPC port")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )

    args = parser.parse_args()

    symbols = args.symbols or []
    if args.file:
        with open(args.file, "r") as f:
            file_symbols = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
            symbols.extend(file_symbols)

    if not symbols:
        parser.error("No symbols provided. Use positional arguments or --file")

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    try:
        print(connect_tws(stub), file=sys.stderr)
        print(f"Processing {len(symbols)} symbol(s)...", file=sys.stderr)

        all_events = []
        for i, symbol in enumerate(symbols, 1):
            try:
                print(
                    f"[{i}/{len(symbols)}] {symbol}...",
                    file=sys.stderr,
                    end=" ",
                )

                con_id = get_contract_id(stub, symbol, args.sec_type)
                if not con_id:
                    print("! Not found", file=sys.stderr)
                    continue

                events = get_wsh_events(
                    stub,
                    con_id,
                    filter=args.filter,
                    start_date=args.start,
                    end_date=args.end,
                    fill_watchlist=args.watchlist,
                    fill_portfolio=args.portfolio,
                    fill_competitors=args.competitors,
                    total_limit=args.limit,
                )

                # Add symbol to each event for reference
                for event in events:
                    if isinstance(event, dict):
                        event["symbol"] = symbol
                        event["con_id"] = con_id

                all_events.extend(events)
                print(f"+ {len(events)} event(s)", file=sys.stderr)

                # Rate limiting
                if i < len(symbols):
                    time.sleep(args.delay)

            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                continue

        print(f"\nRetrieved {len(all_events)} total events", file=sys.stderr)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(all_events, f, indent=2)
            size_kb = os.path.getsize(args.output) / 1024
            print(f"Saved to {args.output} ({size_kb:.2f} KB)", file=sys.stderr)
        else:
            json.dump(all_events, sys.stdout, indent=2)
            print()  # Newline

        stub.Disconnect(tws_pb2.DisconnectRequest())
        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
