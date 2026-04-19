"""
Tests for Wall Street Horizon corporate events
"""

import json

import grpc
import pytest
import tws_pb2


def test_get_wsh_metadata(grpc_stub, tws_session):
    """Test getting WSH metadata (available event types)"""

    try:
        response = grpc_stub.GetWshMetaData(tws_pb2.WshMetaDataRequest())
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    assert isinstance(response.json_data, str)

    if not response.json_data:
        pytest.skip("WSH metadata not available - requires subscription (error 10276)")

    try:
        data = json.loads(response.json_data)
        assert isinstance(data, (dict, list))
    except json.JSONDecodeError:
        pytest.skip("Response is not valid JSON - WSH may not be available")


def test_get_wsh_event_data_aapl(grpc_stub, tws_session):
    """Test getting WSH event data for AAPL"""

    contract_response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )

    if not contract_response.contracts:
        pytest.skip("Could not find AAPL contract")

    con_id = contract_response.contracts[0].con_id

    try:
        response = grpc_stub.GetWshEventData(
            tws_pb2.WshEventDataRequest(
                con_id=con_id,
                filter="",  # Get all event types
                fill_watchlist=False,
                fill_portfolio=False,
                fill_competitors=False,
                start_date="",
                end_date="",
                total_limit=10,  # Limit to 10 events for testing
            )
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    assert isinstance(response.json_data, str)

    if response.json_data:
        try:
            data = json.loads(response.json_data)
            assert isinstance(data, (dict, list))
        except json.JSONDecodeError:
            pytest.skip("Response is not valid JSON - WSH may not be available")


def test_get_wsh_event_data_with_filter(grpc_stub, tws_session):
    """Test getting WSH event data with a specific filter"""

    contract_response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )

    if not contract_response.contracts:
        pytest.skip("Could not find AAPL contract")

    con_id = contract_response.contracts[0].con_id

    try:
        response = grpc_stub.GetWshEventData(
            tws_pb2.WshEventDataRequest(
                con_id=con_id,
                filter="Earnings",
                fill_watchlist=False,
                fill_portfolio=False,
                fill_competitors=False,
                start_date="",
                end_date="",
                total_limit=5,
            )
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    assert isinstance(response.json_data, str)


def test_get_wsh_event_data_with_date_range(grpc_stub, tws_session):
    """Test getting WSH event data with a specific date range"""

    contract_response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )

    if not contract_response.contracts:
        pytest.skip("Could not find AAPL contract")

    con_id = contract_response.contracts[0].con_id

    # Get events for a specific date range
    try:
        response = grpc_stub.GetWshEventData(
            tws_pb2.WshEventDataRequest(
                con_id=con_id,
                filter="",
                fill_watchlist=False,
                fill_portfolio=False,
                fill_competitors=False,
                start_date="20240101",
                end_date="20241231",
                total_limit=10,
            )
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    assert isinstance(response.json_data, str)


def test_get_wsh_event_data_invalid_contract(grpc_stub, tws_session):
    """Test getting WSH event data for an invalid contract ID"""

    try:
        response = grpc_stub.GetWshEventData(
            tws_pb2.WshEventDataRequest(
                con_id=999999999,  # Invalid contract ID
                filter="",
                fill_watchlist=False,
                fill_portfolio=False,
                fill_competitors=False,
                start_date="",
                end_date="",
                total_limit=0,
            )
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            # Expected - IB returns error for invalid contracts
            return
        raise

    assert isinstance(response.json_data, str)
