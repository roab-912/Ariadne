from decimal import Decimal
import pytest
from pydantic import BaseModel, ValidationError

from investigation.domain import AddressId, UINT256_MAX, asset_id, parse_amount, uint256
from investigation.models import UInt256
from investigation.schemas import Amount, SeedInput


def test_chain_is_part_of_address_and_asset_identity():
    value = "0x" + "AB" * 20
    ethereum = AddressId.evm("eip155:1", value)
    base = AddressId.evm("eip155:8453", value)
    assert ethereum.value == base.value
    assert ethereum.key != base.key
    assert ethereum.key == AddressId.evm("eip155:1", value.lower()).key
    assert ethereum.display == value
    assert asset_id("eip155:1", value) != asset_id("eip155:8453", value)
    assert asset_id("eip155:1") != asset_id("eip155:1", value)


@pytest.mark.parametrize("bad", [-1, UINT256_MAX + 1, 1.0, True, "1"])
def test_rejects_lossy_or_out_of_range_amounts(bad):
    with pytest.raises(ValueError):
        uint256(bad)


@pytest.mark.parametrize("bad", ["-1", "1.0", "1e18", "01", " 1", str(UINT256_MAX + 1), 1, 1.0, True])
def test_api_requires_decimal_strings(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


def test_amount_roundtrip_without_float_at_boundaries():
    class Payload(BaseModel):
        amount_raw: Amount
    for value in [0, 2**53 + 1, 10**18 + 1, UINT256_MAX]:
        payload = Payload(amount_raw=str(value))
        assert payload.amount_raw == value
        assert payload.model_dump(mode="json") == {"amount_raw": str(value)}
        storage = UInt256()
        decimal = storage.process_bind_param(value, None)
        assert isinstance(decimal, Decimal)
        assert storage.process_result_value(decimal, None) == value


def test_address_seed_requires_explicit_ordered_window():
    seed = {"chain_id": "eip155:1", "kind": "address", "reference": "0x" + "11" * 20}
    with pytest.raises(ValidationError):
        SeedInput(**seed)
    value = SeedInput(**seed, window={"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"})
    assert value.reference.startswith("eip155:1:")
    with pytest.raises(ValidationError):
        SeedInput(**seed, window={"start": "2026-01-02", "end": "2026-01-01"})
