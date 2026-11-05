from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from connectors.contracts import UnavailableProvider
from investigation.db import get_session
from investigation.models import (
    AnalysisRun, Asset, Case, CaseSeed, Chain, Observation, Operation,
    OperationMovement, RunOperation, SourceSnapshot,
)
from investigation.schemas import (
    AssetView, CapabilityView, CaseCreate, CaseDetail, CaseView, MovementView,
    ObservationView, OperationView, RunView, SeedView, SnapshotView,
)

app = FastAPI(title="Ariadne — Fondations V0.1", version="0.1.0", description=(
    "Application locale sans authentification. Données synthétiques marquées Démonstration. "
    "Aucune collecte blockchain ni analyse automatique. Ne pas exposer publiquement."
))
Db = Annotated[Session, Depends(get_session)]


def required(session, model, identity):
    result = session.get(model, identity)
    if result is None:
        raise HTTPException(404, "Ressource introuvable")
    return result


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/health/ready")
def ready(session: Db):
    import os
    from redis.exceptions import RedisError
    checks = {"postgres": False, "redis": False, "migration": False}
    try:
        session.execute(text("SELECT 1"))
        checks["postgres"] = True
        checks["migration"] = session.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
    except SQLAlchemyError:
        session.rollback()
    try:
        with Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=2, socket_timeout=2) as redis:
            checks["redis"] = bool(redis.ping())
    except RedisError:
        pass
    return JSONResponse({"status": "ok" if all(checks.values()) else "unavailable", "checks": checks}, status_code=200 if all(checks.values()) else 503)


@app.get("/api/v1/capabilities", response_model=CapabilityView)
def capabilities() -> CapabilityView:
    provider = UnavailableProvider()
    return CapabilityView(
        notice="V0.1 locale · Démonstration synthétique disponible · Aucun réseau réellement collecté",
        providers=[provider.get_capabilities(chain) for chain in ("eip155:1", "eip155:8453", "eip155:42161")],
    )


@app.get("/api/v1/cases", response_model=list[CaseView])
def cases(session: Db, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return session.scalars(select(Case).order_by(Case.created_at, Case.id).offset(offset).limit(limit)).all()


@app.post("/api/v1/cases", response_model=CaseView, status_code=201)
def create_case(body: CaseCreate, session: Db):
    if any(session.get(Chain, seed.chain_id) is None for seed in body.seeds):
        raise HTTPException(422, "Chaîne absente du registre local ; consulter /capabilities")
    case = Case(title=body.title, description=body.description, is_demo=False)
    session.add(case)
    session.flush()
    for seed in body.seeds:
        session.add(CaseSeed(case_id=case.id, **seed.model_dump()))
    session.commit()
    return case


@app.get("/api/v1/cases/{case_id}", response_model=CaseDetail)
def case_detail(case_id: str, session: Db):
    case = required(session, Case, case_id)
    return CaseDetail(
        **CaseView.model_validate(case).model_dump(),
        seeds=[SeedView.model_validate(seed) for seed in session.scalars(select(CaseSeed).where(CaseSeed.case_id == case_id).order_by(CaseSeed.id))],
        runs=[RunView.model_validate(run) for run in session.scalars(select(AnalysisRun).where(AnalysisRun.case_id == case_id).order_by(AnalysisRun.created_at, AnalysisRun.id))],
    )


@app.post("/api/v1/cases/{case_id}/runs", response_model=RunView, status_code=201)
def create_run(case_id: str, session: Db, idempotency_key: Annotated[str, Header(min_length=1, max_length=100)]):
    case = required(session, Case, case_id)
    # Les runs du scénario synthétique sont uniquement chargés depuis le fixture.
    if case.is_demo:
        raise HTTPException(409, "Dossier Démonstration en lecture seule")
    lookup = select(AnalysisRun).where(AnalysisRun.case_id == case_id, AnalysisRun.idempotency_key == idempotency_key)
    existing = session.scalar(lookup)
    if existing:
        return existing
    seeds = [SeedView.model_validate(seed).model_dump() for seed in session.scalars(select(CaseSeed).where(CaseSeed.case_id == case_id).order_by(CaseSeed.id))]
    run = AnalysisRun(
        case_id=case_id, idempotency_key=idempotency_key, state="unsupported",
        coverage_status="unsupported", is_demo=False, seeds_snapshot=seeds,
        parameters={"mode": "snapshot_only", "provider_calls": 0}, block_bounds={},
        allocation_policy="none", decoder_versions={}, label_snapshot=[],
        coverage={"scope": "none", "limits": ["Collecte et analyse non implémentées en V0.1"]},
        stop_reasons=["provider_not_configured", "analysis_not_implemented_v0_1"], manifest=[],
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(lookup)
        if existing:
            return existing
        raise
    return run


@app.get("/api/v1/runs/{run_id}", response_model=RunView)
def run_detail(run_id: str, session: Db):
    return required(session, AnalysisRun, run_id)


def observation_view(session: Session, observation: Observation) -> ObservationView:
    values = {column.name: getattr(observation, column.name) for column in observation.__table__.columns}
    values["amount_raw"] = str(observation.amount_raw)
    values["block_number"] = str(observation.block_number)
    return ObservationView(
        **values, is_demo=required(session, SourceSnapshot, observation.snapshot_id).is_demo,
        asset=AssetView.model_validate(required(session, Asset, observation.asset_id)),
    )


def operation_view(session: Session, operation: Operation) -> OperationView:
    links = session.scalars(select(OperationMovement).where(OperationMovement.operation_id == operation.id).order_by(OperationMovement.observation_id, OperationMovement.role)).all()
    return OperationView(
        **{column.name: getattr(operation, column.name) for column in operation.__table__.columns},
        movements=[MovementView(role=link.role, observation=observation_view(session, required(session, Observation, link.observation_id))) for link in links],
    )


@app.get("/api/v1/runs/{run_id}/operations", response_model=list[OperationView])
def run_operations(run_id: str, session: Db, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    required(session, AnalysisRun, run_id)
    operations = session.scalars(select(Operation).join(RunOperation).where(RunOperation.run_id == run_id).order_by(Operation.id).offset(offset).limit(limit))
    return [operation_view(session, operation) for operation in operations]


@app.get("/api/v1/operations/{operation_id}", response_model=OperationView)
def operation_detail(operation_id: str, session: Db):
    return operation_view(session, required(session, Operation, operation_id))


@app.get("/api/v1/observations/{observation_id}", response_model=ObservationView)
def observation_detail(observation_id: str, session: Db):
    return observation_view(session, required(session, Observation, observation_id))


@app.get("/api/v1/snapshots/{snapshot_id}", response_model=SnapshotView)
def snapshot_detail(snapshot_id: str, session: Db):
    return required(session, SourceSnapshot, snapshot_id)
