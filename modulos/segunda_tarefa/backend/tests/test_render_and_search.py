from datetime import date

from app.core.config import Settings
from app.schemas.devolution_schema import Requirement
from app.services.render_service import markdown_to_plain_text, render_note
from app.services.search_service import rrf_merge

SETTINGS = Settings(_env_file=None, serventia_nome="1º RI de Teste", serventia_cidade_uf="Campinas/SP",
                    oficial_nome="Fulana de Tal", prenotacao_dias=20)


def req(order: int, **kw) -> Requirement:
    base = dict(order=order, vicio_code="quebra_continuidade", legal_topic=f"Tópico {order}",
                legal_basis="art. 195 da Lei 6.015/1973", justification_draft="Texto da IA.",
                suggested_solution="Apresentar documento.", source="ai", grounded=True)
    return Requirement(**{**base, **kw})


def render(requirements, **kw):
    return render_note(settings=SETTINGS, protocol_number="184920", protocol_date=date(2026, 10, 14),
                       act_type="Escritura de compra e venda", presenter_name="Banco Exemplo S.A.",
                       requirements=requirements, issue_date=date(2026, 10, 15), **kw)


def test_user_edited_text_takes_precedence():
    md = render([req(1, user_edited_text="Texto revisado pelo escrevente.")])
    assert "Texto revisado pelo escrevente." in md
    assert "Texto da IA." not in md


def test_blank_user_edit_falls_back_to_ai_text():
    assert "Texto da IA." in render([req(1, user_edited_text="   ")])


def test_draft_shows_minuta_and_issued_shows_number():
    draft = render([req(1)])
    assert "MINUTA — SEM VALOR OFICIAL" in draft and "Nº" not in draft
    issued = render([req(1)], note_number="192/2026")
    assert "NOTA DEVOLUTIVA Nº 192/2026" in issued and "MINUTA" not in issued


def test_note_structure():
    md = render([req(2, legal_topic="Segundo"), req(1, legal_topic="Primeiro"),
                 req(3, legal_basis="", suggested_solution="", source="manual", grounded=False)])
    assert md.index("## 1. Primeiro") < md.index("## 2. Segundo")
    assert "184.920" in md and "14/10/2026" in md
    assert "art. 198 da Lei nº 6.015/1973" in md and "art. 205" in md and "(20 dias)" in md
    assert "_[a completar pelo escrevente]_" in md
    assert "Campinas, 15 de outubro de 2026." in md
    assert "Fulana de Tal" in md and "1º RI DE TESTE" in md


def test_plain_text_strips_markdown():
    txt = markdown_to_plain_text(render([req(1)], note_number="1/2026"))
    assert "**" not in txt and "## " not in txt and "&nbsp;" not in txt and "\\_" not in txt
    assert "NOTA DEVOLUTIVA Nº 1/2026" in txt
    assert "Fundamentação: art. 195" in txt


def test_rrf_merge_rewards_presence_in_both_lists():
    a, b, c = {"_id": "a"}, {"_id": "b"}, {"_id": "c"}
    merged = rrf_merge([[a, b], [c, b]])
    assert [d["_id"] for d in merged] == ["b", "a", "c"]


def test_rrf_merge_handles_empty_lists():
    assert rrf_merge([[], []]) == []
    assert [d["_id"] for d in rrf_merge([[{"_id": "x"}], []])] == ["x"]
