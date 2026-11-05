"""La suite hors ligne ne doit jamais utiliser les secrets ou fournisseurs de l'hôte."""
import pytest


@pytest.fixture(autouse=True)
def isolated_provider_configuration(monkeypatch):
    monkeypatch.delenv("ETHEREUM_RPC_URL", raising=False)
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
