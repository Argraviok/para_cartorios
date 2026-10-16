from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.cpf import format_cpf, is_valid_cpf

RiskLevel = Literal["BAIXO", "MEDIO", "ALTO", "CRITICO"]
OfficerDecision = Literal["PENDENTE", "HOMOLOGADO", "RECUSADO"]
DocumentType = Literal["RG", "CNH", "PROCURACAO", "OUTRO"]
CheckStatus = Literal[
    "APROVADO", "SUSPEITO", "DIVERGENTE", "INCONCLUSIVO", "ALERTA", "REPROVADO", "NAO_APLICAVEL", "NAO_EXECUTADO"
]
DecisionAction = Literal["APROVAR_FE_PUBLICA", "SOLICITAR_PRESENCIAL", "REJEITAR_FALSIDADE"]


# ---------- Resultados dos motores de inspeção ----------

class SuspiciousRegion(BaseModel):
    x: int
    y: int
    w: int
    h: int
    intensity: float = Field(description="Desvio robusto (z-score) do nível de erro da região")


class TamperingCheck(BaseModel):
    status: CheckStatus
    score: int = Field(ge=0, le=100, description="Suspeita de adulteração (0-100)")
    findings: list[str] = []
    suspicious_regions: list[SuspiciousRegion] = []
    source_format: str
    ela_reliable: bool
    vlm_used: bool = False
    vlm_error: Optional[str] = None
    image_width: int
    image_height: int


class SignatureCheck(BaseModel):
    status: CheckStatus
    match_score: Optional[int] = Field(default=None, ge=0, le=100)
    confidence: float = Field(default=0.0, ge=0, le=1)
    metrics: dict[str, float] = {}
    observation: str
    signature_card_id: Optional[str] = None
    vlm_used: bool = False
    vlm_error: Optional[str] = None


class ProcurationCheck(BaseModel):
    status: CheckStatus
    is_valid: Optional[bool] = None
    verified_on_censec: bool = False
    age_days: Optional[int] = None
    book: Optional[str] = None
    page: Optional[str] = None
    act: Optional[str] = None
    origin_office: Optional[str] = None
    observations: list[str] = []


class FacialBiometricsCheck(BaseModel):
    status: CheckStatus = "NAO_EXECUTADO"
    similarity_score: Optional[float] = None
    liveness_detected: Optional[bool] = None
    observation: str = "Biometria facial não integrada neste MVP — conferir presencialmente no balcão."


class AuditChecks(BaseModel):
    document_tampering: TamperingCheck
    signature_matching: SignatureCheck
    power_of_attorney_censec: ProcurationCheck
    facial_biometrics: FacialBiometricsCheck = FacialBiometricsCheck()


# ---------- Entrada ----------

class ProcurationInput(BaseModel):
    book: Optional[str] = None
    page: Optional[str] = None
    act: Optional[str] = None
    origin_office: Optional[str] = None
    issued_on: Optional[date] = None
    revocation_declared: bool = False
    censec_confirmed_on: Optional[date] = None

    def is_empty(self) -> bool:
        return not any([self.book, self.page, self.act, self.origin_office, self.issued_on,
                        self.revocation_declared, self.censec_confirmed_on])


class DecisionHistoryEntry(BaseModel):
    action: DecisionAction
    decision: OfficerDecision
    officer_name: str
    notes: str
    decided_at: datetime


class DecisionRequest(BaseModel):
    action: DecisionAction
    officer_name: str = Field(min_length=3, max_length=120)
    notes: str = Field(min_length=10, max_length=4000,
                       description="Justificativa obrigatória, registrada no log de auditoria")

    @field_validator("officer_name", "notes")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Campo obrigatório")
        return v


# ---------- Saída ----------

class FraudAudit(BaseModel):
    id: str
    protocol_number: str
    service_type: str
    document_type: DocumentType
    presenter_name: Optional[str] = None
    presenter_cpf: Optional[str] = None
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    tampering_detected: bool
    tampering_details: list[str]
    signature_match_score: Optional[int] = None
    procuration_verified: Optional[bool] = None
    recommendation_to_officer: str
    risk_factors: list[str] = []
    checks: AuditChecks
    files: dict[str, bool] = Field(default_factory=dict, description="Arquivos disponíveis para visualização")
    officer_decision: OfficerDecision = "PENDENTE"
    officer_notes: Optional[str] = None
    in_person_requested: bool = False
    decision_history: list[DecisionHistoryEntry] = []
    created_at: datetime
    decided_at: Optional[datetime] = None


class FraudAuditSummary(BaseModel):
    id: str
    protocol_number: str
    service_type: str
    document_type: DocumentType
    presenter_name: Optional[str] = None
    risk_level: RiskLevel
    risk_score: int
    tampering_detected: bool
    signature_match_score: Optional[int] = None
    officer_decision: OfficerDecision
    in_person_requested: bool = False
    created_at: datetime


# ---------- Cartões de firma ----------

class SignatureCard(BaseModel):
    id: str
    cpf: str
    full_name: str
    card_number: Optional[str] = None
    created_at: datetime


class SignatureCardCreate(BaseModel):
    cpf: str
    full_name: str = Field(min_length=3, max_length=200)
    card_number: Optional[str] = Field(default=None, max_length=40)

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, v: str) -> str:
        if not is_valid_cpf(v):
            raise ValueError("CPF inválido")
        return format_cpf(v)
