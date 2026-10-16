from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["CONFORME", "PENDENCIA", "ALERTA"]
Severity = Literal["impeditiva", "recomendavel"]


class Rule(BaseModel):
    rule_code: str
    act_type: str
    name: str
    description: str
    severity: Severity
    legal_ref: str


# --- Saída estruturada exigida do LLM ---
class LLMFinding(BaseModel):
    rule_code: str
    status: Status
    finding: str = Field(description="Explicação sucinta do que foi encontrado ou do motivo do não atendimento.")
    citation: Optional[str] = Field(description="Trecho literal, copiado sem alterações do texto da minuta, que fundamenta o status. Null se o elemento exigido está ausente do documento.")
    page_number: Optional[int] = Field(description="Número da página onde a citação se encontra. Null se não houver citação.")
    recommendation: Optional[str] = Field(description="Ação sugerida para o escrevente sanar a exigência. Null se o status for CONFORME.")


class LLMAnalysis(BaseModel):
    checklist: List[LLMFinding]


# --- Resposta da API ---
class RuleFinding(BaseModel):
    rule_code: str
    rule_name: str
    severity: Severity
    legal_ref: str
    status: Status
    finding: str
    citation: Optional[str] = None
    page_number: Optional[int] = None
    citation_verified: bool = Field(description="True se a citação foi localizada literalmente no texto extraído do PDF.")
    recommendation: Optional[str] = None


class QualificationResponse(BaseModel):
    id: str
    document_title: str
    act_type: str
    created_at: datetime
    overall_status: Literal["APROVADO", "EXIGENCIAS_PENDENTES"]
    checklist: List[RuleFinding]
