from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, WithJsonSchema, field_validator, model_validator
from investigation.domain import AddressId, CoverageStatus, parse_amount, validate_chain

Amount = Annotated[
    int, BeforeValidator(parse_amount),
    PlainSerializer(lambda value: str(value), return_type=str),
    WithJsonSchema({"type": "string", "pattern": "^(0|[1-9][0-9]{0,77})$", "description": "uint256 exact, chaîne décimale"}),
]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SeedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chain_id: str
    kind: Literal["transaction", "address"]
    reference: str = Field(max_length=180)
    window: dict[str, str] = Field(default_factory=dict)

    @field_validator("chain_id")
    @classmethod
    def chain(cls, value):
        return validate_chain(value)

    @model_validator(mode="after")
    def validate_reference(self):
        import re
        if not self.chain_id.startswith("eip155:"):
            raise ValueError("Graines non EVM non prises en charge en V0.1")
        if self.kind == "address":
            self.reference = AddressId.evm(self.chain_id, self.reference).key
            if set(self.window) != {"start", "end"}:
                raise ValueError("Une adresse exige une période start/end ISO 8601")
            try:
                start, end = (datetime.fromisoformat(self.window[key]) for key in ("start", "end"))
                if start.tzinfo is None or end.tzinfo is None or end < start:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError("Période ordonnée avec fuseaux horaires attendue") from None
        elif not re.fullmatch(r"0x[0-9a-fA-F]{64}", self.reference):
            raise ValueError("Hash de transaction EVM attendu")
        else:
            self.reference = self.reference.lower()
        return self


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    seeds: list[SeedInput] = Field(min_length=1, max_length=10)


class CaseView(ReadModel):
    id: str
    title: str
    description: str
    created_at: datetime
    is_demo: bool


class SeedView(ReadModel):
    id: str
    chain_id: str
    kind: str
    reference: str
    observation_id: str | None
    window: dict


class RunView(ReadModel):
    id: str
    case_id: str
    created_at: datetime
    state: str
    coverage_status: CoverageStatus
    is_demo: bool
    seeds_snapshot: list[dict]
    parameters: dict
    block_bounds: dict
    allocation_policy: str
    decoder_versions: dict
    label_snapshot: list
    coverage: dict
    stop_reasons: list[str]
    manifest: list[dict]


class CaseDetail(CaseView):
    seeds: list[SeedView]
    runs: list[RunView]


class AssetView(ReadModel):
    id: str
    chain_id: str
    symbol: str | None
    decimals: int | None
    metadata_source: str


class ObservationView(ReadModel):
    id: str
    chain_id: str
    block_number: str
    block_hash: str
    parent_hash: str
    tx_hash: str
    transaction_index: int
    origin: str
    position: str
    observed_at: datetime
    canonicality: str
    finality: dict
    source_address_id: str
    target_address_id: str
    asset_id: str
    amount_raw: Amount
    snapshot_id: str
    evidence_ref: str
    is_demo: bool
    asset: AssetView


class MovementView(BaseModel):
    role: str
    observation: ObservationView


class OperationView(ReadModel):
    id: str
    kind: str
    protocol: str | None
    decoder_version: str
    decoding_status: str
    evidence_refs: list[str]
    is_demo: bool
    movements: list[MovementView]


class SnapshotView(ReadModel):
    id: str
    source: str
    retrieved_at: datetime
    is_demo: bool
    content: dict
    sha256: str
    coverage: dict


class CapabilityView(BaseModel):
    version: Literal["0.1.0"] = "0.1.0"
    mode: Literal["local_foundation"] = "local_foundation"
    notice: str
    providers: list["Capabilities"]


from connectors.contracts import Capabilities
CapabilityView.model_rebuild()
