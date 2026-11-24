# JH III COMPLIANCE — ARA banking demonstration

**Prototype only. Do not deploy publicly or enter real customer data.** This demonstration has no authentication, tenant isolation, encryption at rest, regulatory-content verification, evidence management, or tamper-evident audit trail.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs to create an entity and obligation, run `/refresh`, and inspect `/audit_export`.

Default storage is local SQLite (`ara_demo.db`), intentionally ignored by Git. For PostgreSQL set `DATABASE_URL` and install an appropriate SQLAlchemy PostgreSQL driver.

## Tests

```bash
pip install pytest httpx
pytest -q
```

This is a **new, separately developed demonstration**, not the recovered original source. It contains manually entered regulatory references and deadline-based demonstration scores; it does not perform AML screening, transaction monitoring, regulatory ingestion, or compliance certification. `/refresh` is manual, not scheduled. The audit endpoint returns JSON rather than a signed evidence package.

## Production blockers

Authentication and authorization; tenant isolation; validated regulatory content; evidence custody and retention; migrations; secrets management; audit integrity; robust error handling; security review; legal/compliance review; monitoring; background scheduling; production database and backups.
