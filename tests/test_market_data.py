import pytest
import tws_pb2


@pytest.mark.skip(reason="Streaming not yet implemented")
def test_stream_market_data(grpc_stub, tws_session):
    """Test streaming market data"""

    contract_response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )

    con_id = contract_response.contracts[0].con_id

    stream = grpc_stub.StreamMarketData(
        tws_pb2.MarketDataRequest(
            con_id=con_id, tick_types=["BID", "ASK", "LAST"], snapshot=False
        )
    )

    ticks = []
    for tick in stream:
        ticks.append(tick)
        if len(ticks) >= 5:
            break

    assert len(ticks) > 0
    assert ticks[0].con_id == con_id
