#!/usr/bin/env python3
"""
Download completed orders from Interactive Brokers.

This script retrieves completed orders via the TWS Agent gRPC service.
Orders can be filtered to show only those placed via API.

Examples:
    # Download all completed orders
    python download_orders.py

    # Download only orders placed via API
    python download_orders.py --api-only

    # Output in flat format (one JSON per line)
    python download_orders.py --format flat

    # Save to file
    python download_orders.py -o orders.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "stubs"))

import grpc
import tws_pb2
import tws_pb2_grpc


def download_orders(
    host="localhost",
    port=5005,
    api_only=False,
    output_format="json",
    output_file=None,
):
    """Download completed orders"""
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = tws_pb2_grpc.TWSAgentStub(channel)

    request = tws_pb2.CompletedOrdersRequest(api_only=api_only)
    response = stub.GetCompletedOrders(request)

    orders = []
    for order in response.orders:
        order_dict = {
            "order_id": order.order_id,
            "client_id": order.client_id,
            "perm_id": order.perm_id,
            "con_id": order.con_id,
            "symbol": order.symbol,
            "sec_type": order.sec_type,
            "exchange": order.exchange,
            "currency": order.currency,
            "local_symbol": order.local_symbol,
            "action": order.action,
            "total_quantity": order.total_quantity,
            "filled_quantity": order.filled_quantity,
            "remaining": order.remaining,
            "order_type": order.order_type,
            "lmt_price": order.lmt_price,
            "aux_price": order.aux_price,
            "avg_fill_price": order.avg_fill_price,
            "status": order.status,
            "completed_time": order.completed_time,
            "completed_status": order.completed_status,
            "commission": order.commission,
            "commission_currency": order.commission_currency,
            "tif": order.tif,
            "outside_rth": order.outside_rth,
            "parent_id": order.parent_id,
            "order_ref": order.order_ref,
        }
        orders.append(order_dict)

    if output_format == "flat":
        output = "\n".join(json.dumps(order) for order in orders)
    elif output_format == "summary":
        by_status = {}
        by_symbol = {}
        total_commission = 0.0

        for order in orders:
            status = order["status"]
            symbol = order["symbol"]

            by_status[status] = by_status.get(status, 0) + 1
            by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
            total_commission += order["commission"]

        summary = {
            "total_orders": len(orders),
            "by_status": by_status,
            "by_symbol": by_symbol,
            "total_commission": round(total_commission, 2),
            "orders": orders,
        }
        output = json.dumps(summary, indent=2)
    else:
        output = json.dumps(orders, indent=2)

    if output_file:
        with open(output_file, "w") as f:
            f.write(output)
        print(f"Orders written to {output_file}")
    else:
        print(output)

    return len(orders)


def main():
    parser = argparse.ArgumentParser(
        description="Download completed orders from IB"
    )
    parser.add_argument("--host", default="localhost", help="gRPC server host")
    parser.add_argument(
        "--port", type=int, default=5005, help="gRPC server port"
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Only return orders placed via API",
    )
    parser.add_argument(
        "--format",
        choices=["json", "flat", "summary"],
        default="json",
        help="Output format (json=pretty, flat=one per line, summary=stats)",
    )
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    try:
        count = download_orders(
            host=args.host,
            port=args.port,
            api_only=args.api_only,
            output_format=args.format,
            output_file=args.output,
        )
        if not args.output:
            print(f"\nDownloaded {count} completed order(s)", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
