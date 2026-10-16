"""Cálculo de emolumentos: taxa notarial + fundos estaduais + ISSQN (sobre a taxa notarial).

Os valores vêm sempre da coleção fee_schedules — o LLM nunca calcula nem inventa valores.
Contas em Decimal com arredondamento comercial (meio para cima) em centavos.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.core.config import settings
from app.core.database import get_repository
from app.schemas.triage_schema import FeeEstimateResult, FeeRule, FeeSchedule

CENT = Decimal("0.01")


class FeeError(ValueError):
    pass


def _d(value: float) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def brl(value: Optional[float]) -> str:
    if value is None:
        return "—"
    s = f"{value:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _build(service_name: str, notary: Decimal, fund: Decimal, iss_pct: Decimal,
           declared_value: Optional[float], tier_label: Optional[str]) -> FeeEstimateResult:
    iss = (notary * iss_pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    taxes = fund + iss
    return FeeEstimateResult(
        service_name=service_name,
        declared_value=declared_value,
        base_fee=_money(notary),
        state_funds=_money(fund),
        municipal_tax=_money(iss),
        taxes_and_funds=_money(taxes),
        total_estimate=_money(notary + taxes),
        tier_label=tier_label,
        legal_disclaimer=settings.fee_disclaimer,
    )


def calculate_tiered(schedule: FeeSchedule, declared_value: float, service_name: str) -> FeeEstimateResult:
    if declared_value < 0:
        raise FeeError("O valor declarado não pode ser negativo.")
    value = _d(declared_value)
    # Faixas contíguas em centavos (0–50.000,00 / 50.000,01–150.000,00 ...): vale a primeira
    # cujo teto cobre o valor, o que também resolve frações de centavo entre duas faixas.
    for tier in sorted(schedule.tiers, key=lambda t: t.min_value):
        if tier.max_value is None or value <= _d(tier.max_value):
            label = (f"{brl(tier.min_value)} a {brl(tier.max_value)}" if tier.max_value is not None
                     else f"acima de {brl(tier.min_value)}")
            return _build(service_name, _d(tier.notary_fee), _d(tier.state_fund),
                          _d(tier.municipal_tax_percent), declared_value, label)
    raise FeeError(f"Nenhuma faixa da tabela {schedule.id} cobre o valor {brl(declared_value)}.")


def calculate_fixed(schedule: FeeSchedule, key: str) -> FeeEstimateResult:
    svc = schedule.fixed_services.get(key)
    if svc is None:
        raise FeeError(f"Serviço '{key}' não encontrado na tabela {schedule.id}.")
    return _build(svc.label, _d(svc.notary_fee), _d(svc.state_fund),
                  _d(schedule.municipal_tax_percent), None, None)


async def load_schedule(state: str, service_type: str) -> FeeSchedule:
    raw = await get_repository().get_fee_schedule(state, service_type)
    if raw is None:
        raise FeeError(f"Tabela de emolumentos '{service_type}' não cadastrada para {state}.")
    return FeeSchedule.model_validate(raw)


async def estimate_for_act(requirement: dict, state: str,
                           declared_value: Optional[float]) -> FeeEstimateResult:
    rule = FeeRule.model_validate(requirement["fee_rule"])
    schedule = await load_schedule(state, rule.service_type)
    if rule.kind == "fixed":
        return calculate_fixed(schedule, rule.fixed_key or requirement["act_type"])
    if declared_value is None:
        raise FeeError("Este ato exige o valor declarado dos bens para o cálculo.")
    return calculate_tiered(schedule, declared_value, requirement["name"])
