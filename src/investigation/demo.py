"""Chargement explicite et rejouable du scénario Démonstration, jamais au démarrage API."""
import hashlib
import json
from datetime import datetime, timezone
from importlib.resources import files
from uuid import NAMESPACE_URL, uuid5

from investigation.domain import AddressId, asset_id, parse_amount
from investigation.models import (
    Address, AnalysisRun, Asset, Case, CaseSeed, Chain, Observation, Operation,
    OperationMovement, RunOperation, SourceSnapshot,
)


def demo_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ariadne:demo:v0.1:{name}"))


def seed_demo(session):
    case_id = demo_id("case")
    if session.get(Case, case_id):
        return case_id
    data = json.loads(files("investigation").joinpath("fixtures/demo.json").read_text(encoding="utf-8"))
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    coverage = {"scope": "synthetic_fixture_only", "chain_ids": [data["chain_id"]], "limits": data["limits"]}
    stamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    for chain, name in [("eip155:1", "Ethereum"), ("eip155:8453", "Base"), ("eip155:42161", "Arbitrum One")]:
        if session.get(Chain, chain) is None:
            session.add(Chain(id=chain, name=name, family="evm"))
    session.flush()
    addresses = [AddressId.evm(data["chain_id"], value) for value in data["addresses"]]
    for address in addresses:
        if session.get(Address, address.key) is None:
            session.add(Address(id=address.key, chain_id=address.chain_id, value=address.value, display=address.display))
    native = asset_id(data["chain_id"])
    if session.get(Asset, native) is None:
        session.add(Asset(id=native, chain_id=data["chain_id"], contract_address=None, **data["asset"], metadata_source="Démonstration · demo-v0.1"))
    snapshot = SourceSnapshot(id=demo_id("snapshot"), source="Démonstration · fixture locale demo-v0.1", retrieved_at=stamp, is_demo=True, content=data, sha256=digest, coverage=coverage)
    case = Case(id=case_id, title="Démonstration · Transfert puis dispersion", description=data["notice"], created_at=stamp, is_demo=True)
    session.add_all([snapshot, case])
    session.flush()
    seed = {"chain_id": data["chain_id"], "kind": "transaction", "reference": data["movements"][0]["tx_hash"], "observation_id": demo_id("movement-0"), "window": {}}
    for index, movement in enumerate(data["movements"]):
        evidence = f"{snapshot.id}#/movements/{index}"
        observation = Observation(
            id=demo_id(f"movement-{index}"), chain_id=data["chain_id"],
            block_number=int(movement["block_number"]), block_hash=movement["block_hash"], parent_hash=movement["parent_hash"],
            tx_hash=movement["tx_hash"], transaction_index=movement["transaction_index"],
            origin=movement["origin"], position=movement["position"], observed_at=datetime.fromisoformat(movement["observed_at"]),
            canonicality="unknown", finality={"status": "unknown", "reason": "synthetic"},
            source_address_id=addresses[movement["from"]].key, target_address_id=addresses[movement["to"]].key,
            asset_id=native, amount_raw=parse_amount(movement["amount_raw"]), snapshot_id=snapshot.id, evidence_ref=evidence,
        )
        operation = Operation(id=demo_id(f"operation-{index}"), kind="transfer", protocol=None, decoder_version="fixture-manual/demo-v0.1", decoding_status="synthetic", evidence_refs=[evidence], is_demo=True)
        session.add_all([observation, operation])
        session.flush()
        session.add(OperationMovement(operation_id=operation.id, observation_id=observation.id, role="transfer"))
    session.flush()
    session.add(CaseSeed(id=demo_id("seed"), case_id=case_id, **seed))
    run = AnalysisRun(
        id=demo_id("run"), case_id=case_id, idempotency_key="demo-v0.1", created_at=stamp,
        state="snapshot", coverage_status="partial", is_demo=True, seeds_snapshot=[seed],
        parameters={"mode": "synthetic_fixture_only", "provider_calls": 0},
        block_bounds={"eip155:1": {"start": "100", "end": "101", "hashes": sorted({m["block_hash"] for m in data["movements"]})}},
        allocation_policy="none", decoder_versions={"fixture-manual": "demo-v0.1"}, label_snapshot=[],
        coverage=coverage, stop_reasons=["synthetic_fixture_boundary", "no_real_provider"],
        manifest=[{"snapshot_id": snapshot.id, "sha256": digest, "encoding": "UTF-8", "canonicalization": "json-sort-keys-compact-ensure-ascii-false"}],
    )
    session.add(run)
    session.flush()
    for index in range(len(data["movements"])):
        session.add(RunOperation(run_id=run.id, operation_id=demo_id(f"operation-{index}")))
    session.commit()
    return case_id


if __name__ == "__main__":
    from investigation.db import Session
    with Session() as session:
        identity = seed_demo(session)
        print(f"Démonstration synthétique prête : dossier {identity}")
