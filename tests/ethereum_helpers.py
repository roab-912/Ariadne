"""Rejeu des pièces publiques via MockTransport, uniquement pour les tests."""
import json
from copy import deepcopy
from pathlib import Path

import httpx
from connectors.ethereum import EthereumProvider, EthereumSettings
from connectors.transport import Budget

FIXTURES = Path(__file__).parent / "fixtures" / "ethereum"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def replay_provider(*, index_handler=None, rpc_handler=None, settings=None, budget=None):
    captures = [fixture(name) for name in ("native", "erc20", "failed")]
    bundles = {item["transaction_hash"]: item["bundle"] for item in captures}
    block = captures[0]["bundle"]["block"]

    def handler(request):
        if request.method == "GET":
            if index_handler:
                return index_handler(request)
            return httpx.Response(200, json={"status": "0", "message": "No transactions found", "result": []})
        body = json.loads(request.content)
        if rpc_handler:
            response = rpc_handler(body)
            if response is not None:
                return response
        method, params = body["method"], body["params"]
        result = None
        if method == "eth_chainId":
            result = "0x1"
        elif method == "eth_getTransactionByHash":
            result = deepcopy(bundles.get(params[0], {}).get("transaction"))
        elif method == "eth_getTransactionReceipt":
            result = deepcopy(bundles.get(params[0], {}).get("receipt"))
        elif method in ("eth_getBlockByHash", "eth_getBlockByNumber"):
            result = deepcopy(block)
        elif method == "eth_call":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32000, "message": "historical state unavailable"}})
        elif method == "eth_getLogs":
            result = []
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    return EthereumProvider(settings or EthereumSettings(rpc_url="https://rpc.test", etherscan_api_key="TEST_SECRET", index_interval=0),
        transport=httpx.MockTransport(handler), budget=budget or Budget())
