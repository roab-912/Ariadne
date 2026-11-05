import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import app, get_provider
from connectors.ethereum import EthereumSettings
from investigation.db import get_session
from investigation.demo import seed_demo
from investigation.models import Observation, Operation, RunBundle, SourceSnapshot, TransactionBundle, Asset
from tests.ethereum_helpers import fixture, replay_provider

pytestmark = pytest.mark.postgres


@pytest.fixture
def live_client(db):
    provider = replay_provider()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_provider] = lambda: provider
    with TestClient(app) as client:
        yield client, provider
    app.dependency_overrides.clear()
    provider.close()


def make_case(client, name="native", *, seeds=None):
    seed = {"chain_id": "eip155:1", "kind": "transaction", "reference": fixture(name)["transaction_hash"]}
    response = client.post("/api/v1/cases", json={"title": "Test de rejeu public", "seeds": seeds or [seed]})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def collect(client, case_id, key="test-key", body=None):
    return client.post(f"/api/v1/cases/{case_id}/runs", headers={"Idempotency-Key": key}, json=body or {})


@pytest.mark.parametrize("name,count,status", [("native", 1, 1), ("erc20", 4, 1), ("failed", 0, 0)])
def test_public_snapshots_through_api_and_postgres(db, live_client, name, count, status):
    client, provider = live_client
    seed_demo(db)
    case_id = make_case(client, name)
    response = collect(client, case_id)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["is_demo"] is False and run["state"] == "completed"
    assert run["coverage_status"] == "complete_within_declared_scope"
    assert run["parameters"]["provider_calls"] > 0
    assert run["allocation_policy"] == "none" and run["label_snapshot"] == []
    operations = client.get(f'/api/v1/runs/{run["id"]}/operations').json()
    assert len(operations) == count
    bundles = client.get(f'/api/v1/runs/{run["id"]}/transactions').json()
    assert len(bundles) == 1 and bundles[0]["transaction_status"] == status
    for operation in operations:
        observation = operation["movements"][0]["observation"]
        assert not observation["is_demo"] and observation["bundle_id"] == bundles[0]["id"]
        assert observation["canonicality"] == "canonical" and observation["finality"]["status"] == "finalized"
    if name == "native":
        assert operations[0]["movements"][0]["observation"]["amount_raw"] == "13230000000000000"
    if name == "erc20":
        assert all(item["movements"][0]["observation"]["asset"]["decimals"] is None for item in operations)
        asset = db.get(Asset, operations[0]["movements"][0]["observation"]["asset_id"])
        asset.decimals = 12
        db.commit()
        assert client.get(f'/api/v1/runs/{run["id"]}/operations').json()[0]["movements"][0]["observation"]["asset"]["decimals"] is None
    for manifest in run["manifest"]:
        piece = client.get(f'/api/v1/snapshots/{manifest["snapshot_id"]}').json()
        digest = hashlib.sha256(json.dumps(piece["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert digest == manifest["sha256"] and piece["is_demo"] is False
    # La démonstration ne reçoit ni pièce réelle ni nouvel état de run.
    demo_case = client.get('/api/v1/cases').json()[0]
    assert demo_case["is_demo"] and len(client.get(f'/api/v1/cases/{demo_case["id"]}').json()["runs"]) == 1


def test_idempotence_and_new_run_do_not_duplicate_observations(db, live_client):
    client, provider = live_client
    seed_demo(db)
    identity = make_case(client)
    first = collect(client, identity).json()
    calls = provider.http.budget.calls
    assert collect(client, identity).json()["id"] == first["id"]
    assert provider.http.budget.calls == calls
    assert collect(client, identity, body={"max_transactions": 1}).status_code == 409
    second = collect(client, identity, key="new-key").json()
    assert second["id"] != first["id"]
    assert db.scalar(select(func.count()).select_from(Observation)) == 4
    assert db.scalar(select(func.count()).select_from(Operation)) == 4
    assert db.scalar(select(func.count()).select_from(TransactionBundle)) == 1
    assert db.scalar(select(func.count()).select_from(RunBundle)) == 2
    original_id = client.get(f'/api/v1/runs/{first["id"]}/operations').json()[0]["movements"][0]["observation"]["snapshot_id"]
    assert original_id in [item["snapshot_id"] for item in second["manifest"]]


@pytest.mark.parametrize("rate_limit", [False, True])
def test_address_history_keeps_verified_prefix_on_pagination_failure(db, live_client, rate_limit):
    client, initial = live_client
    captured = fixture("native")
    tx = captured["bundle"]["transaction"]
    number = int(tx["blockNumber"], 16)
    seen = []
    def index(request):
        params = request.url.params
        seen.append((params["action"], params["page"]))
        if params["action"] == "txlist" and params["page"] == "1":
            row = {"hash": tx["hash"], "blockNumber": str(number), "from": tx["from"], "to": tx["to"], "value": "999999999999999999999"}
            rows = [row, dict(row)]
        elif rate_limit and params["page"] == "2":
            return httpx.Response(429)
        else:
            rows = []
        return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})
    provider = replay_provider(index_handler=index, settings=EthereumSettings(rpc_url="https://rpc.test", etherscan_api_key="SECRET_KEY_DO_NOT_EXPOSE", page_size=2, index_interval=0))
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        seed_demo(db)
        identity = make_case(client, seeds=[{"chain_id": "eip155:1", "kind": "address", "reference": tx["from"],
            "window": {"start_block": str(number), "end_block": str(number)}}])
        response = collect(client, identity)
        assert response.status_code == 201, response.text
        run = response.json()
        assert run["coverage_status"] == ("partial" if rate_limit else "complete_within_declared_scope")
        assert ("provider_rate_limited" in run["stop_reasons"]) is rate_limit
        operations = client.get(f'/api/v1/runs/{run["id"]}/operations').json()
        assert len(operations) == 1 and operations[0]["movements"][0]["observation"]["amount_raw"] == "13230000000000000"
        assert run["coverage"]["discovery"][0]["pages"] == 2
        assert seen[:2] == [("txlist", "1"), ("txlist", "2")]
        for item in run["manifest"]:
            assert "SECRET_KEY_DO_NOT_EXPOSE" not in client.get(f'/api/v1/snapshots/{item["snapshot_id"]}').text
    finally:
        provider.close()


def test_receipt_missing_and_unknown_transaction_are_explicit(db, live_client):
    client, initial = live_client
    def missing_receipt(body):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": None}) if body["method"] == "eth_getTransactionReceipt" else None
    provider = replay_provider(rpc_handler=missing_receipt)
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        seed_demo(db)
        identity = make_case(client)
        run = collect(client, identity).json()
        assert run["coverage_status"] == "partial" and "receipt_unavailable" in run["stop_reasons"]
        assert db.scalar(select(func.count()).select_from(TransactionBundle)) == 0
        assert client.get(f'/api/v1/runs/{run["id"]}/operations').json() == []
        unknown = make_case(client, seeds=[{"chain_id": "eip155:1", "kind": "transaction", "reference": "0x" + "00" * 32}])
        assert collect(client, unknown, key="unknown").json()["coverage_status"] == "unknown"
    finally:
        provider.close()


def test_transaction_limit_is_visible_without_false_completeness(db, live_client):
    client, provider = live_client
    seed_demo(db)
    identity = make_case(client, seeds=[{"chain_id": "eip155:1", "kind": "transaction", "reference": fixture(name)["transaction_hash"]} for name in ("native", "erc20")])
    run = collect(client, identity, body={"max_transactions": 1}).json()
    assert run["coverage_status"] == "partial" and "transaction_limit_reached" in run["stop_reasons"]
    assert run["parameters"]["collected_transactions"] == 1


def test_empty_address_history_is_complete_only_inside_declared_scope(db, live_client):
    client, provider = live_client
    seed_demo(db)
    number = fixture("expected")["block_number"]
    seed = {"chain_id": "eip155:1", "kind": "address", "reference": "0x" + "11" * 20,
            "window": {"start_block": number, "end_block": number}}
    identity = make_case(client, seeds=[seed])
    run = collect(client, identity).json()
    assert run["coverage_status"] == "complete_within_declared_scope"
    assert run["coverage"]["verified_transaction_count"] == 0
    assert run["coverage"]["discovery"][0]["finished"] is True
    assert client.get(f'/api/v1/runs/{run["id"]}/transactions').json() == []
    assert collect(client, identity, key="changed-bounds", body={"block_range": {"start": 1, "end": 2}}).status_code == 422
