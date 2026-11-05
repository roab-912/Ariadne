import json
from copy import deepcopy

import httpx
import pytest

from connectors.contracts import BlockRange
from connectors.ethereum import CHAIN, EthereumProvider, EthereumSettings
from connectors.transport import Budget
from investigation.normalization import InvalidBundle, normalize_bundle
from tests.ethereum_helpers import fixture, replay_provider


@pytest.mark.parametrize("name", ["native", "erc20", "failed"])
def test_public_corpus_exact_normalization(name):
    capture, expected = fixture(name), fixture("expected")
    normalized = normalize_bundle(capture["bundle"], capture["transaction_hash"])
    assert capture["kind"] == "public_chain_snapshot"
    assert str(normalized.block_number) == expected["block_number"]
    assert normalized.block_hash == expected["block_hash"]
    assert normalized.transaction_status == expected[name]["status"]
    assert [{"origin": item.origin, "position": item.position, "amount_raw": str(item.amount), "asset_id": item.asset,
             "from": item.source.rsplit(":", 1)[1], "to": item.target.rsplit(":", 1)[1]} for item in normalized.movements] == expected[name]["movements"]
    if name == "failed":
        assert int(capture["bundle"]["transaction"]["value"], 16) > 0
        assert normalized.movements == []
    if name == "erc20":
        assert all(item.metadata["decimals"] is None for item in normalized.movements)


@pytest.mark.parametrize("mutate", [
    lambda data: data["receipt"].update(transactionHash="0x" + "aa" * 32),
    lambda data: data["canonical_block"].update(hash="0x" + "aa" * 32),
    lambda data: data["receipt"]["logs"][0].update(removed=True),
    lambda data: data["receipt"]["logs"].append(deepcopy(data["receipt"]["logs"][0])),
    lambda data: data["block"].update(transactions=[]),
    lambda data: data["receipt"].update(status="0x0"),
])
def test_inconsistent_or_reverted_pieces_are_never_normalized(mutate):
    capture = fixture("erc20")
    mutate(capture["bundle"])
    with pytest.raises(InvalidBundle):
        normalize_bundle(capture["bundle"], capture["transaction_hash"])


def test_zero_erc20_transfer_and_erc721_are_distinguished():
    capture = fixture("erc20")
    log = capture["bundle"]["receipt"]["logs"][0]
    log["data"] = "0x" + "00" * 32
    value = normalize_bundle(capture["bundle"], capture["transaction_hash"])
    assert value.movements[0].amount == 0
    log["topics"].append("0x" + "00" * 32)
    log["data"] = "0x"
    value = normalize_bundle(capture["bundle"], capture["transaction_hash"])
    assert len(value.movements) == 3


def test_pending_and_wrong_chain_have_no_bundle():
    provider = replay_provider(rpc_handler=lambda body: httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": "0x2105"}) if body["method"] == "eth_chainId" else None)
    result = provider.get_transaction_bundle(CHAIN, fixture("native")["transaction_hash"])
    assert result.data is None and result.limits == ["rpc_chain_mismatch"]
    assert provider.http.budget.calls == 1
    provider.close()


@pytest.mark.parametrize("failure,reason", [("timeout", "provider_timeout"), (429, "provider_rate_limited"), (302, "provider_http_error")])
def test_provider_failures_are_explicit_and_not_empty_complete(failure, reason):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("do not expose https://rpc.test/SECRET")
        return httpx.Response(failure)
    provider = EthereumProvider(EthereumSettings(rpc_url="https://rpc.test/SECRET"), transport=httpx.MockTransport(handler))
    result = provider.get_transaction_bundle(CHAIN, fixture("native")["transaction_hash"])
    assert result.data is None and reason in result.limits
    assert "SECRET" not in result.model_dump_json()
    provider.close()


def test_call_and_response_budgets():
    provider = replay_provider(budget=Budget(max_calls=1))
    result = provider.get_transaction_bundle(CHAIN, fixture("native")["transaction_hash"])
    assert result.data is None and result.limits == ["call_budget_exhausted"]
    assert provider.http.budget.calls == 1
    provider.close()
    provider = replay_provider(budget=Budget(max_bytes=1))
    assert provider.get_chain_head_and_finality(CHAIN).data is None
    provider.close()


def index_row(block=10, digit="a", address="0x" + "11" * 20):
    return {"hash": "0x" + digit * 64, "blockNumber": str(block), "from": address, "to": "0x" + "22" * 20}


def test_indexer_paginates_both_streams_and_checks_empty_page():
    seen = []
    def index(request):
        params = request.url.params
        seen.append((params["action"], params["page"]))
        rows = [index_row(), index_row(digit="b")] if params["action"] == "txlist" and params["page"] == "1" else []
        return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})
    provider = replay_provider(index_handler=index, settings=EthereumSettings(rpc_url="https://rpc.test", etherscan_api_key="secret", page_size=2, index_interval=0))
    cursor = None
    results = []
    while True:
        result = provider.discover_address_activity("eip155:1:0x" + "11" * 20, BlockRange(start=10, end=11), cursor)
        results.append(result)
        cursor = result.cursor
        if not cursor:
            break
    assert seen == [("txlist", "1"), ("txlist", "2"), ("tokentx", "1")]
    assert results[0].status.value == "partial" and results[0].covered_range is None
    assert results[-1].status.value == "complete_within_declared_scope"
    assert results[-1].covered_range == BlockRange(start=10, end=11)
    assert "secret" not in "".join(item.model_dump_json() for item in results)
    provider.close()


def test_indexer_subdivides_on_cap_and_preserves_dense_block_truncation():
    requests = []
    def index(request):
        params = request.url.params
        low, high = int(params["startblock"]), int(params["endblock"])
        requests.append((params["action"], low, high))
        rows = [index_row(10), index_row(10, "b")] if params["action"] == "txlist" and low == 10 else []
        return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})
    provider = replay_provider(index_handler=index, settings=EthereumSettings(rpc_url="https://rpc.test", etherscan_api_key="secret", page_size=2, result_cap=2, index_interval=0))
    cursor, statuses = None, []
    for _ in range(10):
        result = provider.discover_address_activity("eip155:1:0x" + "11" * 20, BlockRange(start=10, end=11), cursor)
        statuses.append(result)
        cursor = result.cursor
        if not cursor:
            break
    assert ("txlist", 10, 10) in requests and ("txlist", 11, 11) in requests
    assert "indexer_dense_block_truncated" in statuses[-1].limits
    assert statuses[-1].status.value == "partial" and statuses[-1].covered_range is None
    provider.close()


@pytest.mark.parametrize("payload", [
    {"status": "0", "message": "NOTOK", "result": "Max rate limit reached secret"},
    {"status": "0", "message": "No transactions found", "result": "[]"},
    {"status": "1", "message": "OK", "result": [index_row(9)]},
    {"status": "1", "message": "OK", "result": [{**index_row(), "from": 42}]},
])
def test_indexer_errors_and_out_of_range_rows_do_not_claim_complete(payload):
    provider = replay_provider(index_handler=lambda request: httpx.Response(200, json=payload),
        settings=EthereumSettings(rpc_url="https://rpc.test", etherscan_api_key="secret", index_interval=0))
    result = provider.discover_address_activity("eip155:1:0x" + "11" * 20, BlockRange(start=10, end=11))
    assert result.data is None and result.status.value == "partial" and result.limits
    assert "secret" not in result.model_dump_json()
    provider.close()


def test_logs_require_bounded_range_and_no_secret_in_capabilities():
    provider = replay_provider()
    result = provider.get_logs(CHAIN, {"fromBlock": "0xa", "toBlock": "latest"})
    assert result.data is None and provider.http.budget.calls == 0
    assert provider.get_logs(CHAIN, {"fromBlock": "0xa", "toBlock": "0xb"}).data == []
    assert provider.get_capabilities("eip155:8453").status.value == "unsupported"
    assert "TEST_SECRET" not in provider.get_capabilities(CHAIN).model_dump_json()
    provider.close()


def test_inconsistent_finality_is_not_claimed():
    block = fixture("native")["bundle"]["block"]
    def rpc(body):
        if body["method"] == "eth_getBlockByNumber" and body["params"][0] == "finalized":
            value = {**block, "number": hex(int(block["number"], 16) + 1)}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": value})
    provider = replay_provider(rpc_handler=rpc)
    result = provider.get_chain_head_and_finality(CHAIN)
    assert "finalized" not in result.data and "inconsistent_finality_heads" in result.limits
    assert result.status.value == "partial"
    provider.close()


def test_credentials_in_rpc_path_and_query_are_redacted_in_remote_errors():
    def handler(request):
        payload = json.loads(request.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32000,
            "message": "Invalid key PRIVATE_RPC_KEY, query OTHER_SECRET"}})
    provider = EthereumProvider(EthereumSettings(rpc_url="https://rpc.test/v2/PRIVATE_RPC_KEY?token=OTHER_SECRET"),
                                transport=httpx.MockTransport(handler))
    result = provider.get_transaction_bundle(CHAIN, fixture("native")["transaction_hash"])
    assert result.data is None
    assert "PRIVATE_RPC_KEY" not in result.model_dump_json() and "OTHER_SECRET" not in result.model_dump_json()
    provider.close()
