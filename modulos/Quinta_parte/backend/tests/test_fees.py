import pytest

from app.catalog import FEE_SCHEDULES
from app.schemas.triage_schema import FeeSchedule
from app.services.fee_calculator_service import FeeError, brl, calculate_fixed, calculate_tiered

INVENTARIO = FeeSchedule.model_validate(next(f for f in FEE_SCHEDULES if f["service_type"] == "inventario_extrajudicial"))
ESCRITURA = FeeSchedule.model_validate(next(f for f in FEE_SCHEDULES if f["service_type"] == "escritura_com_valor"))
FIXOS = FeeSchedule.model_validate(next(f for f in FEE_SCHEDULES if f["service_type"] == "atos_valor_fixo"))


def test_inventario_450_mil_bate_com_exemplo_da_spec():
    r = calculate_tiered(INVENTARIO, 450000.0, "Inventário")
    assert (r.base_fee, r.state_funds, r.municipal_tax) == (1920.00, 434.80, 96.00)
    assert r.total_estimate == 2450.80
    assert r.taxes_and_funds == 530.80


@pytest.mark.parametrize("value,fee", [(0, 420.50), (50000.0, 420.50), (50000.004, 890.00),
                                       (50000.01, 890.00), (150000.0, 890.00), (5_000_000, 3600.00)])
def test_limites_de_faixa(value, fee):
    assert calculate_tiered(ESCRITURA, value, "Escritura").base_fee == fee


def test_iss_arredonda_centavos():
    r = calculate_tiered(ESCRITURA, 10000, "Escritura")
    assert r.municipal_tax == 21.03  # 5% de 420,50 = 21,025 → 21,03
    assert r.total_estimate == round(420.50 + 85.10 + 21.03, 2)


def test_valor_negativo():
    with pytest.raises(FeeError):
        calculate_tiered(ESCRITURA, -1, "Escritura")


def test_ato_fixo():
    r = calculate_fixed(FIXOS, "certidao_breve_relato")
    assert r.declared_value is None
    assert r.total_estimate == round(45.20 + 9.15 + 2.26, 2)
    assert "estimativa preliminar" in r.legal_disclaimer


def test_brl():
    assert brl(2450.8) == "R$ 2.450,80"
    assert brl(1234567.891) == "R$ 1.234.567,89"
