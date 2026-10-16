from tests.conftest import make_doc_image


def _start(client, name="Juliana Santos"):
    r = client.post("/api/triage/sessions", json={"customer_contact": "+5511988887777", "customer_name": name})
    assert r.status_code == 201
    return r.json()


def _say(client, protocol, text):
    r = client.post("/api/triage/message", json={"protocol_id": protocol, "message": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_fluxo_inventario_completo(client):
    t = _start(client)
    assert t["stage"] == "identify_act"
    out = _say(client, t["protocol_id"], "Quanto custa um inventário?")
    assert out["triage"]["stage"] == "ask_value"
    assert "valor total" in out["replies"][-1]["message"]

    out = _say(client, t["protocol_id"], "uns 450 mil")
    tri = out["triage"]
    assert tri["stage"] == "collect_docs"
    assert tri["estimated_total"] == 2450.80
    assert len(tri["checklist"]) == 5
    texts = " ".join(r["message"] for r in out["replies"])
    assert "R$ 2.450,80" in texts and "estimativa preliminar" in texts

    # Foto borrada é recusada no pré-filtro de qualidade
    r = client.post("/api/triage/upload-doc", data={"protocol_id": t["protocol_id"]},
                    files={"file": ("doc.jpg", make_doc_image(blur=True), "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["verification"]["validation_status"] == "REJEITADO_ILEGIVEL"
    assert body["triage"]["checklist"][0]["status"] == "REJEITADO"

    # Foto nítida sem LLM vai para conferência manual
    r = client.post("/api/triage/upload-doc", data={"protocol_id": t["protocol_id"], "doc_index": "0"},
                    files={"file": ("doc.jpg", make_doc_image(), "image/jpeg")})
    body = r.json()
    assert body["verification"]["validation_status"] == "REVISAO_MANUAL"
    item = body["triage"]["checklist"][0]
    assert item["status"] == "ENVIADO" and item["image_url"].startswith("/media/uploads/")
    assert client.get(item["image_url"]).status_code == 200

    # Escrevente confere todos → pronto para balcão
    for i in range(5):
        r = client.patch(f"/api/triage/sessions/{t['protocol_id']}/checklist/{i}", json={"status": "VALIDADO"})
        assert r.status_code == 200
    tri = r.json()
    assert tri["status"] == "ready_for_counter"
    assert "Todos os documentos" in tri["chat_history"][-1]["message"]

    inbox = client.get("/api/triage/sessions", params={"status": "ready_for_counter"}).json()
    assert inbox[0]["docs_validated"] == 5 and inbox[0]["docs_required"] == 5

    tri = client.post(f"/api/triage/sessions/{t['protocol_id']}/counter-ticket").json()
    assert tri["counter_ticket"] == "P001" and tri["stage"] == "done"
    # Idempotente
    assert client.post(f"/api/triage/sessions/{t['protocol_id']}/counter-ticket").json()["counter_ticket"] == "P001"


def test_pergunta_valor_na_primeira_mensagem(client):
    t = _start(client)
    out = _say(client, t["protocol_id"], "Quanto custa um inventário de 450 mil?")
    assert out["triage"]["stage"] == "collect_docs"
    assert out["triage"]["estimated_total"] == 2450.80


def test_ato_fixo_vai_direto_ao_checklist(client):
    t = _start(client, name=None)
    assert t["stage"] == "ask_name"
    out = _say(client, t["protocol_id"], "Carlos Pereira")
    assert out["triage"]["customer_name"] == "Carlos Pereira"
    out = _say(client, t["protocol_id"], "quero me casar")
    assert out["triage"]["stage"] == "collect_docs"
    assert out["triage"]["fee_estimate"]["declared_value"] is None
    assert len(out["triage"]["checklist"]) == 3


def test_transbordo_humano_silencia_bot(client):
    t = _start(client)
    _say(client, t["protocol_id"], "quero me casar")
    out = _say(client, t["protocol_id"], "quero falar com um atendente")
    assert out["triage"]["status"] == "human_takeover"
    assert out["triage"]["human_requested"] is True
    out = _say(client, t["protocol_id"], "alô?")
    assert out["replies"] == []

    tri = client.post(f"/api/triage/sessions/{t['protocol_id']}/attendant-message",
                      json={"message": "Oi, aqui é a Ana", "attendant_name": "Ana"}).json()
    assert tri["chat_history"][-1]["sender"] == "attendant"
    # Responder um pedido de atendente registra quem assumiu
    assert tri["attendant_name"] == "Ana"

    tri = client.post(f"/api/triage/sessions/{t['protocol_id']}/release").json()
    assert tri["status"] == "in_progress" and tri["human_requested"] is False
    assert _say(client, t["protocol_id"], "quais documentos faltam?")["replies"]


def test_escrevente_escrever_assume_atendimento(client):
    t = _start(client)
    tri = client.post(f"/api/triage/sessions/{t['protocol_id']}/attendant-message",
                      json={"message": "Bom dia!", "attendant_name": "Ana"}).json()
    assert tri["status"] == "human_takeover" and tri["attendant_name"] == "Ana"


def test_whatsapp_sem_protocolo_retoma_sessao(client):
    r = client.post("/api/triage/message", json={"customer_contact": "+5511900000000", "message": "oi",
                                                  "channel": "whatsapp"})
    p1 = r.json()["triage"]["protocol_id"]
    r = client.post("/api/triage/message", json={"customer_contact": "+5511900000000", "message": "Maria Souza",
                                                  "channel": "whatsapp"})
    assert r.json()["triage"]["protocol_id"] == p1
    assert r.json()["triage"]["customer_name"] == "Maria Souza"


def test_upload_sem_ato_e_formato_invalido(client):
    t = _start(client)
    r = client.post("/api/triage/upload-doc", data={"protocol_id": t["protocol_id"]},
                    files={"file": ("a.jpg", make_doc_image(), "image/jpeg")})
    assert r.status_code == 422
    _say(client, t["protocol_id"], "quero me casar")
    r = client.post("/api/triage/upload-doc", data={"protocol_id": t["protocol_id"]},
                    files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_recusa_exige_motivo(client):
    t = _start(client)
    _say(client, t["protocol_id"], "quero me casar")
    r = client.patch(f"/api/triage/sessions/{t['protocol_id']}/checklist/0", json={"status": "REJEITADO"})
    assert r.status_code == 422


def test_estimativa_avulsa_e_catalogo(client):
    assert len(client.get("/api/acts").json()) == 6
    r = client.get("/api/fees/estimate", params={"act_type": "inventario_extrajudicial", "declared_value": 450000})
    assert r.json()["total_estimate"] == 2450.80
    r = client.get("/api/fees/estimate", params={"act_type": "inventario_extrajudicial"})
    assert r.status_code == 422


def test_verify_photo_avulso(client):
    r = client.post("/api/triage/verify-photo", data={"expected_doc_type": "Certidão de Óbito do Autor da Herança"},
                    files={"file": ("a.jpg", make_doc_image(size=(300, 200)), "image/jpeg")})
    assert r.json()["validation_status"] == "REJEITADO_ILEGIVEL"


def test_demo_data(client):
    from app.demo_data import create_demo_triages

    # Roda no event loop do app (o cliente async do MongoDB fica preso ao loop em que foi criado)
    protocols = client.portal.call(create_demo_triages)
    statuses = {client.get(f"/api/triage/sessions/{p}").json()["status"] for p in protocols}
    assert statuses == {"in_progress", "ready_for_counter", "human_takeover"}
