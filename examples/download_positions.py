#!/usr/bin/env python3
"""
Download current portfolio positions from Interactive Brokers TWS

Retrieves real-time position data for all accounts including:
- Symbol and contract details
- Position quantity (long/short)
- Average cost per share/contract

Examples:
  # Get all current positions
  python download_positions.py

  # Save to file
  python download_positions.py -o positions.json

  # Get positions in summary format
  python download_positions.py --format summary
"""

import argparse
import json
import os
import sys
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


def get_positions(stub):
    """Get all current positions"""

    try:
        response = stub.GetPositions(tws_pb2.PositionsRequest(), timeout=30)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError("Timeout getting positions")
        raise Exception(f"gRPC error: {e.details()}")

    return response.positions


def format_positions_flat(positions):
    """Format positions as flat records

    Returns list of position records suitable for streaming.
    """

    records = []

    for pos in positions:
        records.append(
            {
                "account": pos.account,
                "con_id": pos.con_id,
                "symbol": pos.symbol,
                "sec_type": pos.sec_type,
                "exchange": pos.exchange,
                "currency": pos.currency,
                "local_symbol": pos.local_symbol,
                "trading_class": pos.trading_class,
                "position": pos.position,
                "avg_cost": pos.avg_cost,
                # market_value and unrealized_pnl not
                # available without market data subscription
            }
        )

    return records


def format_positions_summary(positions):
    """Format positions as summary view

    Returns grouped summary with totals and statistics.
    """

    records = format_positions_flat(positions)

    summary = {
        "positions": records,
        "total_positions": len(records),
        "long_positions": len([p for p in records if p["position"] > 0]),
        "short_positions": len([p for p in records if p["position"] < 0]),
        "by_sec_type": {},
    }

    # Group by security type
    for pos in records:
        sec_type = pos["sec_type"]
        if sec_type not in summary["by_sec_type"]:
            summary["by_sec_type"][sec_type] = 0
        summary["by_sec_type"][sec_type] += 1

    return summary


def main():
    parser = argparse.ArgumentParser(
        description=("Download current portfolio positions from Interactive Brokers TWS"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument(
        "--format",
        choices=["flat", "summary"],
        default="flat",
        help="Output format: flat records or summary (with stats)",
    )
    parser.add_argument("--host", default="localhost", help="gRPC host")
    parser.add_argument("--port", type=int, default=5005, help="gRPC port")

    args = parser.parse_args()

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    try:
        print(connect_tws(stub), file=sys.stderr)
        print("Retrieving positions...", file=sys.stderr)

        positions = get_positions(stub)

        if not positions:
            print("No positions found", file=sys.stderr)
            result = (
                [] if args.format == "flat" else {"positions": [], "total_positions": 0}
            )
        else:
            if args.format == "flat":
                result = format_positions_flat(positions)
            else:
                result = format_positions_summary(positions)

            print(f"Retrieved {len(positions)} position(s)", file=sys.stderr)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2)
            size_kb = os.path.getsize(args.output) / 1024
            print(f"Saved to {args.output} ({size_kb:.2f} KB)", file=sys.stderr)
        else:
            json.dump(result, sys.stdout, indent=2)
            print()  # Newline

        stub.Disconnect(tws_pb2.DisconnectRequest())
        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
