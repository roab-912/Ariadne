"""Collecte synchrone bornée V0.2. Aucun job, expansion ou allocation."""
import hashlib
import json
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from connectors.ethereum import CHAIN, EthereumProvider
from connectors.contracts import BlockRange
from investigation.domain import AddressId
from investigation.models import (
    Address, AnalysisRun, Asset, Observation, Operation, OperationMovement,
    RunBundle, RunOperation, SourceSnapshot, TransactionBundle,
)
from investigation.normalization import InvalidBundle, NORMALIZER_VERSION, normalize_bundle

EXCLUSIONS = [
    "Transferts ETH internes, frais, retraits de consensus et NFT hors périmètre",
    "Aucun swap, bridge, label d'entité ni allocation analytique",
    "Les événements Transfer au format ERC-20 ne prouvent ni valeur économique ni conformité globale du contrat",
    "Canonicalité et finalité observées auprès du RPC à la collecte ; aucune surveillance des réorganisations",
]


def stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ariadne:ethereum:v0.2:{value}"))


def seed_range(seed: dict, requested: BlockRange | None):
    window = seed.get("window", {})
    if "start_block" in window and "end_block" in window:
        scope = BlockRange(start=int(window["start_block"]), end=int(window["end_block"]))
        if requested and scope != requested:
            raise ValueError("run_block_range_differs_from_seed")
        return scope
    return requested


def collect_run(session, run: AnalysisRun, provider: EthereumProvider, request):
    reasons: list[str] = []
    limitations = list(EXCLUSIONS)
    discovery = []
    ranges, candidates = {}, {}
    bundle_ids = []
    movement_count = 0
    complete = True
    unsupported = 0
    unknown = 0
    snapshot_ids: set[str] = set()

    def retain(snapshot):
        if snapshot.id not in snapshot_ids:
            snapshot_ids.add(snapshot.id)
            run.manifest = [*run.manifest, {"snapshot_id": snapshot.id, "sha256": snapshot.sha256,
                "encoding": "UTF-8", "canonicalization": "json-sort-keys-compact-ensure-ascii-false"}]

    def snapshot(source, content, coverage):
        raw = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        piece = SourceSnapshot(source=source, is_demo=False, content=content,
            sha256=hashlib.sha256(raw).hexdigest(), coverage=coverage)
        session.add(piece)
        session.flush()
        retain(piece)
        return piece

    def evidence(result):
        for artifact in result.artifacts:
            snapshot(artifact.source, artifact.model_dump(mode="json"), {
                "chain_id": CHAIN, "status": result.status.value, "limits": result.limits,
                "requested_range": result.requested_range.model_dump() if result.requested_range else None,
                "covered_range": result.covered_range.model_dump() if result.covered_range else None,
                "cursor": result.cursor,
            })

    run.parameters = {"mode": "ethereum_bounded_collection", "provider_calls": 0,
        "request": request.model_dump(mode="json"), "budgets": {"max_calls": provider.http.budget.max_calls,
        "max_seconds": provider.http.budget.max_seconds, "max_bytes": provider.http.budget.max_bytes, "max_movements": 200}}
    run.decoder_versions = {"evm-transfer": NORMALIZER_VERSION}
    if not any(seed["chain_id"] == CHAIN for seed in run.seeds_snapshot):
        run.state = run.coverage_status = "unsupported"
        run.stop_reasons = ["unsupported_chain"]
        run.coverage = {"scope": "none", "limits": ["Ethereum mainnet uniquement en V0.2.0", *EXCLUSIONS]}
        return
    if not provider.settings.rpc_url:
        run.state = run.coverage_status = "unsupported"
        run.stop_reasons = ["rpc_not_configured"]
        run.coverage = {"scope": "ethereum_top_level_eth_and_erc20_transfer_logs", "limits": ["Configurer ETHEREUM_RPC_URL", *EXCLUSIONS]}
        return
    head = provider.get_chain_head_and_finality(CHAIN)
    evidence(head)
    heads = head.data or {}
    if any(reason in head.limits for reason in ("rpc_chain_mismatch", "rpc_not_configured")):
        run.state = run.coverage_status = "partial"
        run.stop_reasons = head.limits
        run.coverage = {"scope": "none", "limits": [*head.limits, *EXCLUSIONS]}
        run.parameters = {**run.parameters, "provider_calls": provider.http.budget.calls}
        return

    # Découverte bornée des candidats ; les valeurs de l'indexeur ne deviennent jamais des mouvements.
    for seed in run.seeds_snapshot:
        if seed["chain_id"] != CHAIN:
            reasons.append("unsupported_chain")
            unsupported += 1
            complete = False
            continue
        scope = seed_range(seed, request.block_range)
        if scope and (not heads.get("latest") or scope.end > int(heads["latest"]["number"])):
            reasons.append("requested_range_not_verified_below_head")
            complete = False
            continue
        if scope and scope.end - scope.start >= 10000:
            reasons.append("block_range_limit_exceeded")
            complete = False
            continue
        if scope:
            ranges[seed["id"]] = scope.model_dump()
        if seed["kind"] == "transaction":
            candidates.setdefault(seed["reference"], []).append(seed)
            continue
        if scope is None:
            reasons.append("explicit_block_range_required")
            unsupported += 1
            complete = False
            continue
        cursor, pages = None, 0
        while True:
            previous_cursor = cursor
            result = provider.discover_address_activity(seed["reference"], scope, cursor)
            evidence(result)
            pages += 1
            reasons.extend(result.limits)
            if result.limits:
                complete = False
            if result.data is None:
                unsupported += result.status.value == "unsupported"
                complete = False
            for row in result.data or []:
                tx_hash = row["hash"].lower()
                if tx_hash not in candidates and len(candidates) >= request.max_transactions:
                    reasons.append("transaction_limit_reached")
                    complete = False
                    break
                candidates.setdefault(tx_hash, []).append(seed)
            cursor = result.cursor
            if result.status.value != "complete_within_declared_scope" and not cursor:
                complete = False
            if "transaction_limit_reached" in reasons or result.data is None or not cursor or pages >= 12:
                if cursor:
                    complete = False
                    reasons.append("discovery_incomplete")
                discovery.append({"seed_id": seed["id"], "status": result.status.value,
                    "pages": pages, "requested_range": scope.model_dump(),
                    "last_page_cursor": previous_cursor, "next_cursor": cursor,
                    "limits": result.limits, "finished": cursor is None and result.status.value == "complete_within_declared_scope"})
                break
    hashes = list(candidates)
    if len(hashes) > request.max_transactions:
        hashes = hashes[:request.max_transactions]
        reasons.append("transaction_limit_reached")
        complete = False

    verified_bounds: dict[str, dict] = {}
    for tx_hash in hashes:
        result = provider.get_transaction_bundle(CHAIN, tx_hash)
        evidence(result)
        if result.data is None:
            reasons.extend(result.limits)
            unknown += result.status.value == "unknown"
            complete = False
            continue
        try:
            normalized = normalize_bundle(result.data, tx_hash)
        except InvalidBundle as error:
            reasons.append(str(error))
            complete = False
            continue
        accepted_seeds = []
        for seed in candidates[tx_hash]:
            scope = seed_range(seed, request.block_range)
            if scope and not scope.start <= normalized.block_number <= scope.end:
                complete = False
                reasons.append("transaction_outside_block_range")
                continue
            if seed["kind"] == "address":
                parties = {"eip155:1:" + result.data["transaction"]["from"].lower()}
                if result.data["transaction"]["to"]:
                    parties.add("eip155:1:" + result.data["transaction"]["to"].lower())
                parties.update(value for movement in normalized.movements for value in (movement.source, movement.target))
                if seed["reference"] not in parties:
                    complete = False
                    reasons.append("indexer_candidate_not_related_to_address")
                    continue
                window = seed.get("window", {})
                if "start" in window and not datetime.fromisoformat(window["start"]) <= normalized.timestamp <= datetime.fromisoformat(window["end"]):
                    continue
            accepted_seeds.append(seed)
        if not accepted_seeds:
            continue
        if movement_count + len(normalized.movements) > 200:
            complete = False
            reasons.append("movement_limit_reached")
            break
        limits = normalized.limits
        if any(value != "transaction_reverted_no_effective_transfer" for value in limits):
            complete = False
        reasons.extend(limits)
        finality = {"status": "unknown", "policy": "ethereum_safe_finalized_tags", "heads": heads,
                    "observed_at": result.retrieved_at.isoformat()}
        if heads.get("finalized") and int(heads["finalized"]["number"]) >= normalized.block_number:
            finality["status"] = "finalized"
        elif heads.get("safe") and int(heads["safe"]["number"]) >= normalized.block_number:
            finality["status"] = "safe"
        if finality["status"] != "finalized":
            reasons.append("finality_not_finalized_at_collection")
            complete = False
        content = {"kind": "ethereum_transaction_bundle", "bundle": result.data, "finality": finality}
        piece = snapshot("ethereum-json-rpc · verified bundle", content,
            {"scope": "one_transaction_top_level_eth_and_erc20_transfer_logs", "limits": limits})
        identity = stable_id(f"bundle:{normalized.block_hash}:{tx_hash}")
        existing = session.get(TransactionBundle, identity)
        if existing:
            old_observations = session.scalars(select(Observation).where(Observation.bundle_id == identity)).all()
            old = sorted((item.source_address_id, item.target_address_id, item.asset_id, item.amount_raw, item.origin, item.position) for item in old_observations)
            new = sorted((item.source, item.target, item.asset, item.amount, item.origin, item.position) for item in normalized.movements)
            if old != new or existing.transaction_status != normalized.transaction_status:
                reasons.append("conflicting_existing_bundle")
                complete = False
                continue
            retain(session.get(SourceSnapshot, existing.snapshot_id))
        else:
            session.add(TransactionBundle(id=identity, chain_id=CHAIN, block_hash=normalized.block_hash,
                block_number=normalized.block_number, tx_hash=tx_hash, transaction_status=normalized.transaction_status,
                snapshot_id=piece.id, normalization_limits=limits))
            session.flush()
            for movement in normalized.movements:
                for address_key in (movement.source, movement.target):
                    value = AddressId.evm(CHAIN, address_key.rsplit(":", 1)[1])
                    if session.get(Address, value.key) is None:
                        session.add(Address(id=value.key, chain_id=CHAIN, value=value.value, display=value.display))
                        session.flush()
                if session.get(Asset, movement.asset) is None:
                    contract = bytes.fromhex(movement.asset.rsplit(":", 1)[1][2:]) if "/erc20:" in movement.asset else None
                    session.add(Asset(id=movement.asset, chain_id=CHAIN, contract_address=contract,
                        symbol=movement.metadata["symbol"], decimals=movement.metadata["decimals"], metadata_source=movement.metadata["metadata_source"]))
                    session.flush()
                observation_id = stable_id(f"observation:{identity}:{movement.origin}:{movement.position}")
                reference = f"{piece.id}#/bundle{movement.evidence_path}"
                session.add(Observation(id=observation_id, chain_id=CHAIN, block_number=normalized.block_number,
                    block_hash=normalized.block_hash, parent_hash=normalized.parent_hash, tx_hash=tx_hash,
                    transaction_index=normalized.transaction_index, origin=movement.origin, position=movement.position,
                    observed_at=normalized.timestamp, canonicality="canonical", finality=finality,
                    source_address_id=movement.source, target_address_id=movement.target, asset_id=movement.asset,
                    amount_raw=movement.amount, snapshot_id=piece.id, evidence_ref=reference,
                    bundle_id=identity, asset_metadata=movement.metadata))
                operation_id = stable_id(f"operation:{observation_id}")
                session.add(Operation(id=operation_id, kind=movement.kind, protocol="erc20" if movement.origin == "log" else None,
                    decoder_version=NORMALIZER_VERSION, decoding_status="normalized", evidence_refs=[reference], is_demo=False))
                session.flush()
                session.add(OperationMovement(operation_id=operation_id, observation_id=observation_id, role="transfer"))
        session.flush()
        session.add(RunBundle(run_id=run.id, bundle_id=identity))
        bundle_ids.append(identity)
        movement_count += len(normalized.movements)
        observations = session.scalars(select(Observation).where(Observation.bundle_id == identity)).all()
        for observation in observations:
            retain(session.get(SourceSnapshot, observation.snapshot_id))
            session.add(RunOperation(run_id=run.id, operation_id=stable_id(f"operation:{observation.id}")))
        for seed in accepted_seeds:
            bound = verified_bounds.setdefault(seed["id"], {"start": str(normalized.block_number), "end": str(normalized.block_number), "hashes": []})
            bound["start"] = str(min(int(bound["start"]), normalized.block_number))
            bound["end"] = str(max(int(bound["end"]), normalized.block_number))
            if normalized.block_hash not in bound["hashes"]:
                bound["hashes"].append(normalized.block_hash)
    run.block_bounds = {"requested_by_seed": ranges, "verified_by_seed": verified_bounds}
    run.parameters = {**run.parameters, "provider_calls": provider.http.budget.calls,
                      "response_bytes": provider.http.budget.bytes_received, "collected_transactions": len(bundle_ids)}
    run.coverage_status = "complete_within_declared_scope" if complete else "partial"
    if not bundle_ids and unsupported == len(run.seeds_snapshot):
        run.coverage_status = "unsupported"
    elif not bundle_ids and unknown and unknown == len(hashes):
        run.coverage_status = "unknown"
    run.state = "completed" if complete else run.coverage_status
    run.stop_reasons = list(dict.fromkeys(reasons))
    run.coverage = {"scope": "ethereum_top_level_eth_and_erc20_transfer_logs", "chain_ids": [CHAIN],
        "limits": [*EXCLUSIONS, *run.stop_reasons], "discovery": discovery,
        "finality_heads": heads, "finality_limits": head.limits,
        "verified_transaction_count": len(bundle_ids), "requested_ranges": ranges}
    session.flush()
