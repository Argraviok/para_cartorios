from datetime import date

import pytest

from app.schemas.devolution_schema import GenerateNoteRequest, LLMNoteDraft, LLMRequirement
from app.schemas.enums import VicioCode
from app.services.generator_service import GenerationError, NoteGenerator, format_legal_basis
from tests.fakes import FakeLLM, FakeSearcher, precedent

CONT = precedent("prec_cont_01", "quebra_continuidade", [("Lei 6.015/1973", "195"), ("Lei 6.015/1973", "237")])
ITBI = precedent("prec_itbi_01", "itbi_nao_recolhido", [("Lei 6.015/1973", "289")])


def make_request(*issues: tuple[str, str], **extra) -> GenerateNoteRequest:
    return GenerateNoteRequest(
        protocol_number="184.920",
        protocol_date=date(2026, 10, 14),
        act_type="escritura_compra_venda",
        presenter_name="Fulano",
        uf="sp",
        issues=[{"vicio_code": c, "case_facts": f, **extra} for c, f in issues],
    )


def llm_req(code: str, ids: list[str]) -> LLMRequirement:
    return LLMRequirement(
        vicio_code=VicioCode(code),
        legal_topic="Tópico",
        precedent_ids=ids,
        justification_draft="Verifica-se que...",
        suggested_solution="Apresentar...",
    )


FACTS = "Na matrícula o transmitente consta como solteiro; no título, casado."


async def test_generates_grounded_requirement_with_backend_legal_basis():
    llm = FakeLLM(LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_cont_01"])]))
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), llm)

    result = await gen.generate(make_request(("quebra_continuidade", FACTS)))

    [r] = result.requirements
    assert r.order == 1 and r.source == "ai" and r.grounded
    assert r.legal_basis == "Lei 6.015/1973, arts. 195 e 237"
    assert result.warnings == []
    assert result.llm_model == "fake-llm"


async def test_invalid_citation_is_retried_with_error_feedback():
    llm = FakeLLM(
        LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_inventado"])]),
        LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_cont_01"])]),
    )
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), llm)

    result = await gen.generate(make_request(("quebra_continuidade", FACTS)))

    assert result.requirements[0].precedent_ids == ["prec_cont_01"]
    assert len(llm.prompts) == 2
    assert "prec_inventado" in llm.prompts[1]


async def test_invalid_citation_twice_raises():
    bad = LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_inventado"])])
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), FakeLLM(bad, bad))

    with pytest.raises(GenerationError, match="prec_inventado"):
        await gen.generate(make_request(("quebra_continuidade", FACTS)))


async def test_citation_from_other_vicio_is_rejected():
    # ID existe, mas foi recuperado para outro vício
    cross = LLMNoteDraft(requirements=[
        llm_req("quebra_continuidade", ["prec_itbi_01"]),
        llm_req("itbi_nao_recolhido", ["prec_itbi_01"]),
    ])
    searcher = FakeSearcher({"quebra_continuidade": [CONT], "itbi_nao_recolhido": [ITBI]})
    gen = NoteGenerator(searcher, FakeLLM(cross, cross))

    with pytest.raises(GenerationError, match="quebra_continuidade"):
        await gen.generate(make_request(("quebra_continuidade", FACTS), ("itbi_nao_recolhido", "Guia de ITBI não apresentada.")))


async def test_missing_requirement_for_grounded_vicio_is_rejected():
    only_one = LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_cont_01"])])
    searcher = FakeSearcher({"quebra_continuidade": [CONT], "itbi_nao_recolhido": [ITBI]})
    gen = NoteGenerator(searcher, FakeLLM(only_one, only_one))

    with pytest.raises(GenerationError, match="nenhuma exigência gerada para 'itbi_nao_recolhido'"):
        await gen.generate(make_request(("quebra_continuidade", FACTS), ("itbi_nao_recolhido", "Guia de ITBI não apresentada.")))


async def test_llm_exception_is_retried():
    llm = FakeLLM(ValueError("JSON inválido"), LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_cont_01"])]))
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), llm)

    result = await gen.generate(make_request(("quebra_continuidade", FACTS)))
    assert len(result.requirements) == 1


async def test_ungrounded_vicio_becomes_manual_and_is_not_sent_to_llm():
    llm = FakeLLM(LLMNoteDraft(requirements=[llm_req("quebra_continuidade", ["prec_cont_01"])]))
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), llm)
    cnd_facts = "Não consta certidão de débitos municipais do imóvel."

    result = await gen.generate(make_request(("quebra_continuidade", FACTS), ("cnd_municipal_ausente", cnd_facts)))

    ai, manual = result.requirements
    assert (ai.order, manual.order) == (1, 2)
    assert manual.source == "manual" and not manual.grounded
    assert manual.legal_basis == "" and manual.justification_draft == cnd_facts
    assert manual.legal_topic == "Ausência de CND Municipal"
    assert len(result.warnings) == 1 and "CND Municipal" in result.warnings[0]
    assert cnd_facts not in llm.prompts[0]


async def test_only_ungrounded_issues_never_call_llm():
    llm = FakeLLM()  # qualquer chamada estouraria IndexError
    gen = NoteGenerator(FakeSearcher({}), llm)

    result = await gen.generate(
        make_request(("outro", "Fatos de um vício não catalogado na base."), title="Vício específico")
    )

    [r] = result.requirements
    assert r.legal_topic == "Vício específico" and r.source == "manual"
    assert llm.prompts == []
    assert result.llm_model is None


async def test_without_llm_configured_raises_only_when_needed():
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), llm=None)
    with pytest.raises(GenerationError, match="LLM não configurado"):
        await gen.generate(make_request(("quebra_continuidade", FACTS)))


def test_request_normalizes_and_validates():
    req = make_request(("quebra_continuidade", FACTS))
    assert req.protocol_number == "184920" and req.uf == "SP"
    with pytest.raises(ValueError):
        make_request(("quebra_continuidade", "curto"))
    with pytest.raises(ValueError, match="title"):
        make_request(("outro", "Fatos suficientemente longos aqui."))


def test_format_legal_basis_dedupes_and_handles_missing_article():
    a = precedent("a", "x", [("Lei 6.015/1973", "195"), ("Prov. CNJ 149/2023", None)])
    b = precedent("b", "x", [("Lei 6.015/1973", "195")])
    assert format_legal_basis([a, b]) == "Lei 6.015/1973, art. 195; Prov. CNJ 149/2023"


def test_format_legal_basis_groups_articles_by_diploma():
    a = precedent("a", "x", [("Lei 6.015/1973", "195"), ("Lei 6.015/1973", "237"), ("Lei 6.015/1973", "289")])
    assert format_legal_basis([a]) == "Lei 6.015/1973, arts. 195, 237 e 289"
    b = precedent("b", "x", [("Código Civil", "1.647, I"), ("Código Civil", "1.649")])
    assert format_legal_basis([b]) == "Código Civil, arts. 1.647, I; 1.649"


async def test_offline_mode_uses_ficha_text_and_case_facts_only():
    gen = NoteGenerator(FakeSearcher({"quebra_continuidade": [CONT]}), llm=None, offline=True)

    result = await gen.generate(make_request(("quebra_continuidade", FACTS)))

    [r] = result.requirements
    assert r.precedent_ids == ["prec_cont_01"] and r.source == "ai" and r.grounded
    assert r.justification_draft == f"Redação-modelo.\n\nNo caso concreto: {FACTS}"
    assert r.suggested_solution == "Providência padrão."
    assert result.llm_model == "offline-template"
