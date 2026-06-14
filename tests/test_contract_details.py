import grpc
import pytest
import tws_pb2


def test_get_contract_details_stock(grpc_stub, tws_session):
    """Test getting contract details for a stock"""

    response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )

    assert len(response.contracts) > 0

    contract = response.contracts[0]
    assert contract.symbol == "AAPL"
    assert contract.sec_type == "STK"
    assert contract.currency == "USD"
    assert contract.con_id > 0


def test_get_contract_details_multiple_exchanges(grpc_stub, tws_session):
    """Test getting contracts from different exchanges"""

    response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL",
            sec_type="STK",
            exchange="",  # Empty means all exchanges
            currency="USD",
        )
    )

    # Should get multiple exchange listings
    assert len(response.contracts) >= 1


def test_get_contract_details_option_identity(grpc_stub, tws_session):
    """Test resolving a specific option contract by expiry/strike/right."""

    stock_response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD"
        )
    )
    assert stock_response.contracts

    chain_response = grpc_stub.GetOptionChain(
        tws_pb2.OptionChainRequest(
            underlying_symbol="AAPL",
            underlying_sec_type="STK",
            underlying_con_id=stock_response.contracts[0].con_id,
        )
    )
    assert chain_response.chains

    chain = chain_response.chains[0]
    expiry = sorted(chain.expirations)[0].replace("-", "")
    strikes = sorted(chain.strikes)
    strike = strikes[len(strikes) // 2]

    response = grpc_stub.GetContractDetails(
        tws_pb2.ContractDetailsRequest(
            symbol="AAPL",
            sec_type="OPT",
            exchange=chain.exchange or "SMART",
            currency="USD",
            expiry=expiry,
            strike=strike,
            right="Call",
            multiplier=str(chain.multiplier or 100),
        )
    )

    assert len(response.contracts) == 1
    contract = response.contracts[0]
    assert contract.symbol == "AAPL"
    assert contract.sec_type == "OPT"
    assert contract.expiry == expiry
    assert contract.strike == strike
    assert contract.right == "C"
    assert contract.multiplier == str(chain.multiplier or 100)
    assert contract.con_id > 0


def test_get_contract_details_invalid_symbol(grpc_stub, tws_session):
    """Test handling of invalid symbol"""

    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_stub.GetContractDetails(
            tws_pb2.ContractDetailsRequest(
                symbol="INVALID_SYMBOL_XYZ123",
                sec_type="STK",
                exchange="SMART",
                currency="USD",
            )
        )

    assert exc_info.value.code() == grpc.StatusCode.INTERNAL
