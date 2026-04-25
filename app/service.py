#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys
import threading
from concurrent import futures
from typing import Any

import grpc
import tws_pb2
import tws_pb2_grpc
from client import IBClient
from format import IBFormat
from pacer import IBPacer

from ibapi.common import WshEventData
from ibapi.contract import Contract, ContractDetails
from ibapi.scanner import ScannerSubscription

logger = logging.getLogger("IBService")
IB = IBClient()


class IBServicer(tws_pb2_grpc.TWSAgentServicer):
    """gRPC servicer implementation for IB Agent"""

    def __init__(self, ib_client: IBClient, pacer: IBPacer) -> None:
        self.ib = ib_client
        self.pacer = pacer

    def _check_connection(self, context: grpc.ServicerContext) -> bool:
        """Check if connected to TWS/Gateway, set gRPC error if not.
        Returns True if connected, False otherwise.
        """

        if not self.ib.isConnected():
            logger.warning("Operation attempted without connection to TWS")
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            context.set_details(
                "Not connected to TWS/Gateway. Please call Connect first."
            )
            return False
        return True

    def Connect(
        self,
        request: tws_pb2.ConnectRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.ConnectResponse:
        """Establish connection to TWS/IB Gateway with retry logic"""
        try:
            if self.ib.isConnected():
                return tws_pb2.ConnectResponse(success=True, message="Already connected")

            host = request.host or os.getenv("TWS_HOST")
            port = request.port or int(os.getenv("TWS_PORT"))
            client_id = request.client_id or int(os.getenv("TWS_CLIENT_ID"))

            self.ib.connection_ready.clear()

            self.ib.connect(host, port, client_id)

            t = threading.Thread(target=self.ib.run, daemon=True)
            t.start()

            # Wait for connection to be established (nextValidId callback)
            # Try with increasing timeouts and retry logic
            max_retries = 3
            timeout = 5

            for attempt in range(max_retries):
                logger.info(
                    "Waiting for connection confirmation"
                    f" (attempt {attempt + 1}"
                    f"/{max_retries})..."
                )
                if self.ib.connection_ready.wait(timeout=timeout):
                    logger.info(
                        f"Connected to TWS at {host}:{port} with client_id={client_id}"
                    )
                    return tws_pb2.ConnectResponse(
                        success=True, message=f"Connected to {host}:{port}"
                    )

                if not self.ib.isConnected():
                    break

                # Increase timeout for next attempt
                timeout = min(timeout * 2, 15)

            logger.error(f"Connection verification timeout after {max_retries} attempts")
            if self.ib.isConnected():
                self.ib.disconnect()

            return tws_pb2.ConnectResponse(
                success=False,
                message=("Connection timeout - could not verify connection to TWS"),
            )
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            if self.ib.isConnected():
                self.ib.disconnect()
            return tws_pb2.ConnectResponse(success=False, message=str(e))

    def Disconnect(
        self,
        request: tws_pb2.DisconnectRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.DisconnectResponse:
        """Disconnect from TWS/IB Gateway"""

        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                self.ib.connection_ready.clear()
                logger.info("Disconnected from TWS")
            return tws_pb2.DisconnectResponse(success=True)
        except Exception as e:
            logger.error(f"Disconnect failed: {e}")
            return tws_pb2.DisconnectResponse(success=False)

    def _req_contract_details(
        self,
        symbol: str,
        secType: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> list[ContractDetails] | dict[str, Any]:
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        if not self.pacer.acquire("general"):
            return {"code": 0, "error": "Rate limit timeout"}

        contract = Contract()
        contract.symbol = symbol
        contract.secType = secType
        contract.currency = currency
        if exchange and exchange != "SMART":
            contract.exchange = "SMART"
            contract.primaryExchange = exchange
        else:
            contract.exchange = exchange or "SMART"

        req_id = self.ib.start_request()
        self.ib.reqContractDetails(req_id, contract)

        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        data = self.ib.data.get(req_id, [])
        self.ib.end_request(req_id)

        return data

    def _req_historical_data(
        self,
        conId: int,
        duration: str = "1 D",
        barSize: str = "5 mins",
        whatToShow: str = "TRADES",
        useRTH: bool = False,
        exchange: str = "",
    ) -> list | dict[str, Any]:
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        signature = f"hist_data:{conId}:{duration}:{barSize}:{whatToShow}:{useRTH}"
        contract_key = f"{conId}:{exchange or 'SMART'}:{whatToShow}"
        if not self.pacer.acquire("historical", signature=signature, contract_key=contract_key):
            return {"code": 0, "error": "Rate limit timeout"}

        contract = Contract()
        contract.conId = conId
        contract.exchange = exchange or "SMART"

        req_id = self.ib.start_request()

        self.ib.reqHistoricalData(
            req_id,
            contract,
            "",  # endDateTime = now
            duration,
            barSize,
            whatToShow,
            1 if useRTH else 0,
            1,  # formatDate
            False,
            [],
        )

        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        with self.ib.data_lock:
            data = self.ib.data.get(req_id, [])
        self.ib.end_request(req_id)

        return data

    def _req_historical_ticks(
        self,
        conId: int,
        start_date_time: str = "",
        end_date_time: str = "",
        number_of_ticks: int = 1000,
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        ignore_size: bool = True,
        exchange: str = "",
    ) -> list | dict[str, Any]:
        """Request historical Time & Sales data"""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        signature = f"hist_ticks:{conId}:{start_date_time}:{end_date_time}:{what_to_show}"
        contract_key = f"{conId}:{exchange or 'SMART'}:{what_to_show}"
        if not self.pacer.acquire("historical", signature=signature, contract_key=contract_key):
            return {"code": 0, "error": "Rate limit timeout"}

        contract = Contract()
        contract.conId = conId
        contract.exchange = exchange or "SMART"

        req_id = self.ib.start_request()

        self.ib.reqHistoricalTicks(
            req_id,
            contract,
            start_date_time,
            end_date_time,
            number_of_ticks,
            what_to_show,
            1 if use_rth else 0,
            ignore_size,
            [],
        )

        # First request can be slow
        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        data = self.ib.data.get(req_id, [])
        self.ib.end_request(req_id)

        return data

    def _req_wsh_meta_data(self) -> str | dict[str, Any]:
        """Request WSH metadata (available event types)"""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        if not self.pacer.acquire("general"):
            return {"code": 0, "error": "Rate limit timeout"}

        req_id = self.ib.start_request()
        self.ib.reqWshMetaData(req_id)

        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        with self.ib.data_lock:
            data = self.ib.data.get(req_id, "")
        self.ib.end_request(req_id)

        return data

    def _req_wsh_event_data(
        self,
        conId: int,
        filter: str = "",
        fillWatchlist: bool = False,
        fillPortfolio: bool = False,
        fillCompetitors: bool = False,
        startDate: str = "",
        endDate: str = "",
        totalLimit: int = 0,
    ) -> str | dict[str, Any]:
        """Request WSH event data (corporate events)"""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        if not self.pacer.acquire("general"):
            return {"code": 0, "error": "Rate limit timeout"}

        wsh_event_data = WshEventData()
        wsh_event_data.conId = conId
        wsh_event_data.filter = filter
        wsh_event_data.fillWatchlist = fillWatchlist
        wsh_event_data.fillPortfolio = fillPortfolio
        wsh_event_data.fillCompetitors = fillCompetitors
        wsh_event_data.startDate = startDate
        wsh_event_data.endDate = endDate
        wsh_event_data.totalLimit = totalLimit

        req_id = self.ib.start_request()
        self.ib.reqWshEventData(req_id, wsh_event_data)

        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        with self.ib.data_lock:
            data = self.ib.data.get(req_id, "")
        self.ib.end_request(req_id)

        return data

    def _req_option_chain(
        self,
        underlyingSymbol: str,
        futFopExchange: str = "",
        underlyingSecType: str = "STK",
        underlyingConId: int = 0,
    ) -> list | dict[str, Any]:
        """Request option chain parameters"""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        if not self.pacer.acquire("general"):
            return {"code": 0, "error": "Rate limit timeout"}

        # If no contract ID provided, look it up first
        # Always use SMART for underlying contract lookup
        # futFopExchange is for filtering option exchanges,
        # not for the underlying
        if underlyingConId == 0:
            contract_data = self._req_contract_details(
                underlyingSymbol, underlyingSecType, "SMART", "USD"
            )

            if isinstance(contract_data, dict) and "error" in contract_data:
                return contract_data

            if not contract_data:
                return {
                    "code": 0,
                    "error": f"Contract not found for {underlyingSymbol}",
                }

            underlyingConId = contract_data[0].contract.conId

        req_id = self.ib.start_request()
        self.ib.reqSecDefOptParams(
            req_id,
            underlyingSymbol,
            futFopExchange,
            underlyingSecType,
            underlyingConId,
        )

        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        with self.ib.data_lock:
            data = self.ib.data.get(req_id, [])
        self.ib.end_request(req_id)

        return data

    def GetContractDetails(
        self,
        request: tws_pb2.ContractDetailsRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.ContractDetailsResponse:
        """Get contract details for a symbol"""
        if not self._check_connection(context):
            return tws_pb2.ContractDetailsResponse()

        try:
            data = self._req_contract_details(
                request.symbol,
                request.sec_type or "STK",
                request.exchange or "SMART",
                request.currency or "USD",
            )

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error for {request.symbol}: [{error_code}] {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.ContractDetailsResponse(contracts=[])

            contracts = []
            for d in data:
                # Extract security IDs (ISIN, CUSIP, etc.)
                sec_ids = []
                if d.secIdList:
                    for tag_value in d.secIdList:
                        sec_ids.append(
                            tws_pb2.SecIdTag(tag=tag_value.tag, value=tag_value.value)
                        )

                contracts.append(
                    tws_pb2.ContractInfo(
                        con_id=d.contract.conId,
                        symbol=d.contract.symbol,
                        exchange=d.contract.exchange,
                        currency=d.contract.currency,
                        sec_type=d.contract.secType,
                        local_symbol=d.contract.localSymbol,
                        trading_class=d.contract.tradingClass,
                        primary_exchange=d.contract.primaryExchange or "",
                        long_name=d.longName or "",
                        industry=d.industry or "",
                        category=d.category or "",
                        subcategory=d.subcategory or "",
                        min_tick=d.minTick,
                        multiplier=d.contract.multiplier or "",
                        sec_ids=sec_ids,
                        market_name=d.marketName or "",
                        time_zone_id=d.timeZoneId or "",
                        trading_hours=d.tradingHours or "",
                        liquid_hours=d.liquidHours or "",
                    )
                )

            logger.info(f"Retrieved {len(contracts)} contracts for {request.symbol}")
            return tws_pb2.ContractDetailsResponse(contracts=contracts)
        except Exception as e:
            logger.error(f"GetContractDetails failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.ContractDetailsResponse()

    def GetHistoricalData(
        self,
        request: tws_pb2.HistoricalDataRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.HistoricalDataResponse:
        """Get historical bar data"""
        if not self._check_connection(context):
            return tws_pb2.HistoricalDataResponse()

        try:
            data = self._req_historical_data(
                request.con_id,
                request.duration or "1 D",
                request.bar_size or "5 mins",
                request.what_to_show or "TRADES",
                request.use_rth,
                request.exchange,
            )

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error for contract"
                    f" {request.con_id}:"
                    f" [{error_code}]"
                    f" {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.HistoricalDataResponse(bars=[])

            bars = [
                tws_pb2.Bar(
                    time=IBFormat.to_datetime(b.date),
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=int(b.volume),
                    bar_count=int(b.barCount),
                    wap=float(b.wap),
                )
                for b in data
            ]

            logger.info(f"Retrieved {len(bars)} bars for contract {request.con_id}")
            return tws_pb2.HistoricalDataResponse(bars=bars)
        except Exception as e:
            logger.error(f"GetHistoricalData failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.HistoricalDataResponse()

    def GetHistoricalTicks(
        self,
        request: tws_pb2.HistoricalTicksRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.HistoricalTicksResponse:
        """Get historical Time & Sales tick data"""
        try:
            data = self._req_historical_ticks(
                request.con_id,
                request.start_date_time or "",
                request.end_date_time or "",
                request.number_of_ticks or 1000,
                request.what_to_show or "TRADES",
                request.use_rth,
                request.ignore_size,
                request.exchange,
            )

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error for contract"
                    f" {request.con_id}:"
                    f" [{error_code}]"
                    f" {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.HistoricalTicksResponse()

            response = tws_pb2.HistoricalTicksResponse()
            what_to_show = request.what_to_show or "TRADES"

            if what_to_show == "TRADES":
                response.ticks_last.extend(
                    [
                        tws_pb2.HistoricalTickLast(
                            time=tick.time,
                            price=float(tick.price),
                            size=int(tick.size),
                            exchange=tick.exchange,
                            special_conditions=tick.specialConditions,
                        )
                        for tick in data
                    ]
                )
            elif what_to_show == "BID_ASK":
                response.ticks_bid_ask.extend(
                    [
                        tws_pb2.HistoricalTickBidAsk(
                            time=tick.time,
                            price_bid=float(tick.priceBid),
                            price_ask=float(tick.priceAsk),
                            size_bid=int(tick.sizeBid),
                            size_ask=int(tick.sizeAsk),
                        )
                        for tick in data
                    ]
                )
            elif what_to_show == "MIDPOINT":
                response.ticks_midpoint.extend(
                    [
                        tws_pb2.HistoricalTickMidPoint(
                            time=tick.time, price=float(tick.price)
                        )
                        for tick in data
                    ]
                )

            logger.info(f"Retrieved {len(data)} ticks for contract {request.con_id}")
            return response
        except Exception as e:
            logger.error(f"GetHistoricalTicks failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.HistoricalTicksResponse()

    def GetWshMetaData(
        self,
        request: tws_pb2.WshMetaDataRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.WshMetaDataResponse:
        """Get WSH metadata (available event types)"""
        if not self._check_connection(context):
            return tws_pb2.WshMetaDataResponse()

        try:
            data = self._req_wsh_meta_data()

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error getting WSH metadata: [{error_code}] {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.WshMetaDataResponse(json_data="")

            logger.info("Retrieved WSH metadata")
            return tws_pb2.WshMetaDataResponse(json_data=data)
        except Exception as e:
            logger.error(f"GetWshMetaData failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.WshMetaDataResponse()

    def GetWshEventData(
        self,
        request: tws_pb2.WshEventDataRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.WshEventDataResponse:
        """Get WSH event data (corporate events)"""
        if not self._check_connection(context):
            return tws_pb2.WshEventDataResponse()

        try:
            data = self._req_wsh_event_data(
                request.con_id,
                request.filter or "",
                request.fill_watchlist,
                request.fill_portfolio,
                request.fill_competitors,
                request.start_date or "",
                request.end_date or "",
                request.total_limit or 0,
            )

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error for contract"
                    f" {request.con_id}:"
                    f" [{error_code}]"
                    f" {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.WshEventDataResponse(json_data="")

            logger.info(f"Retrieved WSH event data for contract {request.con_id}")
            return tws_pb2.WshEventDataResponse(json_data=data)
        except Exception as e:
            logger.error(f"GetWshEventData failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.WshEventDataResponse()

    def GetOptionChain(
        self,
        request: tws_pb2.OptionChainRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.OptionChainResponse:
        """Get option chain parameters (expirations and strikes)"""
        if not self._check_connection(context):
            return tws_pb2.OptionChainResponse()

        try:
            data = self._req_option_chain(
                request.underlying_symbol,
                request.fut_fop_exchange or "",
                request.underlying_sec_type or "STK",
                request.underlying_con_id or 0,
            )

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error for"
                    f" {request.underlying_symbol}:"
                    f" [{error_code}]"
                    f" {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.OptionChainResponse(chains=[])

            chains = []
            for chain_data in data:
                expirations_raw = sorted(list(chain_data["expirations"]))
                expirations = [
                    f"{exp[:4]}-{exp[4:6]}-{exp[6:]}" for exp in expirations_raw
                ]

                strikes = sorted(list(chain_data["strikes"]))

                try:
                    multiplier = int(chain_data["multiplier"])
                except (ValueError, TypeError):
                    multiplier = 100  # Default for options

                chains.append(
                    tws_pb2.OptionChainInfo(
                        exchange=chain_data["exchange"],
                        underlying_con_id=chain_data["under_con_id"],
                        trading_class=chain_data["trading_class"],
                        multiplier=multiplier,
                        expirations=expirations,
                        strikes=strikes,
                    )
                )

            logger.info(
                f"Retrieved option chain for"
                f" {request.underlying_symbol}:"
                f" {len(chains)} exchange(s)"
            )
            return tws_pb2.OptionChainResponse(chains=chains)
        except Exception as e:
            logger.error(f"GetOptionChain failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.OptionChainResponse()

    def _req_positions(self) -> list | dict[str, Any]:
        """Request current positions"""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        self.ib.events["positions"] = threading.Event()
        with self.ib.data_lock:
            self.ib.data["positions"] = []

        self.ib.reqPositions()

        completed = self.ib.events["positions"].wait(timeout=30)
        if not completed:
            del self.ib.events["positions"]
            with self.ib.data_lock:
                del self.ib.data["positions"]
            return {"code": 0, "error": "Request timeout"}

        with self.ib.data_lock:
            data = self.ib.data.get("positions", [])

        del self.ib.events["positions"]
        with self.ib.data_lock:
            del self.ib.data["positions"]

        self.ib.cancelPositions()

        return data

    def GetPositions(
        self,
        request: tws_pb2.PositionsRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.PositionsResponse:
        """Get current portfolio positions"""
        if not self._check_connection(context):
            return tws_pb2.PositionsResponse()

        try:
            data = self._req_positions()

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error getting positions: [{error_code}] {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.PositionsResponse(positions=[])

            positions = []
            for pos_data in data:
                contract = pos_data["contract"]

                # Calculate market value and unrealized P&L (simplified)
                position_qty = pos_data["position"]
                avg_cost = pos_data["avgCost"]
                # Note: We don't have current market price in this callback
                # To get accurate market_value and unrealized_pnl,
                # would need to request market data
                market_value = 0.0  # Would need current price
                unrealized_pnl = 0.0  # Would need current price

                positions.append(
                    tws_pb2.Position(
                        account=pos_data["account"],
                        con_id=contract.conId,
                        symbol=contract.symbol,
                        sec_type=contract.secType,
                        exchange=contract.exchange,
                        currency=contract.currency,
                        local_symbol=contract.localSymbol,
                        trading_class=contract.tradingClass,
                        position=position_qty,
                        avg_cost=avg_cost,
                        market_value=market_value,
                        unrealized_pnl=unrealized_pnl,
                    )
                )

            logger.info(f"Retrieved {len(positions)} position(s)")
            return tws_pb2.PositionsResponse(positions=positions)
        except Exception as e:
            logger.error(f"GetPositions failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.PositionsResponse()

    def _req_completed_orders(self, api_only: bool = False) -> list | dict[str, Any]:
        """Request completed orders"""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        self.ib.events["completed_orders"] = threading.Event()
        with self.ib.data_lock:
            self.ib.data["completed_orders"] = []

        self.ib.reqCompletedOrders(api_only)

        completed = self.ib.events["completed_orders"].wait(timeout=30)
        if not completed:
            del self.ib.events["completed_orders"]
            with self.ib.data_lock:
                del self.ib.data["completed_orders"]
            return {"code": 0, "error": "Request timeout"}

        with self.ib.data_lock:
            data = self.ib.data.get("completed_orders", [])

        del self.ib.events["completed_orders"]
        with self.ib.data_lock:
            del self.ib.data["completed_orders"]

        return data

    def GetCompletedOrders(
        self,
        request: tws_pb2.CompletedOrdersRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.CompletedOrdersResponse:
        """Get completed orders"""
        if not self._check_connection(context):
            return tws_pb2.CompletedOrdersResponse()

        try:
            data = self._req_completed_orders(api_only=request.api_only)

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(
                    f"IB API error getting completed orders: [{error_code}] {error_msg}"
                )
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.CompletedOrdersResponse(orders=[])

            orders = []
            for order_data in data:
                contract = order_data["contract"]
                order = order_data["order"]
                order_state = order_data["order_state"]

                orders.append(
                    tws_pb2.CompletedOrder(
                        # Order IDs
                        order_id=order.orderId,
                        client_id=order.clientId,
                        perm_id=order.permId,
                        # Contract info
                        con_id=contract.conId,
                        symbol=contract.symbol,
                        sec_type=contract.secType,
                        exchange=contract.exchange,
                        currency=contract.currency,
                        local_symbol=contract.localSymbol,
                        # Order details
                        action=order.action,
                        total_quantity=float(order.totalQuantity),
                        filled_quantity=float(order.filledQuantity),
                        remaining=float(order.remaining),
                        # Pricing
                        order_type=order.orderType,
                        lmt_price=order.lmtPrice,
                        aux_price=order.auxPrice,
                        avg_fill_price=order.avgFillPrice,
                        # Status
                        status=order_state.status,
                        completed_time=order_state.completedTime,
                        completed_status=order_state.completedStatus,
                        # Commission
                        commission=order_state.commissionAndFees
                        if hasattr(order_state, "commissionAndFees")
                        else 0.0,
                        commission_currency=order_state.commissionAndFeesCurrency
                        if hasattr(order_state, "commissionAndFeesCurrency")
                        else "",
                        # Metadata
                        tif=order.tif,
                        outside_rth=order.outsideRth,
                        parent_id=order.parentId,
                        order_ref=order.orderRef,
                    )
                )

            logger.info(f"Retrieved {len(orders)} completed order(s)")
            return tws_pb2.CompletedOrdersResponse(orders=orders)
        except Exception as e:
            logger.error(f"GetCompletedOrders failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.CompletedOrdersResponse()

    def _req_matching_symbols(self, pattern: str) -> list | dict[str, Any]:
        """Search for contracts matching a pattern (ticker or company name)."""
        if not self.ib.isConnected():
            return {"code": 0, "error": "Not connected to TWS"}

        if not self.pacer.acquire("general"):
            return {"code": 0, "error": "Rate limit timeout"}

        req_id = self.ib.start_request()
        self.ib.reqMatchingSymbols(req_id, pattern)

        completed = self.ib.events[req_id].wait(timeout=30)
        if not completed:
            self.ib.end_request(req_id)
            self.pacer.backoff()
            return {"code": 0, "error": "Request timeout"}

        data = self.ib.data.get(req_id, [])
        self.ib.end_request(req_id)

        return data

    def SearchSymbols(
        self,
        request: tws_pb2.SymbolSearchRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.SymbolSearchResponse:
        """Search for contracts matching a pattern (ticker or company name)."""
        if not self._check_connection(context):
            return tws_pb2.SymbolSearchResponse()

        pattern = request.pattern
        if not pattern:
            return tws_pb2.SymbolSearchResponse()

        data = self._req_matching_symbols(pattern)

        if isinstance(data, dict) and "error" in data:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"[{data.get('code', 0)}] {data['error']}")
            return tws_pb2.SymbolSearchResponse()

        matches = []
        for desc in data:
            contract = desc.contract
            matches.append(
                tws_pb2.SymbolMatch(
                    con_id=contract.conId,
                    symbol=contract.symbol,
                    sec_type=contract.secType,
                    primary_exchange=contract.primaryExchange,
                    currency=contract.currency,
                    description=contract.description or "",
                    issuer_id=contract.issuerId or "",
                    derivative_sec_types=list(desc.derivativeSecTypes),
                )
            )

        logger.info(f"Symbol search '{pattern}': {len(matches)} matches")
        return tws_pb2.SymbolSearchResponse(matches=matches)

    def GetScannerParameters(
        self,
        request: tws_pb2.ScannerParametersRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.ScannerParametersResponse:
        """Get available scanner parameters"""
        if not self._check_connection(context):
            return tws_pb2.ScannerParametersResponse()

        try:
            self.ib.events["scanner_parameters"] = threading.Event()
            self.ib.data["scanner_parameters"] = None

            self.ib.reqScannerParameters()

            completed = self.ib.events["scanner_parameters"].wait(timeout=30)
            if not completed:
                del self.ib.events["scanner_parameters"]
                del self.ib.data["scanner_parameters"]
                logger.error("Scanner parameters request timeout")
                return tws_pb2.ScannerParametersResponse(xml="")

            xml = self.ib.data.get("scanner_parameters", "")

            del self.ib.events["scanner_parameters"]
            del self.ib.data["scanner_parameters"]

            logger.info("Retrieved scanner parameters")
            return tws_pb2.ScannerParametersResponse(xml=xml)
        except Exception as e:
            logger.error(f"GetScannerParameters failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.ScannerParametersResponse()

    def RunMarketScanner(
        self,
        request: tws_pb2.MarketScannerRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.MarketScannerResponse:
        """Run a market scanner query"""
        if not self._check_connection(context):
            return tws_pb2.MarketScannerResponse()

        if not self.pacer.acquire("general"):
            context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
            context.set_details("Rate limit timeout")
            return tws_pb2.MarketScannerResponse()

        try:
            sub = ScannerSubscription()
            sub.numberOfRows = (
                request.number_of_rows if request.number_of_rows > 0 else -1
            )
            sub.instrument = request.instrument
            sub.locationCode = request.location_code
            sub.scanCode = request.scan_code

            if request.above_price > 0:
                sub.abovePrice = request.above_price
            if request.below_price > 0:
                sub.belowPrice = request.below_price
            if request.above_volume > 0:
                sub.aboveVolume = request.above_volume
            if request.market_cap_above > 0:
                sub.marketCapAbove = request.market_cap_above
            if request.market_cap_below > 0:
                sub.marketCapBelow = request.market_cap_below
            if request.stock_type_filter:
                sub.stockTypeFilter = request.stock_type_filter

            req_id = self.ib.start_request()

            self.ib.reqScannerSubscription(req_id, sub, [], [])

            completed = self.ib.events[req_id].wait(timeout=30)
            if not completed:
                self.ib.end_request(req_id)
                logger.error(f"Scanner request {req_id} timeout")
                return tws_pb2.MarketScannerResponse(results=[])

            data = self.ib.data.get(req_id, [])

            if isinstance(data, dict) and "error" in data:
                error_code = data.get("code", 0)
                error_msg = data.get("error", "")
                logger.error(f"IB API error running scanner: [{error_code}] {error_msg}")
                self.ib.end_request(req_id)
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"[{error_code}] {error_msg}")
                return tws_pb2.MarketScannerResponse(results=[])

            self.ib.cancelScannerSubscription(req_id)

            results = []
            for item in data:
                contract_details = item["contract_details"]
                contract = contract_details.contract

                results.append(
                    tws_pb2.ScanResult(
                        rank=item["rank"],
                        con_id=contract.conId,
                        symbol=contract.symbol,
                        sec_type=contract.secType,
                        primary_exchange=contract.primaryExchange,
                        currency=contract.currency,
                        local_symbol=contract.localSymbol,
                        trading_class=contract.tradingClass,
                        distance=item["distance"],
                        benchmark=item["benchmark"],
                        projection=item["projection"],
                        market_name=contract_details.marketName
                        if hasattr(contract_details, "marketName")
                        else "",
                    )
                )

            self.ib.end_request(req_id)

            logger.info(f"Scanner returned {len(results)} result(s)")
            return tws_pb2.MarketScannerResponse(results=results)
        except Exception as e:
            logger.error(f"RunMarketScanner failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.MarketScannerResponse()

    def StreamMarketData(
        self,
        request: tws_pb2.MarketDataRequest,
        context: grpc.ServicerContext,
    ) -> None:
        """Stream real-time market data (streaming RPC)"""
        # TODO: Implement streaming market data
        # This requires setting up market data subscriptions with IB
        # and yielding MarketDataTick messages as they arrive
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("StreamMarketData not yet implemented")
        return

    def _parse_watchlist_export(self, file_path: str) -> list[dict[str, str | float]]:
        """Parse TWS watchlist export CSV file.

        The export.csv file format:
        COLUMN,0
        DES,symbol,secType,exchange,expiry,strike,right,multiplier,currency

        Fields (0-indexed):
        0: DES (marker)
        1: symbol
        2: secType (STK, OPT, FUT, CASH, CRYPTO, IND)
        3: exchange (may include /primary_exchange like SMART/AMEX)
        4: expiry (YYYYMMDD for options, YYYYMM for futures)
        5: strike (for options, decimal number)
        6: right ("Call" or "Put" for options)
        7: multiplier (contract size)
        8: currency (for CASH pairs like USD, EUR, etc.)

        Args:
            file_path: Path to the export.csv file

        Returns:
            List of contract dictionaries
        """
        if not os.path.exists(file_path):
            logger.warning(f"Watchlist export file not found: {file_path}")
            return []

        contracts = []
        in_column = False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    parts = line.split(",")

                    # Check for column marker
                    if parts[0] == "COLUMN":
                        in_column = True

                    # Check for contract description
                    elif parts[0] == "DES" and in_column:
                        # Parse contract details
                        # Format: DES,symbol,secType,exchange,
                        #   expiry,strike,right,multiplier,currency
                        if len(parts) < 9:
                            logger.warning(
                                f"Invalid contract line (too few fields): {line}"
                            )
                            continue

                        symbol = parts[1]
                        sec_type = parts[2]
                        exchange_raw = parts[3]
                        expiry = parts[4] if len(parts) > 4 else ""
                        strike_str = parts[5] if len(parts) > 5 else ""
                        right = parts[6] if len(parts) > 6 else ""
                        multiplier = parts[7] if len(parts) > 7 else ""
                        currency = parts[8] if len(parts) > 8 else ""

                        # Parse strike price
                        strike = 0.0
                        if strike_str:
                            try:
                                strike = float(strike_str)
                            except ValueError:
                                strike = 0.0

                        # Split exchange/primary_exchange
                        # e.g., "SMART/AMEX" -> "SMART", "AMEX"
                        if "/" in exchange_raw:
                            exchange, primary_exchange = exchange_raw.split("/", 1)
                        else:
                            exchange = exchange_raw
                            primary_exchange = ""

                        contracts.append(
                            {
                                "symbol": symbol,
                                "sec_type": sec_type,
                                "exchange": exchange,
                                "primary_exchange": primary_exchange,
                                "expiry": expiry,
                                "strike": strike,
                                "right": right,
                                "multiplier": multiplier,
                                "currency": currency,
                            }
                        )

            logger.info(f"Parsed watchlist with {len(contracts)} contract(s)")
            return contracts

        except Exception as e:
            logger.error(f"Error parsing watchlist export: {e}")
            return []

    def GetWatchlist(
        self,
        request: tws_pb2.WatchlistRequest,
        context: grpc.ServicerContext,
    ) -> tws_pb2.WatchlistResponse:
        """Get watchlist from TWS export file"""
        try:
            # Use custom path if provided, otherwise use default from settings
            from settings import WATCHLIST_EXPORT_PATH

            export_path = (
                request.export_path if request.export_path else WATCHLIST_EXPORT_PATH
            )

            logger.info(f"Reading watchlist from: {export_path}")

            parsed_data = self._parse_watchlist_export(export_path)

            contracts = [
                tws_pb2.WatchlistContract(
                    symbol=c["symbol"],
                    sec_type=c["sec_type"],
                    exchange=c["exchange"],
                    primary_exchange=c["primary_exchange"],
                    expiry=c["expiry"],
                    strike=c["strike"],
                    right=c["right"],
                    multiplier=c["multiplier"],
                    currency=c["currency"],
                )
                for c in parsed_data
            ]

            logger.info(f"Returning watchlist with {len(contracts)} contract(s)")
            return tws_pb2.WatchlistResponse(contracts=contracts)

        except Exception as e:
            logger.error(f"GetWatchlist failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return tws_pb2.WatchlistResponse()


def serve() -> None:
    """Start the gRPC server"""
    host = os.getenv("GRPC_HOST")
    port = int(os.getenv("GRPC_PORT"))
    max_workers = int(os.getenv("GRPC_MAX_WORKERS"))

    from settings import (
        PACING_CONTRACT_MAX,
        PACING_CONTRACT_WINDOW,
        PACING_GENERAL_INTERVAL,
        PACING_HIST_MAX,
        PACING_HIST_WINDOW,
        PACING_IDENTICAL_GAP,
    )

    pacer = IBPacer(
        historical_max_requests=PACING_HIST_MAX,
        historical_window_seconds=PACING_HIST_WINDOW,
        identical_gap_seconds=PACING_IDENTICAL_GAP,
        general_min_interval_seconds=PACING_GENERAL_INTERVAL,
        contract_max_requests=PACING_CONTRACT_MAX,
        contract_window_seconds=PACING_CONTRACT_WINDOW,
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))

    servicer = IBServicer(IB, pacer)
    tws_pb2_grpc.add_TWSAgentServicer_to_server(servicer, server)

    server.add_insecure_port(f"{host}:{port}")
    server.start()

    logger.info(f"gRPC server listening on {host}:{port}")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server...")

        if servicer.ib.isConnected():
            logger.info("Disconnecting from TWS...")
            servicer.ib.disconnect()

        event = server.stop(0)
        event.wait(timeout=2)

        logger.info("Shutdown complete")

        sys.exit(0)
