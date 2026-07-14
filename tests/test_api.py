import os
from pathlib import Path
os.environ["DATABASE_PATH"] = "work/test-agent.db"
from fastapi.testclient import TestClient
from app.main import app

def payload():
    return {"tenant_id":"empresa-teste","business_name":"Empresa Teste","niche":"general","assistant_name":"Lia","tone":"cordial","objective":"Responder clientes e qualificar oportunidades","forbidden_topics":["jurídico"]}

def test_onboarding_and_handoff():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status":"ok"}
        assert client.post("/v1/tenants", json=payload()).status_code == 200
        response=client.post("/v1/tenants/empresa-teste/messages",json={"text":"Questão jurídica","contact_id":"5511999999999"})
        assert response.status_code == 200
        assert response.json()["handoff_required"] is True

def test_unknown_niche():
    with TestClient(app) as client:
        assert client.post("/v1/tenants",json=payload()|{"tenant_id":"outro-cliente","niche":"x"}).status_code == 422

def teardown_module():
    Path("work/test-agent.db").unlink(missing_ok=True)
