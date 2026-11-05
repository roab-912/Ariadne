"""Normalisation pure des pièces EVM ; aucune découverte, identité ou allocation."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from investigation.domain import AddressId, asset_id, uint256

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
NORMALIZER_VERSION = "evm-transfer/0.2.0"


class InvalidBundle(ValueError):
    pass


def quantity(value) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise InvalidBundle("invalid_quantity")
    return int(value, 16)


def hash32(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
        raise InvalidBundle("invalid_hash")
    return value.lower()


def address(value) -> str:
    try:
        return AddressId.evm("eip155:1", value).key
    except (ValueError, TypeError):
        raise InvalidBundle("invalid_address") from None


@dataclass(frozen=True)
class Movement:
    source: str
    target: str
    asset: str
    amount: int
    origin: str
    position: str
    evidence_path: str
    metadata: dict
    kind: str


@dataclass
class NormalizedBundle:
    tx_hash: str
    block_hash: str
    parent_hash: str
    block_number: int
    transaction_index: int
    timestamp: datetime
    transaction_status: int
    movements: list[Movement] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)


def normalize_bundle(data: dict, expected_hash: str) -> NormalizedBundle:
    """Vérifie la cohérence RPC ; ne prétend pas valider un bloc cryptographiquement."""
    try:
        return _normalize(data, expected_hash)
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        if isinstance(error, InvalidBundle):
            raise
        raise InvalidBundle("malformed_bundle") from None


def _normalize(data, expected_hash):
    tx, receipt, block = data["transaction"], data["receipt"], data["block"]
    canonical = data["canonical_block"]
    tx_hash = hash32(expected_hash)
    block_hash = hash32(block["hash"])
    number, index = quantity(block["number"]), quantity(tx["transactionIndex"])
    if number >= 2**64 or index >= 2**31:
        raise InvalidBundle("invalid_block_position")
    if any(hash32(value) != tx_hash for value in (tx["hash"], receipt["transactionHash"])):
        raise InvalidBundle("transaction_hash_mismatch")
    if any(hash32(value) != block_hash for value in (tx["blockHash"], receipt["blockHash"], canonical["hash"])):
        raise InvalidBundle("block_hash_mismatch")
    if any(quantity(value) != number for value in (tx["blockNumber"], receipt["blockNumber"], canonical["number"])):
        raise InvalidBundle("block_number_mismatch")
    if quantity(receipt["transactionIndex"]) != index:
        raise InvalidBundle("transaction_index_mismatch")
    hashes = block["transactions"]
    if not isinstance(hashes, list) or index >= len(hashes) or hash32(hashes[index]) != tx_hash:
        raise InvalidBundle("transaction_not_in_block")
    if "chainId" in tx and quantity(tx["chainId"]) != 1:
        raise InvalidBundle("transaction_chain_mismatch")
    source = address(tx["from"])
    target = address(tx["to"]) if tx["to"] is not None else None
    if address(receipt["from"]) != source or (address(receipt["to"]) if receipt["to"] is not None else None) != target:
        raise InvalidBundle("receipt_parties_mismatch")
    value = uint256(quantity(tx["value"]))
    status = quantity(receipt["status"])
    if status not in (0, 1) or not isinstance(receipt["logs"], list):
        raise InvalidBundle("invalid_receipt_status_or_logs")
    if len(receipt["logs"]) > 5000:
        raise InvalidBundle("receipt_log_limit_exceeded")
    result = NormalizedBundle(tx_hash, block_hash, hash32(block["parentHash"]), number, index,
        datetime.fromtimestamp(quantity(block["timestamp"]), timezone.utc), status)
    if status == 0:
        if receipt["logs"]:
            raise InvalidBundle("failed_receipt_has_logs")
        result.limits.append("transaction_reverted_no_effective_transfer")
        return result
    if value:
        destination = target or address(receipt["contractAddress"])
        result.movements.append(Movement(source, destination, asset_id("eip155:1"), value,
            "top_level", "0", "/transaction", {"id": asset_id("eip155:1"), "chain_id": "eip155:1",
            "decimals": 18, "symbol": "ETH", "metadata_source": "Ethereum native unit: wei (10^-18 ETH)"}, "native_transfer"))
    seen_indices = set()
    for position, log in enumerate(receipt["logs"]):
        if hash32(log["transactionHash"]) != tx_hash or hash32(log["blockHash"]) != block_hash or quantity(log["blockNumber"]) != number or quantity(log["transactionIndex"]) != index or log.get("removed", False) is not False:
            raise InvalidBundle("log_inclusion_mismatch")
        log_index = quantity(log["logIndex"])
        if log_index in seen_indices:
            raise InvalidBundle("duplicate_log_index")
        seen_indices.add(log_index)
        topics = log["topics"]
        if not isinstance(topics, list):
            raise InvalidBundle("invalid_topics")
        if not topics or hash32(topics[0]) != TRANSFER_TOPIC or len(topics) == 4:
            continue
        if len(topics) != 3 or not isinstance(log["data"], str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", log["data"]):
            result.limits.append("malformed_transfer_event")
            continue
        if any(not isinstance(topic, str) or not re.fullmatch(r"0x0{24}[0-9a-fA-F]{40}", topic) for topic in topics[1:]):
            result.limits.append("nonstandard_transfer_topics")
            continue
        contract = AddressId.evm("eip155:1", log["address"])
        identity = asset_id("eip155:1", contract.display)
        metadata = data.get("asset_metadata", {}).get(contract.display.lower(), {})
        decimals = metadata.get("decimals")
        if type(decimals) is not int or not 0 <= decimals <= 255:
            decimals = None
        result.movements.append(Movement(address("0x" + topics[1][-40:]), address("0x" + topics[2][-40:]),
            identity, uint256(int(log["data"], 16)), "log", str(log_index), f"/receipt/logs/{position}",
            {"id": identity, "chain_id": "eip155:1", "symbol": None, "decimals": decimals,
             "metadata_source": f"RPC eth_call decimals at block hash; contract {contract.display.lower()}"}, "erc20_transfer"))
    return result
