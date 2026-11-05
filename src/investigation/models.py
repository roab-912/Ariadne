"""Schéma V0.1. Aucune collecte, attribution ou allocation automatique."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Integer, LargeBinary, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from investigation.domain import UINT256_MAX, uint256


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class UInt256(TypeDecorator):
    """Entier Python ↔ NUMERIC(78,0), sans passage par un flottant."""
    impl = Numeric(78, 0)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else Decimal(uint256(value))

    def process_result_value(self, value, dialect):
        return None if value is None else int(value)


class Base(DeclarativeBase):
    pass


class Chain(Base):
    __tablename__ = "chains"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    family: Mapped[str] = mapped_column(String(32))


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        UniqueConstraint("chain_id", "value"), UniqueConstraint("id", "chain_id"),
        CheckConstraint("length(value) = 20", name="address_evm_length"),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    chain_id: Mapped[str] = mapped_column(ForeignKey("chains.id"))
    value: Mapped[bytes] = mapped_column(LargeBinary)
    display: Mapped[str] = mapped_column(String(100))


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("id", "chain_id"),
        CheckConstraint("decimals IS NULL OR (decimals >= 0 AND decimals <= 255)", name="asset_decimals"),
    )
    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    chain_id: Mapped[str] = mapped_column(ForeignKey("chains.id"))
    contract_address: Mapped[bytes | None] = mapped_column(LargeBinary)
    symbol: Mapped[str | None] = mapped_column(String(64))
    decimals: Mapped[int | None] = mapped_column(Integer)
    metadata_source: Mapped[str] = mapped_column(String(200))


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(200))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[dict] = mapped_column(JSON)
    sha256: Mapped[str] = mapped_column(String(64))
    coverage: Mapped[dict] = mapped_column(JSON)


class Observation(Base):
    """Mouvement observé : son inclusion est identifiée par le hash de bloc."""
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("chain_id", "block_hash", "tx_hash", "origin", "position"),
        UniqueConstraint("id", "chain_id"),
        ForeignKeyConstraint(["source_address_id", "chain_id"], ["addresses.id", "addresses.chain_id"]),
        ForeignKeyConstraint(["target_address_id", "chain_id"], ["addresses.id", "addresses.chain_id"]),
        ForeignKeyConstraint(["asset_id", "chain_id"], ["assets.id", "assets.chain_id"]),
        CheckConstraint(f"amount_raw >= 0 AND amount_raw <= {UINT256_MAX}", name="observation_uint256"),
        CheckConstraint("block_number >= 0 AND transaction_index >= 0", name="observation_order"),
        CheckConstraint("origin IN ('top_level', 'trace', 'log')", name="observation_origin"),
        CheckConstraint("canonicality IN ('canonical', 'orphaned', 'unknown')", name="observation_canonicality"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    chain_id: Mapped[str] = mapped_column(ForeignKey("chains.id"), index=True)
    block_number: Mapped[int] = mapped_column(Numeric(20, 0))
    block_hash: Mapped[str] = mapped_column(String(66))
    parent_hash: Mapped[str] = mapped_column(String(66))
    tx_hash: Mapped[str] = mapped_column(String(66), index=True)
    transaction_index: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16))
    position: Mapped[str] = mapped_column(String(100))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    canonicality: Mapped[str] = mapped_column(String(16))
    finality: Mapped[dict] = mapped_column(JSON)
    source_address_id: Mapped[str] = mapped_column(String(160))
    target_address_id: Mapped[str] = mapped_column(String(160))
    asset_id: Mapped[str] = mapped_column(String(180))
    amount_raw: Mapped[int] = mapped_column(UInt256())
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("source_snapshots.id"))
    evidence_ref: Mapped[str] = mapped_column(String(200))


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(40))
    protocol: Mapped[str | None] = mapped_column(String(100))
    decoder_version: Mapped[str] = mapped_column(String(100))
    decoding_status: Mapped[str] = mapped_column(String(32))
    evidence_refs: Mapped[list] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class OperationMovement(Base):
    __tablename__ = "operation_movements"
    __table_args__ = (CheckConstraint("role IN ('input', 'output', 'transfer', 'fee')", name="movement_role"),)
    operation_id: Mapped[str] = mapped_column(ForeignKey("operations.id"), primary_key=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class CaseSeed(Base):
    __tablename__ = "case_seeds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    chain_id: Mapped[str] = mapped_column(ForeignKey("chains.id"))
    kind: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str] = mapped_column(String(180))
    observation_id: Mapped[str | None] = mapped_column(ForeignKey("observations.id"))
    window: Mapped[dict] = mapped_column(JSON)


class AnalysisRun(Base):
    """Snapshot durable ; aucun calcul/worker d'analyse en V0.1."""
    __tablename__ = "analysis_runs"
    __table_args__ = (UniqueConstraint("case_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    state: Mapped[str] = mapped_column(String(32))
    coverage_status: Mapped[str] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    seeds_snapshot: Mapped[list] = mapped_column(JSON)
    parameters: Mapped[dict] = mapped_column(JSON)
    block_bounds: Mapped[dict] = mapped_column(JSON)
    allocation_policy: Mapped[str] = mapped_column(String(100))
    decoder_versions: Mapped[dict] = mapped_column(JSON)
    label_snapshot: Mapped[list] = mapped_column(JSON)
    coverage: Mapped[dict] = mapped_column(JSON)
    stop_reasons: Mapped[list] = mapped_column(JSON)
    manifest: Mapped[list] = mapped_column(JSON)


class RunOperation(Base):
    __tablename__ = "run_operations"
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), primary_key=True)
    operation_id: Mapped[str] = mapped_column(ForeignKey("operations.id"), primary_key=True)


class LabelAssertion(Base):
    """Contrat réservé ; aucune attribution n'est produite en V0.1."""
    __tablename__ = "label_assertions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subject_address_id: Mapped[str] = mapped_column(ForeignKey("addresses.id"))
    predicate: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(200))
    evidence_ref: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    method: Mapped[str] = mapped_column(String(200))
    review_status: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(100))
    author: Mapped[str | None] = mapped_column(String(200))


class Allocation(Base):
    """Résultat analytique lié à un run, jamais stocké dans une observation."""
    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint(f"amount_raw >= 0 AND amount_raw <= {UINT256_MAX}", name="allocation_uint256"),
        UniqueConstraint("run_id", "observation_id", "policy_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"))
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.id"))
    amount_raw: Mapped[int] = mapped_column(UInt256())
    policy_version: Mapped[str] = mapped_column(String(100))
    rationale: Mapped[str] = mapped_column(String(2000))
