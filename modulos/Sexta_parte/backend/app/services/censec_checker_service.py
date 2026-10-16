"""Validação de procurações (livro, folha, ato, cartório de origem, vigência e revogação).

A CENSEC não oferece API pública de consulta automatizada; este MVP valida os dados informados
pelo escrevente (incluindo a data da certidão/consulta de não-revogação feita no portal). A
interface `CensecGateway` permite plugar uma integração oficial quando disponível.
"""
from datetime import date
from typing import Optional, Protocol

from app.core.config import get_settings
from app.schemas.fraud_schema import ProcurationCheck, ProcurationInput


class CensecGateway(Protocol):
    async def is_revoked(self, data: ProcurationInput) -> Optional[bool]:
        """True/False quando a consulta for conclusiva; None se indisponível."""


class ManualCensecGateway:
    async def is_revoked(self, data: ProcurationInput) -> Optional[bool]:
        return None


_gateway: CensecGateway = ManualCensecGateway()


def set_gateway(gateway: CensecGateway) -> None:
    global _gateway
    _gateway = gateway


async def check_procuration(data: ProcurationInput, document_type: str, today: date | None = None) -> ProcurationCheck:
    s = get_settings()
    today = today or date.today()

    if data.is_empty():
        if document_type == "PROCURACAO":
            return ProcurationCheck(status="ALERTA", observations=[
                "Documento é procuração, mas livro, folha, ato e cartório de origem não foram informados."])
        return ProcurationCheck(status="NAO_APLICAVEL", observations=["Ato sem procuração vinculada."])

    obs: list[str] = []
    status = "APROVADO"
    is_valid: Optional[bool] = True

    missing = [label for label, v in [("livro", data.book), ("folha", data.page), ("cartório de origem", data.origin_office)] if not v]
    if missing:
        status = "ALERTA"
        obs.append("Dados de identificação da procuração incompletos: " + ", ".join(missing) + ".")

    age_days = None
    if data.issued_on:
        age_days = (today - data.issued_on).days
        if age_days < 0:
            status, is_valid = "REPROVADO", False
            obs.append("Data de lavratura posterior à data atual — dado inconsistente.")
    else:
        status = "ALERTA" if status == "APROVADO" else status
        obs.append("Data de lavratura não informada; vigência não pôde ser avaliada.")

    revoked = await _gateway.is_revoked(data)
    if data.revocation_declared or revoked:
        status, is_valid = "REPROVADO", False
        obs.append("Revogação declarada/registrada para esta procuração — ato não pode ser praticado com ela.")

    confirmation_age = (today - data.censec_confirmed_on).days if data.censec_confirmed_on else None
    verified = revoked is False or (confirmation_age is not None and 0 <= confirmation_age <= s.censec_confirmation_max_age_days)

    if is_valid and age_days is not None and age_days > s.procuration_alert_days and not verified:
        status = "ALERTA"
        obs.append(f"Procuração lavrada há {age_days} dias (mais de {s.procuration_alert_days // 365} anos) "
                   "sem confirmação recente de não-revogação na CENSEC.")
    elif is_valid and not verified:
        if status == "APROVADO":
            status = "ALERTA"
        obs.append(f"Consultar a CENSEC e registrar a data da certidão de não-revogação "
                   f"(válida por {s.censec_confirmation_max_age_days} dias).")
    elif verified and is_valid:
        obs.append(f"Não-revogação confirmada na CENSEC em {data.censec_confirmed_on:%d/%m/%Y}.")

    return ProcurationCheck(
        status=status, is_valid=is_valid, verified_on_censec=verified, age_days=age_days,
        book=data.book, page=data.page, act=data.act, origin_office=data.origin_office, observations=obs,
    )
