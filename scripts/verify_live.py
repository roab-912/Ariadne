"""Vérification RPC explicite du corpus public ; hors CI et sans écriture en base."""
import json
import os
from pathlib import Path

from connectors.ethereum import CHAIN, EthereumProvider, EthereumSettings
from investigation.normalization import normalize_bundle


def main():
    url = os.getenv("LIVE_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
    if not url:
        raise SystemExit("Configurer LIVE_RPC_URL ou ETHEREUM_RPC_URL pour ce contrôle explicite")
    expected = json.loads(Path("tests/fixtures/ethereum/expected.json").read_text(encoding="utf-8"))
    provider = EthereumProvider(EthereumSettings(rpc_url=url))
    try:
        head = provider.get_chain_head_and_finality(CHAIN)
        if head.data is None:
            raise SystemExit(f"RPC indisponible : {head.limits}")
        for name in ("native", "erc20", "failed"):
            result = provider.get_transaction_bundle(CHAIN, expected[name]["transaction_hash"])
            if result.data is None:
                raise SystemExit(f"{name} : collecte incomplète {result.limits}")
            actual = normalize_bundle(result.data, expected[name]["transaction_hash"])
            movements = [{"origin": item.origin, "position": item.position, "amount_raw": str(item.amount),
                "asset_id": item.asset, "from": item.source.rsplit(":", 1)[1], "to": item.target.rsplit(":", 1)[1]}
                for item in actual.movements]
            if movements != expected[name]["movements"] or actual.transaction_status != expected[name]["status"] or actual.block_hash != expected["block_hash"]:
                raise SystemExit(f"{name} : divergence avec le corpus revu ; inspection nécessaire")
            print(f"{name}: OK, {len(movements)} mouvement(s), statut reçu {actual.transaction_status}")
        print(f"RPC live vérifié : {provider.http.budget.calls} appels, {provider.http.budget.bytes_received} octets ; aucun appel d'indexeur")
    finally:
        provider.close()


if __name__ == "__main__":
    main()
