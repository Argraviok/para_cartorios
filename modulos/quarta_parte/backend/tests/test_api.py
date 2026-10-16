"""Testes ponta a ponta com os PDFs de test_samples/ (extrator heurístico, repositório em memória)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

SAMPLES = Path(__file__).parent.parent / "test_samples"


@pytest.fixture(scope="module")
def client():
    settings.llm_provider = "heuristic"
    settings.mongodb_uri = ""
    settings.geocoding_enabled = False  # sem chamadas reais ao Nominatim nos testes
    if not (SAMPLES / "matricula_georref_77001.pdf").exists():
        import runpy

        runpy.run_path(str(SAMPLES / "generate_samples.py"), run_name="__main__")
    from app.main import app

    with TestClient(app) as c:
        yield c


def pdf(name):
    return (name, (SAMPLES / name).read_bytes(), "application/pdf")


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def word(name):
    mime = DOCX_MIME if name.endswith(".docx") else "application/msword"
    return (name, (SAMPLES / name).read_bytes(), mime)


def test_full_analysis_detects_break_and_lien(client):
    r = client.post(
        "/api/parcels/analyze",
        files={
            "matricula": pdf("matricula_89214.pdf"),
            "memorial": pdf("memorial_89214.pdf"),
            "titulo": pdf("contrato_compra_venda.pdf"),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cont = body["subjective_continuity"]
    assert body["registry_number"] == "89.214"
    assert cont["status"] == "QUEBRA_DETECTADA"
    assert cont["current_registered_owner"] == "CARLOS EDUARDO PEREIRA (R-4)"
    assert cont["seller_in_contract"] == "MARCOS VINICIUS PEREIRA"
    assert [lien["act_code"] for lien in cont["active_liens"]] == ["AV-5"]

    geo = body["geometry"]
    assert geo["is_closed"] and geo["gap_meters"] < 0.02
    assert geo["area_difference_percent"] < 5
    assert geo["location_geojson"]["type"] == "Polygon"
    assert {c["registry"] for c in geo["confrontants"] if c["registry"]} == {"41.877", "52.310"}

    codes = {a["code"] for a in body["alerts"]}
    assert {"QUEBRA_CONTINUIDADE", "ONUS_PENHORA", "CONFRONTANTES_MATRICULADOS"} <= codes

    fetched = client.get(f"/api/parcels/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["geometry"]["calculated_area"] == geo["calculated_area"]
    assert any(p["id"] == body["id"] for p in client.get("/api/parcels").json())


def test_manual_seller_overrides_title(client):
    r = client.post(
        "/api/parcels/analyze",
        files={"matricula": pdf("matricula_89214.pdf"), "titulo": pdf("contrato_compra_venda.pdf")},
        data={"seller_name": "Carlos Eduardo Pereira"},
    )
    cont = r.json()["subjective_continuity"]
    assert cont["status"] == "ALERTA"  # vendedor confere, mas penhora vigente
    assert r.json()["geometry"] is None


def test_overlap_with_previous_analysis(client):
    client.post("/api/parcels/analyze", files={"matricula": pdf("matricula_89214.pdf"), "memorial": pdf("memorial_89214.pdf")})
    from app.core.database import get_repository

    repo = get_repository()
    doc = next(d for d in repo.docs.values() if d["geometry"])
    hits = __import__("asyncio").run(repo.find_overlaps(doc["geometry"]["location_geojson"], "99.999"))
    assert any(h["registry_number"] == "89.214" for h in hits)


def test_geometry_endpoint_not_closing(client):
    r = client.post("/api/geometry/analyze", files={"memorial": pdf("memorial_nao_fecha.pdf")})
    assert r.status_code == 200
    g = r.json()
    assert not g["is_closed"] and g["gap_meters"] == pytest.approx(3.0)
    assert not g["is_georeferenced"]


def test_scanned_pdf_without_llm_returns_422(client):
    r = client.post("/api/continuity/analyze", files={"matricula": pdf("vazio_escaneado.pdf")})
    assert r.status_code == 422
    assert "escaneado" in r.json()["detail"]


def test_invalid_pdf_returns_422(client):
    r = client.post("/api/continuity/analyze", files={"matricula": ("x.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 422


@pytest.mark.skipif(not (SAMPLES / "matricula_89214.doc").exists(), reason="LibreOffice ausente: sem .doc de exemplo")
def test_word_documents_give_same_result_as_pdf(client):
    """Matrícula em .doc (Word 97-2003), memorial em .docx com tabela de vértices e contrato em .docx."""
    r = client.post(
        "/api/parcels/analyze",
        files={
            "matricula": word("matricula_89214.doc"),
            "memorial": word("memorial_89214_tabela.docx"),
            "titulo": word("contrato_compra_venda.docx"),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cont, geo = body["subjective_continuity"], body["geometry"]
    assert cont["status"] == "QUEBRA_DETECTADA"
    assert cont["current_registered_owner"] == "CARLOS EDUARDO PEREIRA (R-4)"
    assert cont["seller_in_contract"] == "MARCOS VINICIUS PEREIRA"
    assert [lien["act_code"] for lien in cont["active_liens"]] == ["AV-5"]
    assert geo["is_georeferenced"] and geo["gap_meters"] < 0.02
    assert geo["calculated_area"] == pytest.approx(1504.48, abs=0.01)
    assert {c["registry"] for c in geo["confrontants"] if c["registry"]} == {"41.877", "52.310"}


def test_unsupported_format_returns_422(client):
    r = client.post("/api/continuity/analyze", files={"matricula": ("x.txt", "MATRÍCULA 1".encode(), "text/plain")})
    assert r.status_code == 422
    assert "DOCX" in r.json()["detail"]


def test_geometry_from_registry_when_no_memorial(client):
    r = client.post("/api/parcels/analyze", files={"matricula": pdf("matricula_georref_77001.pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    geo = body["geometry"]
    assert geo["source"] == "MATRICULA"
    assert geo["georeference_method"] == "COORDINATES"
    assert geo["calculated_area"] == pytest.approx(1504.48, abs=0.01)
    assert "GEOMETRIA_DA_MATRICULA" in {a["code"] for a in body["alerts"]}
    assert geo["confrontants"][-1]["name"] == "Área Pública Municipal"  # não engole o parágrafo seguinte
    assert {c["registry"] for c in geo["confrontants"] if c["registry"]} == {"41.877", "52.310"}
    assert body["subjective_continuity"]["current_registered_owner"] == "PAULO HENRIQUE LIMA (R-1)"


def test_manual_anchor_places_traverse_on_map(client):
    r = client.post(
        "/api/parcels/analyze",
        files={"matricula": pdf("matricula_89214.pdf"), "memorial": pdf("memorial_nao_fecha.pdf")},
    )
    body = r.json()
    assert body["geometry"]["georeference_method"] == "NONE"
    assert body["geometry"]["location_geojson"] is None

    r = client.post(f"/api/parcels/{body['id']}/anchor", json={"lat": -22.9056, "lon": -47.0608})
    assert r.status_code == 200, r.text
    geo = r.json()["geometry"]
    assert geo["georeference_method"] == "MANUAL_ANCHOR" and geo["is_georeferenced"]
    first = geo["segments"][0]["coordinates"][0]
    assert first == pytest.approx([-47.0608, -22.9056], abs=1e-7)
    assert geo["calculated_area"] == body["geometry"]["calculated_area"]  # só translada, não deforma
    assert geo["closure_gap_line"] is not None  # o erro de 3 m continua visível no mapa
    # Persistido: a próxima leitura já vem posicionada
    again = client.get(f"/api/parcels/{body['id']}").json()
    assert again["geometry"]["georeference_method"] == "MANUAL_ANCHOR"


def test_anchor_refused_for_coordinate_geometry(client):
    body = client.post(
        "/api/parcels/analyze",
        files={"matricula": pdf("matricula_89214.pdf"), "memorial": pdf("memorial_89214.pdf")},
    ).json()
    r = client.post(f"/api/parcels/{body['id']}/anchor", json={"lat": -22.9, "lon": -47.0})
    assert r.status_code == 409


def test_location_far_from_coordinates_is_flagged(client, monkeypatch):
    from app.api.endpoints import parcels
    from app.schemas.geo_schema import ApproximateLocation

    async def fake_geocode(addr):
        assert addr.city == "Campinas" and addr.street == "Rua das Acácias"
        return ApproximateLocation(lat=-23.55, lon=-46.63, precision="RUA", query="Rua das Acácias, Campinas, SP")

    monkeypatch.setattr(parcels, "geocode_address", fake_geocode)
    body = client.post(
        "/api/parcels/analyze",
        files={"matricula": pdf("matricula_89214.pdf"), "memorial": pdf("memorial_89214.pdf")},
    ).json()
    assert body["approximate_location"]["precision"] == "RUA"
    assert "COORDENADAS_LONGE_DO_ENDERECO" in {a["code"] for a in body["alerts"]}


def test_location_only_when_no_geometry(client, monkeypatch):
    from app.api.endpoints import parcels
    from app.schemas.geo_schema import ApproximateLocation

    async def fake_geocode(addr):
        return ApproximateLocation(lat=-22.9, lon=-47.06, precision="RUA", query="Rua das Acácias, Campinas, SP")

    monkeypatch.setattr(parcels, "geocode_address", fake_geocode)
    body = client.post("/api/parcels/analyze", files={"matricula": pdf("matricula_89214.pdf")}).json()
    assert body["geometry"] is None
    assert body["approximate_location"]["lat"] == -22.9
    assert "LOCALIZACAO_APROXIMADA" in {a["code"] for a in body["alerts"]}
