from datetime import datetime
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, Field, model_validator
from investigation.domain import CoverageStatus, validate_chain

T = TypeVar("T")


class BlockRange(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Plage de blocs inversée")
        return self


class Capabilities(BaseModel):
    provider: str
    chain_id: str
    status: CoverageStatus = CoverageStatus.UNSUPPORTED
    address_history: bool = False
    transaction_bundle: bool = False
    logs: bool = False
    traces: bool = False
    pagination: str | None = None
    available_blocks: BlockRange | None = None
    finality_policy: str = "unknown"
    quota: str = "non configuré"
    cost: str = "inconnu"
    protocols: list[str] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=lambda: ["Aucun fournisseur réel en V0.1"])


class ProviderResult(BaseModel, Generic[T]):
    data: T | None = None
    source: str
    retrieved_at: datetime
    chain_id: str
    status: CoverageStatus
    requested_range: BlockRange | None = None
    covered_range: BlockRange | None = None
    cursor: str | None = None
    limits: list[str] = Field(default_factory=list)
    finality: dict = Field(default_factory=lambda: {"status": "unknown"})
    evidence_refs: list[str] = Field(default_factory=list)


class BlockchainProvider(Protocol):
    def get_capabilities(self, chain: str) -> Capabilities: ...
    def discover_address_activity(self, address: str, block_range: BlockRange, cursor: str | None = None) -> ProviderResult[list[dict]]: ...
    def get_transaction_bundle(self, chain: str, tx_hash: str) -> ProviderResult[dict]: ...
    def get_logs(self, chain: str, filter: dict, cursor: str | None = None) -> ProviderResult[list[dict]]: ...
    def get_chain_head_and_finality(self, chain: str) -> ProviderResult[dict]: ...


class UnavailableProvider:
    """Réponse explicite ; ne confond jamais indisponibilité et historique vide."""
    def get_capabilities(self, chain: str) -> Capabilities:
        return Capabilities(provider="unconfigured", chain_id=validate_chain(chain))

    def _result(self, chain: str, block_range=None, cursor=None):
        from datetime import timezone
        return ProviderResult(
            source="unconfigured", retrieved_at=datetime.now(timezone.utc),
            chain_id=validate_chain(chain), status=CoverageStatus.UNSUPPORTED,
            requested_range=block_range, cursor=cursor,
            limits=["V0.1 : collecte non implémentée ; aucune donnée réelle récupérée"],
        )

    def discover_address_activity(self, address: str, block_range: BlockRange, cursor=None):
        chain = address.rsplit(":", 1)[0]
        return self._result(chain, block_range, cursor)

    def get_transaction_bundle(self, chain: str, tx_hash: str):
        return self._result(chain)

    def get_logs(self, chain: str, filter: dict, cursor=None):
        return self._result(chain, cursor=cursor)

    def get_chain_head_and_finality(self, chain: str):
        return self._result(chain)
