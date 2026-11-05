import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from connectors.contracts import BlockRange, ProviderResult, UnavailableProvider
from investigation.domain import CoverageStatus


def test_unavailable_provider_never_claims_empty_complete_history():
    provider = UnavailableProvider()
    scope = BlockRange(start=100, end=200)
    results = [
        provider.discover_address_activity("eip155:1:0x" + "11" * 20, scope, "next"),
        provider.get_transaction_bundle("eip155:1", "0x" + "aa" * 32),
        provider.get_logs("eip155:1", {}),
        provider.get_chain_head_and_finality("eip155:1"),
    ]
    for result in results:
        assert result.status == CoverageStatus.UNSUPPORTED
        assert result.data is None
        assert result.covered_range is None
        assert result.limits
        assert result.retrieved_at.tzinfo
    assert results[0].requested_range == scope
    assert results[0].cursor == "next"
    complete = ProviderResult(data=[], source="fixture-test", retrieved_at=results[0].retrieved_at, chain_id="eip155:1", status=CoverageStatus.COMPLETE, covered_range=scope)
    assert complete.data == [] and complete.status != results[0].status


def test_invalid_block_range():
    with pytest.raises(ValidationError):
        BlockRange(start=2, end=1)


def test_capabilities_no_network_is_claimed_supported():
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert len(response.json()["providers"]) == 3
    assert all(item["status"] == "unsupported" and not item["transaction_bundle"] and not item["protocols"] for item in response.json()["providers"])


def test_openapi_amount_is_string():
    schema = app.openapi()["components"]["schemas"]["ObservationView"]
    assert schema["properties"]["amount_raw"]["type"] == "string"
