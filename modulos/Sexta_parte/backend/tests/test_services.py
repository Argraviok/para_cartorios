from datetime import date, timedelta

from app.schemas.fraud_schema import ProcurationInput
from app.services import censec_checker_service, forensics_service, signature_service
from app.services.cpf import format_cpf, is_valid_cpf, mask_cpf
from tests.fixtures import jpeg, make_clean, make_document, make_signature, make_tampered


def test_cpf():
    assert is_valid_cpf("529.982.247-25")
    assert not is_valid_cpf("529.982.247-26")
    assert not is_valid_cpf("111.111.111-11")
    assert format_cpf("52998224725") == "529.982.247-25"
    assert mask_cpf("52998224725") == "***.982.247-**"


async def test_ela_separates_clean_and_tampered():
    for seed in (1, 2, 3):
        clean = await forensics_service.analyze_document(make_clean(seed), "rg.jpg", "RG")
        tampered = await forensics_service.analyze_document(make_tampered(seed), "rg.jpg", "RG")
        assert clean.check.status == "APROVADO", clean.check
        assert tampered.check.status == "SUSPEITO", tampered.check
        # A região apontada deve cobrir o CPF colado (x 150-520, y 190-250).
        r = tampered.check.suspicious_regions[0]
        assert r.x < 520 and r.x + r.w > 150 and r.y < 250 and r.y + r.h > 190


async def test_png_source_flags_low_reliability():
    import io
    buf = io.BytesIO()
    make_document().save(buf, "PNG")
    res = await forensics_service.analyze_document(buf.getvalue(), "rg.png", "RG")
    assert not res.check.ela_reliable
    assert any("baixa confiabilidade" in f for f in res.check.findings)


async def test_pdf_with_embedded_jpeg_uses_original_compression():
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=640)
    page.insert_image(page.rect, stream=make_tampered(1))
    res = await forensics_service.analyze_document(doc.tobytes(), "proc.pdf", "PROCURACAO")
    assert res.check.source_format == "PDF/JPEG"
    assert res.check.status == "SUSPEITO"


async def test_exif_editing_software_flag():
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(make_clean(1)))
    exif = img.getexif()
    exif[0x0131] = "Adobe Photoshop 25.0"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95, exif=exif)
    res = await forensics_service.analyze_document(buf.getvalue(), "rg.jpg", "RG")
    assert any("Photoshop" in f for f in res.check.findings)
    assert res.check.score >= 25


async def test_signature_genuine_vs_forged():
    card = make_signature(0, "A", seed=1)
    for v in (1, 2, 3):
        genuine = await signature_service.compare(make_signature(v, "A", seed=1), card, "44.912", None)
        assert genuine.status == "APROVADO", genuine
    forged = await signature_service.compare(make_signature(1, "B", seed=5), card, "44.912", None)
    assert forged.status == "DIVERGENTE", forged
    assert "44.912" in forged.observation


async def test_censec_rules():
    today = date(2026, 10, 14)
    old = ProcurationInput(book="120", page="45", origin_office="2º Tabelionato", issued_on=today - timedelta(days=1840))
    r = await censec_checker_service.check_procuration(old, "PROCURACAO", today)
    assert r.status == "ALERTA" and r.age_days == 1840 and r.is_valid

    confirmed = old.model_copy(update={"censec_confirmed_on": today - timedelta(days=3)})
    r = await censec_checker_service.check_procuration(confirmed, "PROCURACAO", today)
    assert r.status == "APROVADO" and r.verified_on_censec

    revoked = old.model_copy(update={"revocation_declared": True})
    r = await censec_checker_service.check_procuration(revoked, "PROCURACAO", today)
    assert r.status == "REPROVADO" and r.is_valid is False

    r = await censec_checker_service.check_procuration(ProcurationInput(), "RG", today)
    assert r.status == "NAO_APLICAVEL"
    r = await censec_checker_service.check_procuration(ProcurationInput(), "PROCURACAO", today)
    assert r.status == "ALERTA"
