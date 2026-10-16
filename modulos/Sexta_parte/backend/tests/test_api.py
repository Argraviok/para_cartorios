from datetime import date, timedelta

from tests.fixtures import make_clean, make_signature, make_tampered

CPF = "529.982.247-25"


async def _create_card(client):
    r = await client.post("/api/signature-cards", data={"cpf": "52998224725", "full_name": "João da Silva",
                                                        "card_number": "44.912"},
                          files={"signature": ("s.png", make_signature(0, "A", seed=1), "image/png")})
    assert r.status_code == 201, r.text
    return r.json()


async def _audit(client, doc, sig=None, **extra):
    files = {"document": ("rg.jpg", doc, "image/jpeg")}
    if sig:
        files["signature_image"] = ("sig.png", sig, "image/png")
    data = {"protocol_number": "219.040", "service_type": "escritura_compra_venda", "document_type": "RG",
            "presenter_cpf": CPF, "presenter_name": "João da Silva", **extra}
    return await client.post("/api/fraud/audit-document", data=data, files=files)


async def test_signature_card_crud(client):
    card = await _create_card(client)
    assert card["cpf"] == CPF
    dup = await client.post("/api/signature-cards", data={"cpf": CPF, "full_name": "Outro"},
                            files={"signature": ("s.png", make_signature(0, "A"), "image/png")})
    assert dup.status_code == 409
    bad = await client.post("/api/signature-cards", data={"cpf": "123", "full_name": "X Y Z"},
                            files={"signature": ("s.png", make_signature(0, "A"), "image/png")})
    assert bad.status_code == 422
    assert (await client.get(f"/api/signature-cards/by-cpf/{CPF}")).json()["id"] == card["id"]
    img = await client.get(f"/api/signature-cards/{card['id']}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"


async def test_clean_document_low_risk(client):
    await _create_card(client)
    r = await _audit(client, make_clean(2), make_signature(2, "A", seed=1))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["risk_level"] == "BAIXO", a
    assert a["checks"]["signature_matching"]["status"] == "APROVADO"
    assert a["checks"]["power_of_attorney_censec"]["status"] == "NAO_APLICAVEL"
    assert a["procuration_verified"] is None
    assert a["files"]["heatmap"] and a["files"]["signature_card"]


async def test_tampered_forged_is_critical_and_tracks_recidivism(client):
    await _create_card(client)
    proc = {"procuration_book": "120", "procuration_page": "45", "procuration_origin_office": "2º Tabelionato",
            "procuration_issued_on": str(date.today() - timedelta(days=1840))}
    r = await _audit(client, make_tampered(1), make_signature(1, "B", seed=5), **proc)
    a = r.json()
    assert a["risk_level"] == "CRITICO", a
    assert a["tampering_detected"] and a["checks"]["signature_matching"]["status"] == "DIVERGENTE"
    assert a["checks"]["power_of_attorney_censec"]["status"] == "ALERTA"
    assert await client.db.suspicious_patterns.count_documents({"cpf": CPF}) == 1

    again = (await _audit(client, make_clean(1), make_signature(2, "A", seed=1))).json()
    assert any("Reincidência" in f for f in again["risk_factors"])

    # arquivos servidos descriptografados
    heat = await client.get(f"/api/fraud/audits/{a['id']}/files/heatmap")
    assert heat.status_code == 200 and heat.content[:2] == b"\xff\xd8"

    listing = (await client.get("/api/fraud/audits", params={"risk_level": "CRITICO"})).json()
    assert [x["id"] for x in listing] == [a["id"]]
    stats = (await client.get("/api/fraud/stats")).json()
    assert stats["by_risk_level"]["CRITICO"] == 1 and stats["pending"] == 2


async def test_storage_is_encrypted_at_rest(client, settings):
    await _create_card(client)
    a = (await _audit(client, make_clean(1))).json()
    raw = next((settings.storage_dir / "documents").iterdir()).read_bytes()
    assert raw[:2] != b"\xff\xd8" and raw.startswith(b"gAAAA")  # token Fernet
    assert a["checks"]["signature_matching"]["status"] == "NAO_EXECUTADO"


async def test_decision_flow(client):
    a = (await _audit(client, make_clean(1))).json()
    url = f"/api/fraud/audits/{a['id']}/decision"
    short = await client.patch(url, json={"action": "APROVAR_FE_PUBLICA", "officer_name": "Ana", "notes": "ok"})
    assert short.status_code == 422

    r = await client.patch(url, json={"action": "SOLICITAR_PRESENCIAL", "officer_name": "Ana Escrevente",
                                      "notes": "Comparecer com documento original."})
    assert r.json()["officer_decision"] == "PENDENTE" and r.json()["in_person_requested"]

    r = await client.patch(url, json={"action": "APROVAR_FE_PUBLICA", "officer_name": "Dr. Paulo Tabelião",
                                      "notes": "Conferido presencialmente com biometria no balcão."})
    body = r.json()
    assert body["officer_decision"] == "HOMOLOGADO" and len(body["decision_history"]) == 2

    r = await client.patch(url, json={"action": "REJEITAR_FALSIDADE", "officer_name": "Outro",
                                      "notes": "Tentativa de alterar decisão final."})
    assert r.status_code == 409


async def test_invalid_inputs(client):
    r = await client.post("/api/fraud/audit-document",
                          data={"protocol_number": "1", "service_type": "x", "presenter_cpf": "123"},
                          files={"document": ("a.jpg", make_clean(1), "image/jpeg")})
    assert r.status_code == 422
    r = await client.post("/api/fraud/audit-document", data={"protocol_number": "1", "service_type": "x"},
                          files={"document": ("a.txt", b"not an image", "text/plain")})
    assert r.status_code == 422
    assert (await client.get("/api/fraud/audits/nao-existe")).status_code == 404


async def test_api_token(client, settings, monkeypatch):
    from app.core import config
    monkeypatch.setenv("API_TOKEN", "s3cr3t")
    config.get_settings.cache_clear()
    assert (await client.get("/api/fraud/stats")).status_code == 401
    ok = await client.get("/api/fraud/stats", headers={"Authorization": "Bearer s3cr3t"})
    assert ok.status_code == 200
