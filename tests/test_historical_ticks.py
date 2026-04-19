from datetime import datetime, timedelta

import grpc
import pytest
import tws_pb2


def get_recent_trading_datetime():
    """Get a recent datetime that's likely during trading hours"""

    now = datetime.now()
    for days_back in range(1, 6):
        past_date = now - timedelta(days=days_back)
        if past_date.weekday() < 5:
            return past_date.strftime("%Y%m%d 14:00:00 US/Eastern")
    return (now - timedelta(days=5)).strftime("%Y%m%d 14:00:00 US/Eastern")


@pytest.fixture
def aapl_contract_id(grpc_stub, tws_session):
    """Get AAPL contract ID for testing"""

    response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )
    if len(response.contracts) == 0:
        pytest.skip(
            "Unable to retrieve AAPL contract details."
            " TWS may not be connected or data"
            " unavailable."
        )
    return response.contracts[0].con_id


def test_get_historical_ticks_trades(grpc_stub, aapl_contract_id, tws_session):
    """Test getting historical TRADES tick data"""

    start_date = get_recent_trading_datetime()

    response = grpc_stub.GetHistoricalTicks(
        tws_pb2.HistoricalTicksRequest(
            con_id=aapl_contract_id,
            start_date_time=start_date,
            end_date_time="",
            number_of_ticks=10,
            what_to_show="TRADES",
            use_rth=True,
            ignore_size=True,
        )
    )

    # Should have ticks_last populated for TRADES
    assert len(response.ticks_last) > 0, "Expected TRADES ticks but got none"

    # Verify tick structure
    tick = response.ticks_last[0]
    assert tick.time > 0, "Tick time should be a valid Unix timestamp"
    assert tick.price > 0, "Tick price should be positive"
    assert tick.size >= 0, "Tick size should be non-negative"
    assert isinstance(tick.exchange, str), "Exchange should be a string"

    # Verify ticks are in chronological order
    for i in range(1, len(response.ticks_last)):
        assert response.ticks_last[i].time >= response.ticks_last[i - 1].time, (
            "Ticks should be in chronological order"
        )


def test_get_historical_ticks_bid_ask(grpc_stub, aapl_contract_id, tws_session):
    """Test getting historical BID_ASK tick data"""

    start_date = get_recent_trading_datetime()

    try:
        response = grpc_stub.GetHistoricalTicks(
            tws_pb2.HistoricalTicksRequest(
                con_id=aapl_contract_id,
                start_date_time=start_date,
                end_date_time="",
                number_of_ticks=10,
                what_to_show="BID_ASK",
                use_rth=True,
                ignore_size=False,
            )
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    # BID_ASK data may not always be available, so make this more lenient
    # Just verify the response structure is correct
    if len(response.ticks_bid_ask) == 0:
        pytest.skip("BID_ASK tick data not available for this time period")

    assert len(response.ticks_bid_ask) > 0

    # Verify tick structure
    tick = response.ticks_bid_ask[0]
    assert tick.time > 0, "Tick time should be a valid Unix timestamp"
    assert tick.price_bid > 0, "Bid price should be positive"
    assert tick.price_ask > 0, "Ask price should be positive"
    assert tick.size_bid >= 0, "Bid size should be non-negative"
    assert tick.size_ask >= 0, "Ask size should be non-negative"

    # Verify bid-ask spread is non-negative
    assert tick.price_ask >= tick.price_bid, (
        f"Ask price ({tick.price_ask}) should be >= Bid price ({tick.price_bid})"
    )

    # Verify ticks are in chronological order
    for i in range(1, len(response.ticks_bid_ask)):
        assert response.ticks_bid_ask[i].time >= response.ticks_bid_ask[i - 1].time, (
            "Ticks should be in chronological order"
        )


def test_get_historical_ticks_midpoint(grpc_stub, aapl_contract_id, tws_session):
    """Test getting historical MIDPOINT tick data"""

    start_date = get_recent_trading_datetime()

    try:
        response = grpc_stub.GetHistoricalTicks(
            tws_pb2.HistoricalTicksRequest(
                con_id=aapl_contract_id,
                start_date_time=start_date,
                end_date_time="",
                number_of_ticks=10,
                what_to_show="MIDPOINT",
                use_rth=True,
                ignore_size=True,
            )
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.INTERNAL:
            pytest.skip(f"IB API error: {e.details()}")
        raise

    # MIDPOINT data may not always be available, so make this more lenient
    if len(response.ticks_midpoint) == 0:
        pytest.skip("MIDPOINT tick data not available for this time period")

    assert len(response.ticks_midpoint) > 0

    # Verify tick structure
    tick = response.ticks_midpoint[0]
    assert tick.time > 0, "Tick time should be a valid Unix timestamp"
    assert tick.price > 0, "Midpoint price should be positive"

    # Verify ticks are in chronological order
    for i in range(1, len(response.ticks_midpoint)):
        assert response.ticks_midpoint[i].time >= response.ticks_midpoint[i - 1].time, (
            "Ticks should be in chronological order"
        )


def test_get_historical_ticks_with_end_date(grpc_stub, aapl_contract_id, tws_session):
    """Test historical ticks using end_date_time."""

    end_date = get_recent_trading_datetime()

    response = grpc_stub.GetHistoricalTicks(
        tws_pb2.HistoricalTicksRequest(
            con_id=aapl_contract_id,
            start_date_time="",
            end_date_time=end_date,
            number_of_ticks=10,
            what_to_show="TRADES",
            use_rth=False,  # Include after hours
            ignore_size=True,
        )
    )

    assert hasattr(response, "ticks_last")
    assert len(response.ticks_last) > 0


def test_get_historical_ticks_max_limit(grpc_stub, aapl_contract_id, tws_session):
    """Test requesting maximum number of ticks (1000)"""

    start_date = get_recent_trading_datetime()

    response = grpc_stub.GetHistoricalTicks(
        tws_pb2.HistoricalTicksRequest(
            con_id=aapl_contract_id,
            start_date_time=start_date,
            end_date_time="",
            number_of_ticks=1000,
            what_to_show="TRADES",
            use_rth=True,
            ignore_size=True,
        )
    )

    if len(response.ticks_last) > 0:
        assert len(response.ticks_last) <= 1500, (
            f"Should not exceed ~1000 ticks, got {len(response.ticks_last)}"
        )


def test_get_historical_ticks_rth_vs_all_hours(grpc_stub, aapl_contract_id, tws_session):
    """Test comparing regular trading hours vs all hours"""

    start_date = get_recent_trading_datetime()

    response_rth = grpc_stub.GetHistoricalTicks(
        tws_pb2.HistoricalTicksRequest(
            con_id=aapl_contract_id,
            start_date_time=start_date,
            end_date_time="",
            number_of_ticks=100,
            what_to_show="TRADES",
            use_rth=True,
            ignore_size=True,
        )
    )

    response_all = grpc_stub.GetHistoricalTicks(
        tws_pb2.HistoricalTicksRequest(
            con_id=aapl_contract_id,
            start_date_time=start_date,
            end_date_time="",
            number_of_ticks=100,
            what_to_show="TRADES",
            use_rth=False,
            ignore_size=True,
        )
    )

    assert hasattr(response_rth, "ticks_last")
    assert hasattr(response_all, "ticks_last")
    assert len(response_rth.ticks_last) > 0
    assert len(response_all.ticks_last) > 0


def test_get_historical_ticks_invalid_contract(grpc_stub, tws_session):
    """Test requesting ticks for an invalid contract ID"""

    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_stub.GetHistoricalTicks(
            tws_pb2.HistoricalTicksRequest(
                con_id=999999999,  # Invalid contract ID
                start_date_time=get_recent_trading_datetime(),
                end_date_time="",
                number_of_ticks=10,
                what_to_show="TRADES",
                use_rth=True,
                ignore_size=True,
            )
        )

    assert exc_info.value.code() == grpc.StatusCode.INTERNAL


def test_historical_ticks_data_quality(grpc_stub, aapl_contract_id, tws_session):
    """Test data quality of historical ticks"""

    start_date = get_recent_trading_datetime()

    response = grpc_stub.GetHistoricalTicks(
        tws_pb2.HistoricalTicksRequest(
            con_id=aapl_contract_id,
            start_date_time=start_date,
            end_date_time="",
            number_of_ticks=50,
            what_to_show="TRADES",
            use_rth=True,
            ignore_size=True,
        )
    )

    assert len(response.ticks_last) > 0

    # Check data quality
    prices = [tick.price for tick in response.ticks_last]
    sizes = [tick.size for tick in response.ticks_last]

    assert all(p > 0 for p in prices), "All prices should be positive"
    assert all(s >= 0 for s in sizes), "All sizes should be non-negative"

    price_min = min(prices)
    price_max = max(prices)
    price_range = price_max - price_min
    price_avg = sum(prices) / len(prices)

    assert price_range < price_avg * 0.2, (
        f"Price range ({price_range}) seems too large compared to average ({price_avg})"
    )
