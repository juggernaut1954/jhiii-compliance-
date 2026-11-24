from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app

def test_end_to_end():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        e = client.post("/entities", json={"name":"Example Credit Union","industry":"CreditUnion","jurisdiction":"US"} )
        assert e.status_code == 201
        entity_id = e.json()["id"]
        due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        o = client.post("/obligations", json={"entity_id":entity_id,"title":"Review BSA policy","regulation_reference":"DEMO-BSA-001","due_date":due})
        assert o.status_code == 201
        assert o.json()["status"] == "due_soon"
        assert o.json()["risk_score"] == 0.7
        assert client.post("/refresh").status_code == 200
        snapshot = client.get("/state_snapshot").json()
        assert any(item["entity_id"] == entity_id for item in snapshot["obligations"])
        export = client.get("/audit_export").json()
        assert any(item["id"] == entity_id for item in export["entities"])
        assert export["notice"].startswith("DEMONSTRATION")
