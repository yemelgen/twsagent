"""
Tests for portfolio positions retrieval
"""

import pytest
import tws_pb2


def test_get_positions(grpc_stub, tws_session):
    """Test getting current positions"""

    response = grpc_stub.GetPositions(tws_pb2.PositionsRequest())

    assert isinstance(response.positions, list) or hasattr(response, "positions")

    if len(response.positions) > 0:
        pos = response.positions[0]

        assert pos.account
        assert pos.con_id > 0
        assert pos.symbol
        assert pos.sec_type
        assert pos.currency
        assert isinstance(pos.position, float)
        assert isinstance(pos.avg_cost, float)


def test_get_positions_structure(grpc_stub, tws_session):
    """Test that positions response has correct structure"""

    response = grpc_stub.GetPositions(tws_pb2.PositionsRequest())

    assert response is not None
    assert hasattr(response, "positions")

    positions_list = list(response.positions)
    assert isinstance(positions_list, list)


def test_get_positions_fields(grpc_stub, tws_session):
    """Test that position fields are accessible"""

    response = grpc_stub.GetPositions(tws_pb2.PositionsRequest())

    if len(response.positions) == 0:
        pytest.skip("No positions in account")

    pos = response.positions[0]

    # All fields should be accessible (even if some are empty/zero)
    _ = pos.account
    _ = pos.con_id
    _ = pos.symbol
    _ = pos.sec_type
    _ = pos.exchange
    _ = pos.currency
    _ = pos.local_symbol
    _ = pos.trading_class
    _ = pos.position
    _ = pos.avg_cost
    _ = pos.market_value
    _ = pos.unrealized_pnl
