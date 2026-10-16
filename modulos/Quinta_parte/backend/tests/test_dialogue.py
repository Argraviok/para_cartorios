from datetime import date

import pytest

from app.catalog import ACT_REQUIREMENTS
from app.services.chat_service import _looks_like_name, detect_act, parse_brl_amount
from app.services.doc_vision_service import check_age, parse_issue_date


@pytest.mark.parametrize("text,value", [
    ("450 mil", 450000), ("R$ 450.000,00", 450000), ("uns 1,2 milhão", 1_200_000),
    ("450000", 450000), ("300k", 300000), ("R$ 1.500", 1500), ("2.5 milhões", 2_500_000),
    ("Quanto custa um inventário de 450 mil?", 450000),
])
def test_parse_valor(text, value):
    assert parse_brl_amount(text) == pytest.approx(value)


def test_valor_exige_indicio_fora_da_pergunta():
    assert parse_brl_amount("somos 3 herdeiros", require_hint=True) is None
    assert parse_brl_amount("os bens somam 300 mil", require_hint=True) == 300000


@pytest.mark.parametrize("text,act", [
    ("Quanto custa um inventário?", "inventario_extrajudicial"),
    ("meu pai faleceu e deixou uma casa", "inventario_extrajudicial"),
    ("quero me casar", "habilitacao_casamento"),
    ("preciso de uma procuração", "procuracao_imovel"),
    ("certidão de inteiro teor", "certidao_inteiro_teor"),
    ("vou comprar um imóvel, como faço a escritura?", "escritura_compra_venda"),
    ("bom dia", None),
])
def test_detecta_ato(text, act):
    assert detect_act(text, ACT_REQUIREMENTS) == act


def test_nome():
    assert _looks_like_name("Juliana Santos") == "Juliana Santos"
    assert _looks_like_name("meu nome é joão da silva") == "João Da Silva"
    assert _looks_like_name("quero fazer um inventário") is None
    assert _looks_like_name("tenho 3 filhos") is None


def test_datas_e_prazo():
    today = date(2026, 10, 14)
    assert parse_issue_date("2026-09-01") == (date(2026, 9, 1), False)
    assert parse_issue_date("01/09/2026") == (date(2026, 9, 1), False)
    assert parse_issue_date("3 de março de 2026") == (date(2026, 3, 3), False)
    assert parse_issue_date("Emitida em 2021") == (date(2021, 12, 31), True)
    assert check_age("2026-09-01", 90, today) is None
    assert "2021" in check_age("2021", 90, today)
    assert "15/06/2026" in check_age("2026-06-15", 90, today)
    assert check_age("2020-01-01", None, today) is None
