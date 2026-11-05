"""Ethereum mainnet uniquement : JSON-RPC de vérification, Etherscan V2 de découverte."""
import base64
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from connectors.contracts import BlockRange, Capabilities, ProviderResult
from connectors.transport import BoundedHTTP, Budget, ProviderError
from investigation.domain import AddressId, CoverageStatus

CHAIN = "eip155:1"
HASH = re.compile(r"0x[0-9a-fA-F]{64}\Z")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def hex_int(value) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise ProviderError("invalid_rpc_quantity")
    return int(value, 16)


def hash_value(value) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ProviderError("invalid_rpc_hash")
    return value.lower()


def check_endpoint(value: str):
    if not value:
        return
    parsed = urlsplit(value)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or not (parsed.scheme == "https" or (parsed.scheme == "http" and local)):
        raise ValueError("Endpoint serveur HTTPS attendu (HTTP accepté sur boucle locale)")


@dataclass(frozen=True)
class EthereumSettings:
    rpc_url: str = ""
    etherscan_api_key: str = ""
    etherscan_url: str = "https://api.etherscan.io/v2/api"
    page_size: int = 100
    result_cap: int = 10000
    index_interval: float = 0.55

    def __post_init__(self):
        check_endpoint(self.rpc_url)
        check_endpoint(self.etherscan_url)
        if not 1 <= self.page_size <= 1000 or not self.page_size <= self.result_cap <= 10000:
            raise ValueError("Taille de page / plafond Etherscan invalides")

    @classmethod
    def from_env(cls):
        return cls(rpc_url=os.getenv("ETHEREUM_RPC_URL", ""), etherscan_api_key=os.getenv("ETHERSCAN_API_KEY", ""))


class EthereumProvider:
    def __init__(self, settings: EthereumSettings, *, transport=None, budget=None):
        self.settings = settings
        endpoint = urlsplit(settings.rpc_url)
        path_values = [unquote(value) for value in endpoint.path.split("/") if value and value.lower() not in
            {"v1", "v2", "v3", "api", "rpc", "json-rpc", "eth", "ethereum", "mainnet"}]
        secrets = [settings.rpc_url, settings.etherscan_api_key, *path_values, *(value for _, value in parse_qsl(endpoint.query))]
        self.http = BoundedHTTP(budget or Budget(), transport, tuple([*secrets, *(quote(value, safe="") for value in secrets if value)]))
        self.checked_chain = False
        self.last_index_call = 0.0

    def close(self):
        self.http.close()

    def get_capabilities(self, chain: str) -> Capabilities:
        available = chain == CHAIN and bool(self.settings.rpc_url)
        return Capabilities(
            provider="ethereum-json-rpc + etherscan-v2", chain_id=chain,
            status=CoverageStatus.PARTIAL if available else CoverageStatus.UNSUPPORTED,
            transaction_bundle=available, logs=available, traces=False,
            address_history=available and bool(self.settings.etherscan_api_key),
            pagination="pages + subdivision de plages au plafond" if available and self.settings.etherscan_api_key else None,
            finality_policy="ethereum safe/finalized si disponibles", quota="100 appels / 45 s / 24 Mio par run",
            cost="selon contrats des fournisseurs configurés",
            limits=["Ethereum mainnet uniquement", "Aucune trace, frais, NFT, swap ni relation inter-chaînes", "Capacités configurées, disponibilité et profondeur historique vérifiées lors des appels", "Historique par adresse : RPC + clé Etherscan V2 nécessaires"],
        )

    def _result(self, start, *, data=None, status=CoverageStatus.PARTIAL, limits=None, block_range=None, covered=None, cursor=None):
        return ProviderResult(
            data=data, source="ethereum-json-rpc + etherscan-v2", retrieved_at=datetime.now(timezone.utc),
            chain_id=CHAIN, status=status, limits=limits or [], requested_range=block_range,
            covered_range=covered, cursor=cursor, artifacts=self.http.artifacts[start:],
        )

    def call(self, method: str, params: list):
        if not self.settings.rpc_url:
            raise ProviderError("rpc_not_configured")
        identity = self.http.budget.calls + 1
        value = self.http.fetch("POST", self.settings.rpc_url, source="ethereum-json-rpc",
            request={"method": method, "params": params}, json={"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or value.get("id") != identity:
            raise ProviderError("invalid_rpc_envelope")
        if "error" in value:
            code = value["error"].get("code") if isinstance(value["error"], dict) else None
            raise ProviderError("rpc_method_unavailable" if code == -32601 else "rpc_error")
        if "result" not in value:
            raise ProviderError("invalid_rpc_envelope")
        return value["result"]

    def ensure_chain(self, chain: str):
        if chain != CHAIN:
            raise ProviderError("unsupported_chain")
        if not self.checked_chain:
            if hex_int(self.call("eth_chainId", [])) != 1:
                raise ProviderError("rpc_chain_mismatch")
            self.checked_chain = True

    def get_transaction_bundle(self, chain: str, tx_hash: str):
        start = len(self.http.artifacts)
        try:
            self.ensure_chain(chain)
            tx_hash = hash_value(tx_hash)
            tx = self.call("eth_getTransactionByHash", [tx_hash])
            if tx is None:
                return self._result(start, status=CoverageStatus.UNKNOWN, limits=["transaction_not_found"])
            if not isinstance(tx, dict) or tx.get("blockHash") is None:
                return self._result(start, status=CoverageStatus.PARTIAL, limits=["transaction_pending_or_invalid"])
            receipt = self.call("eth_getTransactionReceipt", [tx_hash])
            if receipt is None:
                return self._result(start, limits=["receipt_unavailable"])
            block = self.call("eth_getBlockByHash", [hash_value(tx["blockHash"]), False])
            canonical = self.call("eth_getBlockByNumber", [hex(hex_int(tx["blockNumber"])), False])
            if not isinstance(block, dict) or not isinstance(canonical, dict) or canonical.get("hash") != block.get("hash"):
                raise ProviderError("inclusion_not_canonical_at_collection")
            metadata = {}
            # Métadonnées optionnelles au hash du bloc ; leur absence ne perd aucun montant brut.
            if isinstance(receipt, dict) and isinstance(receipt.get("logs"), list):
                contracts = sorted({log.get("address", "").lower() for log in receipt["logs"]
                    if isinstance(log, dict) and isinstance(log.get("address"), str)
                    and isinstance(log.get("topics"), list) and len(log["topics"]) == 3
                    and isinstance(log["topics"][0], str) and log["topics"][0].lower() == TRANSFER_TOPIC})
                for contract in contracts[:8]:
                    try:
                        AddressId.evm(CHAIN, contract)
                        raw = self.call("eth_call", [{"to": contract, "data": "0x313ce567"}, {"blockHash": block["hash"], "requireCanonical": True}])
                        decimals = int(raw, 16) if isinstance(raw, str) and re.fullmatch(r"0x[0-9a-fA-F]{64}", raw) else None
                        metadata[contract] = {"decimals": decimals if decimals is not None and decimals <= 255 else None, "symbol": None}
                    except (ProviderError, ValueError):
                        metadata[contract] = {"decimals": None, "symbol": None}
            return self._result(start, data={"transaction": tx, "receipt": receipt, "block": block, "canonical_block": canonical, "asset_metadata": metadata}, status=CoverageStatus.COMPLETE)
        except (ProviderError, KeyError, TypeError, ValueError) as error:
            reason = error.reason if isinstance(error, ProviderError) else "malformed_transaction_bundle"
            return self._result(start, status=CoverageStatus.UNSUPPORTED if reason in ("rpc_not_configured", "unsupported_chain") else CoverageStatus.PARTIAL, limits=[reason])

    def get_chain_head_and_finality(self, chain: str):
        start = len(self.http.artifacts)
        result, limits = {}, []
        try:
            self.ensure_chain(chain)
            for tag in ("latest", "safe", "finalized"):
                try:
                    block = self.call("eth_getBlockByNumber", [tag, False])
                    if not isinstance(block, dict):
                        raise ProviderError("head_unavailable")
                    result[tag] = {"number": str(hex_int(block["number"])), "hash": hash_value(block["hash"])}
                except (ProviderError, KeyError, TypeError) as error:
                    limits.append(f"{tag}_unavailable")
            for tag in ("safe", "finalized"):
                if tag in result and ("latest" not in result or int(result[tag]["number"]) > int(result["latest"]["number"])
                    or (result[tag]["number"] == result["latest"]["number"] and result[tag]["hash"] != result["latest"]["hash"])):
                    result.pop(tag)
                    limits.append("inconsistent_finality_heads")
            if "safe" in result and "finalized" in result and (int(result["finalized"]["number"]) > int(result["safe"]["number"])
                or (result["finalized"]["number"] == result["safe"]["number"] and result["finalized"]["hash"] != result["safe"]["hash"])):
                result.pop("finalized")
                limits.append("inconsistent_finality_heads")
            return self._result(start, data=result, status=CoverageStatus.PARTIAL if limits else CoverageStatus.COMPLETE, limits=limits)
        except ProviderError as error:
            return self._result(start, status=CoverageStatus.UNSUPPORTED if not self.settings.rpc_url else CoverageStatus.PARTIAL, limits=[error.reason])

    def get_logs(self, chain: str, filter: dict, cursor=None):
        start = len(self.http.artifacts)
        try:
            if cursor or set(filter) - {"fromBlock", "toBlock", "address", "topics"}:
                raise ProviderError("unsupported_logs_filter")
            scope = BlockRange(start=hex_int(filter["fromBlock"]), end=hex_int(filter["toBlock"]))
            if scope.end - scope.start >= 1000:
                raise ProviderError("logs_range_too_large")
            self.ensure_chain(chain)
            logs = self.call("eth_getLogs", [filter])
            if not isinstance(logs, list) or len(logs) >= 5000:
                raise ProviderError("logs_truncated_or_invalid")
            return self._result(start, data=logs, status=CoverageStatus.COMPLETE, block_range=scope, covered=scope)
        except (ProviderError, KeyError, ValueError) as error:
            return self._result(start, limits=[error.reason if isinstance(error, ProviderError) else "invalid_logs_range"])

    def discover_address_activity(self, address: str, block_range: BlockRange, cursor=None):
        start = len(self.http.artifacts)
        try:
            chain, raw_address = address.rsplit(":", 1)
            AddressId.evm(chain, raw_address)
            if chain != CHAIN:
                raise ProviderError("unsupported_chain")
            if not self.settings.etherscan_api_key:
                raise ProviderError("indexer_not_configured")
            tasks = [[action, block_range.start, block_range.end, 1] for action in ("txlist", "tokentx")]
            cumulative_limits = []
            if cursor:
                if len(cursor) > 16384:
                    raise ProviderError("invalid_indexer_cursor")
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if decoded["address"] != address.lower() or decoded["range"] != block_range.model_dump():
                    raise ProviderError("cursor_scope_mismatch")
                tasks = decoded["tasks"]
                cumulative_limits = decoded["limits"]
                if not isinstance(cumulative_limits, list) or any(value != "indexer_dense_block_truncated" for value in cumulative_limits):
                    raise ProviderError("invalid_indexer_cursor")
            if not tasks or len(tasks) > 64:
                raise ProviderError("invalid_indexer_cursor")
            if any(not isinstance(task, list) or len(task) != 4 or task[0] not in ("txlist", "tokentx")
                   or any(type(value) is not int for value in task[1:])
                   or not block_range.start <= task[1] <= task[2] <= block_range.end or task[3] < 1
                   or task[3] * self.settings.page_size > self.settings.result_cap for task in tasks):
                raise ProviderError("invalid_indexer_cursor")
            action, low, high, page = tasks[0]
            if action not in ("txlist", "tokentx") or not block_range.start <= low <= high <= block_range.end or type(page) is not int or page < 1 or page * self.settings.page_size > self.settings.result_cap:
                raise ProviderError("invalid_indexer_cursor")
            delay = self.settings.index_interval - (time.monotonic() - self.last_index_call)
            if delay > 0:
                if delay >= self.http.budget.remaining():
                    raise ProviderError("time_budget_exhausted")
                time.sleep(delay)
            self.last_index_call = time.monotonic()
            params = {"chainid": "1", "module": "account", "action": action, "address": raw_address,
                      "startblock": low, "endblock": high, "page": page, "offset": self.settings.page_size, "sort": "asc"}
            value = self.http.fetch("GET", self.settings.etherscan_url, source="etherscan-v2", request=params,
                                    params={**params, "apikey": self.settings.etherscan_api_key})
            if not isinstance(value, dict):
                raise ProviderError("invalid_indexer_response")
            rows = value.get("result")
            empty = value.get("status") == "0" and value.get("message", "").lower() == "no transactions found" and rows == []
            if not empty and (value.get("status") != "1" or not isinstance(rows, list)):
                raise ProviderError("indexer_error_or_rate_limit")
            if len(rows) > self.settings.page_size:
                raise ProviderError("invalid_indexer_page_size")
            previous = low
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("blockNumber"), str) or not re.fullmatch(r"0|[1-9][0-9]*", row["blockNumber"]):
                    raise ProviderError("invalid_indexer_row")
                number = int(row["blockNumber"])
                hash_value(row["hash"])
                parties = [row.get("from"), row.get("to")]
                if any(value is not None and not isinstance(value, str) for value in parties):
                    raise ProviderError("invalid_indexer_row")
                if not low <= number <= high or number < previous or raw_address.lower() not in [(value or "").lower() for value in parties]:
                    raise ProviderError("indexer_row_outside_scope")
                previous = number
            limits = list(cumulative_limits)
            if len(rows) == self.settings.page_size:
                if page * self.settings.page_size < self.settings.result_cap:
                    tasks[0][3] += 1
                elif low < high:
                    middle = (low + high) // 2
                    tasks[:1] = [[action, low, middle, 1], [action, middle + 1, high, 1]]
                else:
                    # Aucun curseur ne peut récupérer ce qui dépasse le plafond dans un bloc dense.
                    tasks.pop(0)
                    limits.append("indexer_dense_block_truncated")
            else:
                tasks.pop(0)
            limits = list(dict.fromkeys(limits))
            next_cursor = base64.urlsafe_b64encode(json.dumps({"address": address.lower(), "range": block_range.model_dump(), "tasks": tasks, "limits": limits}, separators=(",", ":")).encode()).decode() if tasks else None
            complete = not tasks and not limits
            return self._result(start, data=rows, status=CoverageStatus.COMPLETE if complete else CoverageStatus.PARTIAL,
                limits=limits, block_range=block_range, covered=block_range if complete else None, cursor=next_cursor)
        except (ProviderError, ValueError, KeyError, TypeError, UnicodeDecodeError) as error:
            reason = error.reason if isinstance(error, ProviderError) else "invalid_indexer_cursor_or_response"
            return self._result(start, status=CoverageStatus.UNSUPPORTED if reason in ("indexer_not_configured", "unsupported_chain") else CoverageStatus.PARTIAL, limits=[reason], block_range=block_range)
