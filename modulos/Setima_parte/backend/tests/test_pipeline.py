import asyncio
import shutil
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.services import regex_rules
from app.services.pdf_sanitizer_service import sanitize
from app.services.pii_detector_service import detect_pii

SAMPLES = Path(__file__).parent.parent / "test_samples"


@pytest.fixture(scope="session", autouse=True)
def samples():
    from test_samples.generate_samples import build_certidao, build_docx, build_scanned

    build_certidao(SAMPLES / "certidao_interdicao_ficticia.pdf")
    build_scanned(SAMPLES / "certidao_digitalizada_ficticia.pdf")
    build_docx(SAMPLES / "certidao_interdicao_ficticia.docx")


@pytest.fixture
def certidao() -> bytes:
    return (SAMPLES / "certidao_interdicao_ficticia.pdf").read_bytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MONGODB_URI", "")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_cpf_and_luhn_validators():
    assert regex_rules.is_valid_cpf("529.982.247-25")
    assert not regex_rules.is_valid_cpf("529.982.247-26")
    assert not regex_rules.is_valid_cpf("111.111.111-11")
    assert regex_rules.passes_luhn("4111 1111 1111 1111")
    assert not regex_rules.passes_luhn("4111 1111 1111 1112")


def test_financial_rule_redacts_only_the_amount():
    text = "com saldo de R$ 48.320,15 em conta"
    [m] = [m for m in regex_rules.find_matches(text) if m.category == "DADO_FINANCEIRO"]
    assert text[m.start : m.end] == "R$ 48.320,15"


def test_detection_finds_expected_categories(certidao):
    result = asyncio.run(detect_pii(certidao, Settings(llm_provider="none")))
    found = {(i.category, i.pii_type) for i in result.items}
    assert {
        ("DADO_MEDICO", "CONDICAO_SAUDE"),
        ("DADO_BANCARIO", "CONTA_BANCARIA"),
        ("DADO_BANCARIO", "CHAVE_PIX"),
        ("DADO_BANCARIO", "CARTAO_CREDITO"),
        ("DADO_FINANCEIRO", "VALOR_PATRIMONIAL"),
        ("FILIACAO_PROTEGIDA", "ORIGEM_FILIACAO"),
        ("DOCUMENTO_PESSOAL", "CPF"),
    } <= found
    conta = next(i for i in result.items if i.pii_type == "CONTA_BANCARIA")
    assert conta.detected_text == "Banco Santander Ag. 0918 C/C 0109283-4"
    pix = next(i for i in result.items if i.pii_type == "CHAVE_PIX")
    assert pix.detected_text == "fulano.ficticio@example.com"
    # CPF das partes integra o teor do ato: nasce não aprovado.
    assert all(not i.approved for i in result.items if i.category == "DOCUMENTO_PESSOAL")


def test_sanitized_pdf_has_no_selectable_text_under_redactions(certidao):
    """Teste de seleção de texto obrigatório (spec, seção 6)."""
    result = asyncio.run(detect_pii(certidao, Settings(llm_provider="none")))
    approved = [i for i in result.items if i.approved]
    output = sanitize(certidao, result.items)

    with pymupdf.open(stream=output, filetype="pdf") as doc:
        full_text = "\n".join(p.get_text() for p in doc)
        for secret in ("esquizofrenia", "F20.0", "0109283-4", "48.320,15", "4111 1111", "fulano.ficticio", "CICRANA"):
            assert secret not in full_text, secret
        # Itens não aprovados (CPF) permanecem.
        assert "529.982.247-25" in full_text
        # Texto fora das tarjas permanece.
        assert "O referido é verdade e dou fé" in full_text
        # Nota adesiva sobre o diagnóstico e metadados foram eliminados.
        assert not list(doc[1].annots())
        assert not doc.metadata.get("author") and not doc.metadata.get("title")
        for item in approved:
            page = doc[item.page_number - 1]
            for b in item.bboxes:
                assert page.get_text("text", clip=pymupdf.Rect(b.x0, b.y0, b.x1, b.y1)).strip() == ""

    # Nenhum resquício no binário (fluxos antigos órfãos seriam detectados aqui).
    with pymupdf.open(stream=output, filetype="pdf") as doc:
        raw = b"".join(doc.xref_stream(x) or b"" for x in range(1, doc.xref_length()) if doc.xref_is_stream(x))
    assert b"esquizofrenia" not in raw and b"Santander" not in raw


def test_scanned_page_pixels_are_destroyed():
    data = (SAMPLES / "certidao_digitalizada_ficticia.pdf").read_bytes()
    result = asyncio.run(detect_pii(data, Settings(llm_provider="none")))
    assert result.items == [] and "sem camada de texto" in result.warnings[0]

    from app.schemas.redaction_schema import BoundingBox, RedactionItem

    box = BoundingBox(x0=100, y0=100, x1=300, y1=160)
    item = RedactionItem(
        redaction_id="man_1", category="DADO_BANCARIO", pii_type="MANUAL", page_number=1,
        bboxes=[box], approved=True, legal_basis="manual", source="manual",
    )
    output = sanitize(data, [item])
    with pymupdf.open(stream=output, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(clip=pymupdf.Rect(110, 110, 290, 150))
        assert set(pix.samples) == {0}  # área inteiramente preta


def test_api_end_to_end(client, certidao):
    resp = client.post(
        "/api/redact/analyze",
        files={"file": ("certidao.pdf", certidao, "application/pdf")},
        data={"service_type": "registro_civil_interdicoes", "operator": "escrevente.teste"},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "pending_review" and job["total_detected"] > 0

    assert client.get(f"/api/redact/jobs/{job['job_id']}/pages/1.png").headers["content-type"] == "image/png"

    items = job["items"]
    items.append({
        "redaction_id": "man_x", "category": "DOCUMENTO_PESSOAL", "pii_type": "MANUAL", "page_number": 1,
        "bboxes": [{"x0": 60, "y0": 140, "x1": 300, "y1": 160}], "approved": True,
        "legal_basis": "ignorado", "source": "manual",
    })
    body = {"job_id": job["job_id"], "items": items, "operator": "escrevente.teste", "confirm_irreversible": False}
    assert client.post("/api/redact/apply", json=body).status_code == 422

    body["confirm_irreversible"] = True
    resp = client.post("/api/redact/apply", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    with pymupdf.open(stream=resp.content, filetype="pdf") as doc:
        assert "esquizofrenia" not in doc[1].get_text()

    stored = client.get(f"/api/redact/jobs/{job['job_id']}").json()
    assert stored["status"] == "sanitized"
    assert all("esquizofrenia" not in i["detected_text"] for i in stored["items"])
    manual = next(i for i in stored["items"] if i["source"] == "manual")
    assert manual["legal_basis"].startswith("Tarja manual")

    assert client.post("/api/redact/apply", json=body).status_code == 409
    assert client.get(f"/api/redact/jobs/{job['job_id']}/sanitized").status_code == 200

    audit = client.get(f"/api/redact/jobs/{job['job_id']}/audit").json()
    assert [e["event"] for e in audit] == ["ANALYZE", "SANITIZE"]
    assert "esquizofrenia" not in str(audit) and "Santander" not in str(audit)
    csv = client.get(f"/api/redact/jobs/{job['job_id']}/audit.csv")
    assert "SANITIZE" in csv.text
    report = client.get(f"/api/redact/jobs/{job['job_id']}/audit.pdf")
    assert report.content.startswith(b"%PDF")


def test_rejects_unsupported_format(client):
    resp = client.post("/api/redact/analyze", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert resp.status_code == 415
    # ZIP que não é documento Word também é recusado, mesmo com extensão .docx.
    import io, zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("foo.txt", "x")
    resp = client.post("/api/redact/analyze", files={"file": ("x.docx", buf.getvalue(), "application/octet-stream")})
    assert resp.status_code == 415


def _legacy_doc(tmp_path) -> bytes:
    """Converte o .docx de amostra para o formato .doc (Word 97) via LibreOffice."""
    import subprocess

    subprocess.run(
        ["soffice", f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}", "--headless",
         "--convert-to", "doc:MS Word 97", "--outdir", str(tmp_path), str(SAMPLES / "certidao_interdicao_ficticia.docx")],
        check=True, capture_output=True, timeout=120,
    )
    return (tmp_path / "certidao_interdicao_ficticia.doc").read_bytes()


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice não instalado")
@pytest.mark.parametrize("ext", ["docx", "doc"])
def test_word_documents_end_to_end(client, tmp_path, ext):
    data = (SAMPLES / "certidao_interdicao_ficticia.docx").read_bytes() if ext == "docx" else _legacy_doc(tmp_path)
    resp = client.post(
        "/api/redact/analyze",
        files={"file": (f"certidao.{ext}", data, "application/octet-stream")},
        data={"service_type": "registro_civil_interdicoes", "operator": "escrevente.teste"},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["source_format"] == ext and job["source_sha256"]
    assert len(job["pages"]) == 3
    found = {i["pii_type"] for i in job["items"]}
    assert {"CONDICAO_SAUDE", "CONTA_BANCARIA", "CARTAO_CREDITO", "ORIGEM_FILIACAO"} <= found

    resp = client.post(
        "/api/redact/apply",
        json={"job_id": job["job_id"], "items": job["items"], "operator": "escrevente.teste", "confirm_irreversible": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "certidao_tarjado.pdf" in resp.headers["content-disposition"]
    with pymupdf.open(stream=resp.content, filetype="pdf") as doc:
        text = "\n".join(p.get_text() for p in doc)
    for secret in ("esquizofrenia", "0109283-4", "48.320,15", "CICRANA"):
        assert secret not in text, secret
    assert "O referido é verdade e dou fé" in text
    # O Word enviado é preservado, intacto, ao lado do PDF de trabalho.
    stored = (tmp_path / "originals" / f"{job['job_id']}.{ext}").read_bytes()
    assert stored == data
