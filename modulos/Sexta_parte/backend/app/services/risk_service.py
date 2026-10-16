"""Consolidação das camadas de verificação em score e nível de risco únicos."""
from app.schemas.fraud_schema import AuditChecks

WEIGHTS = {"tampering": 0.45, "signature": 0.35, "procuration": 0.20}
PROCURATION_RISK = {"APROVADO": 0, "ALERTA": 55, "REPROVADO": 100}


def level_for(score: int) -> str:
    if score >= 75:
        return "CRITICO"
    if score >= 50:
        return "ALTO"
    if score >= 25:
        return "MEDIO"
    return "BAIXO"


def consolidate(checks: AuditChecks, prior_alerts: int = 0) -> tuple[int, str, list[str], str]:
    """Retorna (score, nível, fatores, recomendação)."""
    components: dict[str, int] = {"tampering": checks.document_tampering.score}
    factors: list[str] = []

    sig = checks.signature_matching
    if sig.match_score is not None:
        components["signature"] = 100 - sig.match_score
    proc = checks.power_of_attorney_censec
    if proc.status in PROCURATION_RISK:
        components["procuration"] = PROCURATION_RISK[proc.status]

    total_w = sum(WEIGHTS[k] for k in components)
    weighted = sum(WEIGHTS[k] * v for k, v in components.items()) / total_w
    # Um único sinal forte não pode ser diluído pelos demais.
    score = max(weighted, 0.85 * max(components.values()))

    if checks.document_tampering.status == "SUSPEITO":
        factors.append("Indícios de adulteração material no documento.")
    if sig.status == "DIVERGENTE":
        factors.append("Assinatura divergente do cartão de autógrafo.")
    elif sig.status == "INCONCLUSIVO":
        factors.append("Cotejo de assinatura inconclusivo.")
    elif sig.status == "NAO_EXECUTADO":
        factors.append("Cotejo de assinatura não realizado.")
    if proc.status == "REPROVADO":
        factors.append("Procuração revogada ou inconsistente.")
        score = max(score, 90)
    elif proc.status == "ALERTA":
        factors.append("Procuração requer confirmação na CENSEC.")
    if checks.document_tampering.status == "SUSPEITO" and sig.status == "DIVERGENTE":
        score = max(score, 85)
    if prior_alerts:
        factors.append(f"Reincidência: CPF com {prior_alerts} alerta(s) de alto risco anterior(es).")
        score += min(15, 5 * prior_alerts)

    score = int(round(min(100, max(0, score))))
    level = level_for(score)
    recommendation = {
        "BAIXO": "Sem indícios relevantes. Prosseguir com a conferência usual do ato.",
        "MEDIO": "Conferir pessoalmente os pontos sinalizados antes da lavratura; registrar a conferência.",
        "ALTO": "Reter o ato para conferência do titular. Recomenda-se comparecimento presencial com "
                "biometria e documento original.",
        "CRITICO": "Não lavrar o ato. Submeter ao Oficial titular; avaliar recusa por suspeita de falsidade "
                   "e comunicação aos órgãos competentes.",
    }[level]
    return score, level, factors, recommendation
