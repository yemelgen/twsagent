#!/usr/bin/env python
"""Definitions for the IB API client and utility classes."""

from __future__ import annotations

import logging
import threading
from typing import Any

from ibapi.client import EClient
from ibapi.common import BarData, TickAttrib
from ibapi.contract import Contract, ContractDescription, ContractDetails
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.ticktype import TickType
from ibapi.wrapper import EWrapper

logger = logging.getLogger("IBClient")


class IBClient(EWrapper, EClient):
    """Custom IB API client extending EClient and EWrapper.

    Do not add business logic here, only IB API callbacks.
    Callbacks can corrupt data when doing more than
    just storing values.
    """

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.events: dict[int | str, threading.Event] = {}
        self.data: dict[int | str, Any] = {}
        self.next_valid_id: int = 1
        self.id_lock = threading.Lock()
        self.data_lock = threading.Lock()
        self.connection_ready = threading.Event()

    def nextValidId(self, orderId: int) -> None:
        """Receives the next valid order ID from IB API.
        This is called automatically upon connection.
        """

        with self.id_lock:
            self.next_valid_id = orderId
            logger.info(f"Next valid ID received from IB: {orderId}")
        # Signal that connection is ready
        self.connection_ready.set()

    def start_request(self) -> int:
        """Starts a new request using IB-provided valid IDs."""

        with self.id_lock:
            req_id = self.next_valid_id
            self.next_valid_id += 1
        self.events[req_id] = threading.Event()
        return req_id

    def end_request(self, req_id: int) -> None:
        """Ends a request."""

        if req_id in self.events:
            self.events[req_id].clear()
            del self.events[req_id]
        with self.data_lock:
            if req_id in self.data:
                del self.data[req_id]

    def contractDetails(self, reqId: int, details: ContractDetails) -> None:
        """Handles contract details responses."""

        if reqId not in self.events:
            return
        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].append(details)

    def contractDetailsEnd(self, reqId: int) -> None:
        """Handles the end of contract details responses."""

        if reqId in self.events:
            self.events[reqId].set()

    def historicalData(self, reqId: int, bar: BarData) -> None:
        """Handles historical data responses."""

        if reqId not in self.events:
            return
        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        """Handles the end of historical data responses."""

        if reqId in self.events:
            self.events[reqId].set()

    def historicalTicks(self, reqId: int, ticks: list, done: bool) -> None:
        """Handles historical tick responses for MIDPOINT data."""

        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].extend(ticks)
        if done and reqId in self.events:
            self.events[reqId].set()

    def historicalTicksBidAsk(self, reqId: int, ticks: list, done: bool) -> None:
        """Handles historical tick responses for BID_ASK data."""

        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].extend(ticks)
        if done and reqId in self.events:
            self.events[reqId].set()

    def historicalTicksLast(self, reqId: int, ticks: list, done: bool) -> None:
        """Handles historical tick responses for TRADES data."""

        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].extend(ticks)
        if done and reqId in self.events:
            self.events[reqId].set()

    def securityDefinitionOptionParameter(
        self,
        reqId: int,
        exchange: str,
        underlyingConId: int,
        tradingClass: str,
        multiplier: str,
        expirations: set[str],
        strikes: set[float],
    ) -> None:
        """Handles security definition option parameter responses."""

        if reqId not in self.events:
            return
        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].append(
                {
                    "under_con_id": underlyingConId,
                    "exchange": exchange,
                    "trading_class": tradingClass,
                    "multiplier": multiplier,
                    "expirations": expirations,
                    "strikes": strikes,
                }
            )

    def securityDefinitionOptionParameterEnd(self, reqId: int) -> None:
        """Handles the end of security definition option parameter responses."""

        if reqId in self.events:
            self.events[reqId].set()

    def symbolSamples(
        self, reqId: int, contractDescriptions: list[ContractDescription]
    ) -> None:
        """Handles symbol samples responses."""

        if reqId in self.events:
            with self.data_lock:
                self.data[reqId] = contractDescriptions
            self.events[reqId].set()

    def tickPrice(
        self, reqId: int, tickType: TickType, price: float, attrib: TickAttrib
    ) -> None:
        """Handles real-time market data responses."""

        if reqId in self.events:
            with self.data_lock:
                self.data[reqId] = price
            self.events[reqId].set()

    def wshMetaData(self, reqId: int, dataJson: str) -> None:
        """Handles WSH metadata responses (available event types)."""

        if reqId in self.events:
            with self.data_lock:
                self.data[reqId] = dataJson
            self.events[reqId].set()

    def wshEventData(self, reqId: int, dataJson: str) -> None:
        """Handles WSH event data responses (corporate events)."""

        if reqId in self.events:
            with self.data_lock:
                self.data[reqId] = dataJson
            self.events[reqId].set()

    def position(
        self, account: str, contract: Contract, position: float, avgCost: float
    ) -> None:
        """Handles position responses."""
        with self.data_lock:
            if "positions" not in self.data:
                self.data["positions"] = []
            self.data["positions"].append(
                {
                    "account": account,
                    "contract": contract,
                    "position": float(position),
                    "avgCost": avgCost,
                }
            )

    def positionEnd(self) -> None:
        """Handles the end of position responses."""

        if "positions" in self.events:
            self.events["positions"].set()

    def completedOrder(
        self, contract: Contract, order: Order, orderState: OrderState
    ) -> None:
        """Handles completed order responses."""

        with self.data_lock:
            if "completed_orders" not in self.data:
                self.data["completed_orders"] = []
            self.data["completed_orders"].append(
                {
                    "contract": contract,
                    "order": order,
                    "order_state": orderState,
                }
            )

    def completedOrdersEnd(self) -> None:
        """Handles the end of completed orders responses."""

        if "completed_orders" in self.events:
            self.events["completed_orders"].set()

    def scannerParameters(self, xml: str) -> None:
        """Handles scanner parameters response."""

        with self.data_lock:
            self.data["scanner_parameters"] = xml
        if "scanner_parameters" in self.events:
            self.events["scanner_parameters"].set()

    def scannerData(
        self,
        reqId: int,
        rank: int,
        contractDetails: ContractDetails,
        distance: str,
        benchmark: str,
        projection: str,
        legsStr: str,
    ) -> None:
        """Handles scanner data responses."""

        with self.data_lock:
            if reqId not in self.data:
                self.data[reqId] = []
            self.data[reqId].append(
                {
                    "rank": rank,
                    "contract_details": contractDetails,
                    "distance": distance,
                    "benchmark": benchmark,
                    "projection": projection,
                    "legs_str": legsStr,
                }
            )

    def scannerDataEnd(self, reqId: int) -> None:
        """Handles the end of scanner data responses."""

        if reqId in self.events:
            self.events[reqId].set()

    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        """Handles errors."""

        logger.error(f"{reqId}: [{errorCode}] {errorString}")
        if reqId in self.events:
            with self.data_lock:
                self.data[reqId] = {"code": errorCode, "error": errorString}
            self.events[reqId].set()  # Ensure we don't block forever
