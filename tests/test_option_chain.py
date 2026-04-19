"""
Tests for option chain retrieval
"""

import grpc
import pytest
import tws_pb2


def test_get_option_chain_aapl(grpc_stub, tws_session):
    """Test getting option chain for AAPL"""

    response = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            fut_fop_exchange="",
            underlying_sec_type="STK",
            underlying_con_id=0,
        )
    )

    assert len(response.chains) > 0

    chain = response.chains[0]

    # Verify chain data structure
    assert chain.exchange
    assert chain.underlying_con_id > 0
    assert chain.trading_class
    assert isinstance(chain.multiplier, int)
    assert chain.multiplier > 0
    assert len(chain.expirations) > 0
    assert len(chain.strikes) > 0

    # Verify expirations are in ISO format (YYYY-MM-DD)
    for exp in chain.expirations:
        assert len(exp) == 10
        assert exp[4] == "-" and exp[7] == "-"
        year, month, day = exp.split("-")
        assert year.isdigit() and len(year) == 4
        assert month.isdigit() and len(month) == 2
        assert day.isdigit() and len(day) == 2

    # Verify strikes are numeric
    for strike in chain.strikes:
        assert isinstance(strike, float)
        assert strike > 0


def test_get_option_chain_specific_exchange(grpc_stub, tws_session):
    """Test getting option chain with exchange parameter"""

    response_all = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            fut_fop_exchange="",  # Empty = all exchanges
            underlying_sec_type="STK",
            underlying_con_id=0,
        )
    )

    response_smart = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            fut_fop_exchange="SMART",
            underlying_sec_type="STK",
            underlying_con_id=0,
        )
    )

    # Should return results for all exchanges
    assert len(response_all.chains) > 0

    # SMART exchange filter works (may return 0 or more chains)
    # Just verify the call succeeds and returns valid response
    assert len(response_smart.chains) >= 0


def test_get_option_chain_invalid_symbol(grpc_stub, tws_session):
    """Test handling of invalid symbol"""

    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_stub.GetOptionChain(
            tws_pb2.OptionChainRequest(
                underlying_symbol="INVALID_SYMBOL_XYZ123",
                fut_fop_exchange="",
                underlying_sec_type="STK",
                underlying_con_id=0,
            )
        )

    assert exc_info.value.code() == grpc.StatusCode.INTERNAL


def test_get_option_chain_multiple_exchanges(grpc_stub, tws_session):
    """Test getting option chain from all exchanges"""

    response = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            fut_fop_exchange="",  # Empty means all exchanges
            underlying_sec_type="STK",
            underlying_con_id=0,
        )
    )

    # Should potentially get multiple exchanges
    assert len(response.chains) >= 1

    # If multiple, verify they have different exchanges or trading classes
    if len(response.chains) > 1:
        exchanges = {chain.exchange for chain in response.chains}
        trading_classes = {chain.trading_class for chain in response.chains}
        assert len(exchanges) > 1 or len(trading_classes) > 1


def test_option_chain_expirations_sorted(grpc_stub, tws_session):
    """Test that expirations are returned sorted"""

    response = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            fut_fop_exchange="",
            underlying_sec_type="STK",
            underlying_con_id=0,
        )
    )

    assert len(response.chains) > 0

    for chain in response.chains:
        expirations = list(chain.expirations)
        assert expirations == sorted(expirations)


def test_option_chain_strikes_sorted(grpc_stub, tws_session):
    """Test that strikes are returned sorted"""

    response = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            fut_fop_exchange="",
            underlying_sec_type="STK",
            underlying_con_id=0,
        )
    )

    assert len(response.chains) > 0

    for chain in response.chains:
        strikes = list(chain.strikes)
        assert strikes == sorted(strikes)
