
import os
import secrets

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, SessionLocal
from .models import Entity, Obligation
from .schemas import EntityIn, ObligationIn
from .risk_engine import evaluate


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="JH III Compliance ARA — Demonstration",
    version="0.2.0",
    lifespan=lifespan
)


api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False
)


def require_api_key(
    api_key: str | None = Depends(api_key_header)
):
    expected_key = os.getenv("ARA_API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="API authentication is not configured"
        )

    if not api_key or not secrets.compare_digest(
        api_key.encode("utf-8"),
        expected_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )


def db_session():
    with SessionLocal() as db:
        yield db


def entity_out(e):
    return {
        "id": e.id,
        "name": e.name,
        "industry": e.industry,
        "jurisdiction": e.jurisdiction
    }


def obligation_out(o):
    return {
        "id": o.id,
        "entity_id": o.entity_id,
        "title": o.title,
        "regulation_reference": o.regulation_reference,
        "due_date": o.due_date.isoformat(),
        "status": o.status,
        "risk_score": o.risk_score
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": "demo"
    }


@app.post(
    "/entities",
    status_code=201,
    dependencies=[Depends(require_api_key)]
)
def create_entity(
    data: EntityIn,
    db: Session = Depends(db_session)
):
    e = Entity(**data.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return entity_out(e)


@app.get(
    "/entities",
    dependencies=[Depends(require_api_key)]
)
def list_entities(
    db: Session = Depends(db_session)
):
    return [
        entity_out(e)
        for e in db.scalars(
            select(Entity).order_by(Entity.id)
        ).all()
    ]


@app.post(
    "/obligations",
    status_code=201,
    dependencies=[Depends(require_api_key)]
)
def create_obligation(
    data: ObligationIn,
    db: Session = Depends(db_session)
):
    if not db.get(Entity, data.entity_id):
        raise HTTPException(
            status_code=404,
            detail="Entity not found"
        )

    status, score = evaluate(data.due_date)

    o = Obligation(
        **data.model_dump(),
        status=status,
        risk_score=score
    )

    db.add(o)
    db.commit()
    db.refresh(o)

    return obligation_out(o)


@app.get(
    "/obligations",
    dependencies=[Depends(require_api_key)]
)
def list_obligations(
    entity_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(db_session)
):
    query = select(Obligation)

    if entity_id is not None:
        if not db.get(Entity, entity_id):
            raise HTTPException(
                status_code=404,
                detail="Entity not found"
            )

        query = query.where(
            Obligation.entity_id == entity_id
        )

    query = query.order_by(Obligation.id)

    return [
        obligation_out(o)
        for o in db.scalars(query).all()
    ]


@app.get(
    "/obligations/{obligation_id}",
    dependencies=[Depends(require_api_key)]
)
def get_obligation(
    obligation_id: int,
    db: Session = Depends(db_session)
):
    obligation = db.get(
        Obligation,
        obligation_id
    )

    if not obligation:
        raise HTTPException(
            status_code=404,
            detail="Obligation not found"
        )

    return obligation_out(obligation)


@app.post(
    "/refresh",
    dependencies=[Depends(require_api_key)]
)
def refresh(
    db: Session = Depends(db_session)
):
    changed = 0

    for o in db.scalars(
        select(Obligation)
    ).all():

        status, score = evaluate(o.due_date)

        if (o.status, o.risk_score) != (status, score):
            o.status = status
            o.risk_score = score
            changed += 1

    db.commit()

    return {
        "evaluated": db.query(Obligation).count(),
        "changed": changed
    }


@app.get(
    "/state_snapshot",
    dependencies=[Depends(require_api_key)]
)
def state_snapshot(
    db: Session = Depends(db_session)
):
    return {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "obligations": [
            obligation_out(o)
            for o in db.scalars(
                select(Obligation).order_by(
                    Obligation.id
                )
            ).all()
        ]
    }


@app.get(
    "/audit_export",
    dependencies=[Depends(require_api_key)]
)
def audit_export(
    db: Session = Depends(db_session)
):
    return {
        "notice": (
            "DEMONSTRATION ONLY — "
            "not regulator-certified or audit-ready"
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "entities": [
            entity_out(e)
            for e in db.scalars(
                select(Entity)
            ).all()
        ],
        "obligations": [
            obligation_out(o)
            for o in db.scalars(
                select(Obligation)
            ).all()
        ]
    }
