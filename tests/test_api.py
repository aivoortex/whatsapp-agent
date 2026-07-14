import os
from pathlib import Path

os.environ["DATABASE_PATH"] = "work/test-agent-v2.db"

from fastapi.testclient import TestClient

from app.knowledge import retrieve
from app.main import app


def tenant_payload(tenant_id="empresa-teste"):
    return {
        "tenant_id": tenant_id,
        "business_name": "Empresa Teste",
        "niche": "general",
        "assistant_name": "Lia",
        "tone": "cordial e natural",
        "objective": "Responder clientes e qualificar oportunidades",
        "forbidden_topics": ["jurídico"],
        "lead_qualification_fields": [
            {"name": "name", "label": "Nome", "question": "Como você gostaria de ser chamado?"},
            {"name": "email", "label": "E-mail", "question": "Qual é o melhor e-mail para contato?"},
        ],
    }


def test_health_onboarding_and_handoff():
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["status"] == "ok"
        assert health["version"] == "0.2.0"
        assert client.post("/v1/tenants", json=tenant_payload()).status_code == 200
        response = client.post(
            "/v1/tenants/empresa-teste/messages",
            json={"text": "Tenho uma questão jurídica", "contact_id": "5511999999999"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["handoff_required"] is True
        assert body["trace_id"]
        assert body["suggested_actions"][0]["type"] == "handoff"


def test_progressive_qualification_and_contact_memory():
    with TestClient(app) as client:
        client.post("/v1/tenants", json=tenant_payload("empresa-vendas"))
        response = client.post(
            "/v1/tenants/empresa-vendas/messages",
            json={"text": "Quero comprar. Meu nome é Ana", "contact_id": "contato-ana"},
        )
        body = response.json()
        assert body["intent"] == "sales"
        assert body["captured_fields"]["name"] == "Ana"
        assert "email" in body["missing_fields"]
        context = client.get("/v1/tenants/empresa-vendas/contacts/contato-ana").json()
        assert context["profile"]["name"] == "Ana"


def test_idempotent_webhook_message():
    with TestClient(app) as client:
        client.post("/v1/tenants", json=tenant_payload("empresa-idempotente"))
        request = {"text": "Quero saber o preço", "contact_id": "lead-1", "message_id": "wamid.123"}
        first = client.post("/v1/tenants/empresa-idempotente/messages", json=request).json()
        second = client.post("/v1/tenants/empresa-idempotente/messages", json=request).json()
        assert first == second
        context = client.get("/v1/tenants/empresa-idempotente/contacts/lead-1").json()
        assert len(context["recent_messages"]) == 2


def test_feedback_analytics_and_handoff_context():
    with TestClient(app) as client:
        client.post("/v1/tenants", json=tenant_payload("empresa-metricas"))
        result = client.post(
            "/v1/tenants/empresa-metricas/messages",
            json={"text": "Quero falar com um humano", "contact_id": "lead-2"},
        ).json()
        feedback = client.post(
            f"/v1/tenants/empresa-metricas/messages/{result['trace_id']}/feedback",
            json={"rating": 5, "resolved": True, "comment": "Ótimo"},
        )
        assert feedback.status_code == 201
        analytics = client.get("/v1/tenants/empresa-metricas/analytics").json()
        assert analytics["messages_processed"] == 1
        assert analytics["handoff_rate"] == 1
        assert analytics["average_rating"] == 5
        handoff = client.get("/v1/tenants/empresa-metricas/handoffs/lead-2").json()
        assert handoff["last_intent"] == "human_handoff"
        assert len(handoff["transcript"]) == 2


def test_retrieval_is_accent_insensitive_and_returns_excerpt():
    documents = [{"title": "Política de devolução", "text": "O cliente pode devolver o produto em até sete dias.", "url": "https://example.com/trocas"}]
    matches = retrieve("Como faco uma devolucao?", documents)
    assert matches
    assert matches[0].score > 0
    assert "devolver" in matches[0].excerpt


def test_unknown_niche_is_rejected():
    with TestClient(app) as client:
        response = client.post("/v1/tenants", json=tenant_payload("outro-cliente") | {"niche": "inexistente"})
        assert response.status_code == 422


def teardown_module():
    Path("work/test-agent-v2.db").unlink(missing_ok=True)
