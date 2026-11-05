"""Capture explicite de trois transactions publiques ; jamais utilisée par l'application.

CORPUS_RPC_URL (ou ETHEREUM_RPC_URL) est obligatoire. Les réponses conservées
doivent être revues avant de modifier le corpus et ses résultats attendus.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from connectors.ethereum import CHAIN, TRANSFER_TOPIC, EthereumProvider, EthereumSettings, hex_int
from connectors.transport import Budget


def main():
    url = os.getenv("CORPUS_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
    if not url:
        raise SystemExit("Configurer CORPUS_RPC_URL ; aucune source publique implicite")
    provider = EthereumProvider(EthereumSettings(rpc_url=url), budget=Budget(max_calls=120, max_seconds=180))
    try:
        provider.ensure_chain(CHAIN)
        number = int(os.getenv("CORPUS_BLOCK_NUMBER", "0")) or (hex_int(provider.call("eth_blockNumber", [])) - 128)
        block = provider.call("eth_getBlockByNumber", [hex(number), True])
        receipts = {item["transactionHash"]: item for item in provider.call("eth_getBlockReceipts", [hex(number)])}
        selected = {}
        for transaction in block["transactions"]:
            receipt = receipts.get(transaction["hash"])
            if receipt is None:
                continue
            if receipt["status"] == "0x0":
                selected.setdefault("failed", transaction["hash"])
            elif hex_int(transaction["value"]) > 0 and not receipt["logs"]:
                selected.setdefault("native", transaction["hash"])
            elif any(len(log["topics"]) == 3 and log["topics"][0].lower() == TRANSFER_TOPIC for log in receipt["logs"]):
                selected.setdefault("erc20", transaction["hash"])
            if len(selected) == 3:
                break
        if len(selected) != 3:
            raise SystemExit(f"Corpus incomplet : bloc {number}, {len(block['transactions'])} transactions, types {list(selected)} ; aucune fixture inventée")
        target = Path("tests/fixtures/ethereum")
        target.mkdir(parents=True, exist_ok=True)
        for name, tx_hash in selected.items():
            result = provider.get_transaction_bundle(CHAIN, tx_hash)
            if result.data is None:
                raise SystemExit(f"Capture {name} incomplète : {result.limits}")
            content = {
                "kind": "public_chain_snapshot", "chain_id": CHAIN,
                "source_host": urlsplit(url).hostname, "retrieved_at": result.retrieved_at.isoformat(),
                "transaction_hash": tx_hash, "bundle": result.data,
                "artifacts": [artifact.model_dump(mode="json") for artifact in result.artifacts],
            }
            (target / f"{name}.json").write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(name, tx_hash, "value", result.data["transaction"]["value"], "logs", len(result.data["receipt"]["logs"]))
    finally:
        provider.close()


if __name__ == "__main__":
    main()
