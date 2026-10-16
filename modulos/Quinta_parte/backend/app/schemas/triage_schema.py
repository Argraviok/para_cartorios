from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

TriageStatus = Literal["in_progress", "ready_for_counter", "human_takeover"]
# Etapa interna da máquina de estados do diálogo
TriageStage = Literal["ask_name", "identify_act", "ask_value", "collect_docs", "done"]
DocStatus = Literal["PENDENTE", "ENVIADO", "VALIDADO", "REJEITADO"]
Sender = Literal["user", "bot", "attendant", "system"]


# ---------------------------------------------------------------------------
# Catálogo (act_requirements / fee_schedules)
# ---------------------------------------------------------------------------


class RequiredDocument(BaseModel):
    doc_name: str
    description: str = ""
    required: bool = True
    # Documentos com prazo de emissão (ex.: certidões "atualizadas 90 dias")
    max_age_days: Optional[int] = None
    accepted_types: list[str] = Field(default_factory=list)


class FeeRule(BaseModel):
    kind: Literal["tiered", "fixed"]
    service_type: str  # fee_schedules.service_type
    fixed_key: Optional[str] = None  # chave em fixed_services, quando kind == "fixed"


class ActRequirement(BaseModel):
    act_type: str
    name: str
    summary: str
    keywords: list[str]
    requires_declared_value: bool = False
    value_question: Optional[str] = None
    documents: list[RequiredDocument]
    fee_rule: FeeRule
    notes: list[str] = Field(default_factory=list)


class FeeTier(BaseModel):
    min_value: float
    max_value: Optional[float] = None  # None = sem teto
    notary_fee: float
    state_fund: float
    municipal_tax_percent: float


class FixedService(BaseModel):
    label: str
    notary_fee: float
    state_fund: float = 0.0


class FeeSchedule(BaseModel):
    id: str = Field(alias="_id")
    state: str
    service_type: str
    label: str = ""
    valid_from: Optional[str] = None
    source: str = ""
    municipal_tax_percent: float = 5.0
    tiers: list[FeeTier] = Field(default_factory=list)
    fixed_services: dict[str, FixedService] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class FeeEstimateResult(BaseModel):
    service_name: str
    declared_value: Optional[float] = None
    base_fee: float
    state_funds: float
    municipal_tax: float
    taxes_and_funds: float
    total_estimate: float
    tier_label: Optional[str] = None
    legal_disclaimer: str


# ---------------------------------------------------------------------------
# Triagem
# ---------------------------------------------------------------------------


class ChecklistItem(BaseModel):
    doc_name: str
    description: str = ""
    required: bool = True
    max_age_days: Optional[int] = None
    status: DocStatus = "PENDENTE"
    image_url: Optional[str] = None
    content_type: Optional[str] = None
    rejection_reason: Optional[str] = None
    ai_feedback: Optional[str] = None
    document_type_identified: Optional[str] = None
    issue_date: Optional[str] = None
    validated_by: Optional[Literal["ai", "attendant"]] = None
    uploaded_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    sender: Sender
    message: str
    timestamp: datetime
    attendant_name: Optional[str] = None
    attachment_url: Optional[str] = None


class Triage(BaseModel):
    protocol_id: str
    customer_name: Optional[str] = None
    customer_contact: str
    channel: Literal["webchat", "whatsapp"] = "webchat"
    state: str = "SP"
    act_type: Optional[str] = None
    act_name: Optional[str] = None
    stage: TriageStage = "identify_act"
    status: TriageStatus = "in_progress"
    human_requested: bool = False
    attendant_name: Optional[str] = None
    declared_value: Optional[float] = None
    estimated_total: Optional[float] = None
    fee_estimate: Optional[FeeEstimateResult] = None
    checklist: list[ChecklistItem] = Field(default_factory=list)
    chat_history: list[ChatMessage] = Field(default_factory=list)
    counter_ticket: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TriageSummary(BaseModel):
    """Linha do inbox do escrevente (sem histórico completo)."""

    protocol_id: str
    customer_name: Optional[str] = None
    customer_contact: str
    channel: str
    act_name: Optional[str] = None
    status: TriageStatus
    human_requested: bool
    attendant_name: Optional[str] = None
    estimated_total: Optional[float] = None
    docs_validated: int
    docs_required: int
    docs_rejected: int
    last_message: Optional[str] = None
    last_sender: Optional[str] = None
    counter_ticket: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Requisições / respostas
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    customer_contact: str = Field(min_length=3, max_length=120)
    customer_name: Optional[str] = Field(None, max_length=120)
    channel: Literal["webchat", "whatsapp"] = "webchat"


class UserMessageRequest(BaseModel):
    protocol_id: Optional[str] = None
    # Usados para abrir a sessão quando protocol_id não é informado (ex.: WhatsApp)
    customer_contact: Optional[str] = Field(None, max_length=120)
    customer_name: Optional[str] = Field(None, max_length=120)
    channel: Literal["webchat", "whatsapp"] = "webchat"
    message: str = Field(min_length=1, max_length=4000)


class TurnResponse(BaseModel):
    triage: Triage
    replies: list[ChatMessage]


class AttendantMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    attendant_name: str = Field("Escrevente", max_length=80)


class TakeoverRequest(BaseModel):
    attendant_name: str = Field("Escrevente", max_length=80)


class ChecklistReviewRequest(BaseModel):
    status: Literal["VALIDADO", "REJEITADO", "PENDENTE"]
    rejection_reason: Optional[str] = Field(None, max_length=500)
    notify_customer: bool = True


class DocumentVerificationResult(BaseModel):
    document_type_identified: str = Field(
        description="Ex: RG, CNH, Certidão de Casamento, Comprovante de Residência"
    )
    is_legible: bool = Field(description="Indica se o documento está legível ou se a foto está cortada/embaçada")
    matches_expected: bool = Field(description="O documento corresponde ao tipo exigido no checklist")
    issue_date_identified: Optional[str] = Field(
        None, description="Data de expedição ou emissão encontrada, no formato AAAA-MM-DD"
    )
    validation_status: Literal[
        "APROVADO", "REJEITADO_ILEGIVEL", "EXPIRADO", "DOCUMENTO_INCORRETO", "REVISAO_MANUAL"
    ]
    feedback_to_user: str = Field(
        description="Mensagem clara e amigável em português explicando o status ao cidadão"
    )
    engine: str = "heuristic"


class UploadDocResponse(BaseModel):
    triage: Triage
    verification: DocumentVerificationResult
    doc_index: int
    replies: list[ChatMessage]
