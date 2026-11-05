import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from apps.api.main import app
from investigation.db import get_session
from investigation.demo import demo_id, seed_demo
from investigation.domain import UINT256_MAX
from investigation.models import (
    Address, Allocation, AnalysisRun, Asset, Case, LabelAssertion, Observation,
    Operation, OperationMovement, SourceSnapshot,
)

pytestmark = pytest.mark.postgres


@pytest.fixture
def client(db):
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_seed_replay_and_separation(db, client):
    assert seed_demo(db) == seed_demo(db)
    assert db.scalar(select(func.count()).select_from(Case)) == 1
    assert db.scalar(select(func.count()).select_from(Observation)) == 3
    assert db.scalar(select(func.count()).select_from(Operation)) == 3
    assert db.scalar(select(func.count()).select_from(LabelAssertion)) == 0
    assert db.scalar(select(func.count()).select_from(Allocation)) == 0
    snapshot = db.get(SourceSnapshot, demo_id("snapshot"))
    digest = hashlib.sha256(json.dumps(snapshot.content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    run = db.get(AnalysisRun, demo_id("run"))
    assert digest == snapshot.sha256 == run.manifest[0]["sha256"]
    cases = client.get("/api/v1/cases").json()
    assert cases[0]["is_demo"] is True
    detail = client.get(f'/api/v1/cases/{cases[0]["id"]}').json()
    assert detail["runs"][0]["coverage_status"] == "partial"
    response = client.get(f'/api/v1/runs/{run.id}/operations')
    assert response.status_code == 200
    movements = [item["movements"][0]["observation"] for item in response.json()]
    assert sorted(item["amount_raw"] for item in movements) == sorted(["1000000000000000001", "600000000000000000", "400000000000000001"])
    assert all(item["is_demo"] and item["finality"]["status"] == "unknown" for item in movements)
    assert client.get(f'/api/v1/snapshots/{snapshot.id}').json()["is_demo"] is True
    assert client.get('/api/v1/operations/missing').status_code == 404
    assert client.post(f'/api/v1/cases/{cases[0]["id"]}/runs', headers={"Idempotency-Key": "test"}).status_code == 409


def test_readiness_checks_postgres_migration_and_redis(db, client):
    import os
    if not os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL nécessaire pour vérifier la disponibilité complète")
    response = client.get('/health/ready')
    assert response.status_code == 200
    assert response.json()["checks"] == {"postgres": True, "redis": True, "migration": True}


@pytest.mark.parametrize("value", [0, 2**53 + 1, 10**18 + 1, UINT256_MAX])
def test_postgres_and_api_uint256_roundtrip(db, client, value):
    seed_demo(db)
    observation = db.get(Observation, demo_id("movement-0"))
    observation.amount_raw = value
    db.commit()
    db.expire_all()
    assert db.get(Observation, observation.id).amount_raw == value
    assert client.get(f'/api/v1/observations/{observation.id}').json()["amount_raw"] == str(value)


@pytest.mark.parametrize("value", [-1, UINT256_MAX + 1])
def test_database_check_cannot_be_bypassed(db, value):
    seed_demo(db)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE observations SET amount_raw = :amount"), {"amount": value})


def test_cross_chain_foreign_keys_and_orphan_history(db):
    seed_demo(db)
    original = db.get(Observation, demo_id("movement-0"))
    values = {column.name: deepcopy(getattr(original, column.name)) for column in original.__table__.columns}
    values.update(id=demo_id("orphaned"), block_hash="0x" + "cc" * 32, canonicality="orphaned")
    db.add(Observation(**values))
    db.flush()
    assert db.scalar(select(func.count()).select_from(Observation).where(Observation.tx_hash == original.tx_hash)) == 2
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE observations SET chain_id = 'eip155:8453' WHERE id = :id"), {"id": original.id})
    # Une même inclusion et position reste unique, même si on change l'ID technique.
    values.update(id=demo_id("duplicate"))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Observation(**values))
            db.flush()


def test_unknown_decimals_and_multi_movement_operation(db, client):
    seed_demo(db)
    asset = db.get(Asset, "eip155:1/native")
    asset.decimals = None
    operation = db.get(Operation, demo_id("operation-0"))
    db.add(OperationMovement(operation_id=operation.id, observation_id=demo_id("movement-1"), role="output"))
    db.commit()
    result = client.get(f'/api/v1/operations/{operation.id}').json()
    assert len(result["movements"]) == 2
    assert all(item["observation"]["asset"]["decimals"] is None for item in result["movements"])


def test_analytical_and_attribution_records_do_not_mutate_observations(db, client):
    seed_demo(db)
    identity = demo_id("movement-0")
    before = client.get(f'/api/v1/observations/{identity}').json()
    db.add(LabelAssertion(
        subject_address_id=before["source_address_id"], predicate="test-only-note",
        value="Assertion technique de test, aucune entité réelle", source="test fixture",
        evidence_ref=before["evidence_ref"], observed_at=datetime.now(timezone.utc),
        method="test-only", review_status="unreviewed", version="test-v1",
    ))
    db.add(Allocation(run_id=demo_id("run"), observation_id=identity, amount_raw=1,
                      policy_version="test-only-v1", rationale="Vérification de séparation, aucun moteur"))
    db.commit()
    assert client.get(f'/api/v1/observations/{identity}').json() == before
    assert db.scalar(select(func.count()).select_from(Operation)) == 3
    # Le run initial reste un snapshot sans ces enrichissements ultérieurs.
    assert client.get(f'/api/v1/runs/{demo_id("run")}').json()["label_snapshot"] == []


def test_create_case_and_unsupported_run_are_not_simulated(db, client):
    seed_demo(db)
    body = {"title": "Dossier local", "seeds": [{"chain_id": "eip155:8453", "kind": "transaction", "reference": "0x" + "aa" * 32}]}
    response = client.post('/api/v1/cases', json=body)
    assert response.status_code == 201
    case = response.json()
    assert case["is_demo"] is False
    route = f'/api/v1/cases/{case["id"]}/runs'
    assert client.post(route).status_code == 422
    first = client.post(route, headers={"Idempotency-Key": "same"})
    second = client.post(route, headers={"Idempotency-Key": "same"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["state"] == first.json()["coverage_status"] == "unsupported"
    assert first.json()["is_demo"] is False
    assert first.json()["parameters"]["provider_calls"] == 0
    assert first.json()["manifest"] == []
    assert client.get(f'/api/v1/runs/{first.json()["id"]}/operations').json() == []
    assert client.get(f'/api/v1/cases/{case["id"]}').json()["seeds"][0]["reference"] == body["seeds"][0]["reference"]
