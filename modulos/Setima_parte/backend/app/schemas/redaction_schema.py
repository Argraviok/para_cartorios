from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Category = Literal["DADO_MEDICO", "DADO_BANCARIO", "FILIACAO_PROTEGIDA", "DADO_FINANCEIRO", "DOCUMENTO_PESSOAL"]
DetectionSource = Literal["regex", "llm", "manual"]
JobStatus = Literal["analyzed", "pending_review", "sanitized"]
ServiceType = Literal[
    "registro_civil",
    "registro_civil_interdicoes",
    "registro_imoveis",
    "tabelionato_notas",
    "protesto",
    "titulos_documentos",
]


class BoundingBox(BaseModel):
    """Retângulo em pontos PDF (origem no canto superior esquerdo, como no PyMuPDF)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _normalize(self) -> "BoundingBox":
        self.x0, self.x1 = sorted((self.x0, self.x1))
        self.y0, self.y1 = sorted((self.y0, self.y1))
        return self


class RedactionItem(BaseModel):
    redaction_id: str
    category: Category
    pii_type: str
    detected_text: str = ""
    page_number: int = Field(ge=1)
    # Um trecho que quebra de linha gera um retângulo por linha.
    bboxes: list[BoundingBox] = Field(min_length=1)
    approved: bool
    legal_basis: str
    source: DetectionSource


class PageInfo(BaseModel):
    page_number: int
    width: float
    height: float
    has_text_layer: bool


class RedactionJob(BaseModel):
    job_id: str
    filename: str
    service_type: ServiceType
    status: JobStatus
    total_detected: int
    items: list[RedactionItem]
    pages: list[PageInfo]
    warnings: list[str] = []
    llm_provider: str
    # Formato enviado pelo operador; o tarjamento opera sempre sobre o PDF (original_sha256).
    source_format: Literal["pdf", "docx", "doc"] = "pdf"
    source_sha256: str | None = None
    original_sha256: str
    sanitized_sha256: str | None = None
    created_at: datetime
    updated_at: datetime
    sanitized_at: datetime | None = None
    sanitized_by: str | None = None


class JobSummary(BaseModel):
    job_id: str
    filename: str
    service_type: ServiceType
    status: JobStatus
    total_detected: int
    created_at: datetime


class ReviewUpdateRequest(BaseModel):
    items: list[RedactionItem]
    operator: str = Field(min_length=1, max_length=120)


class ApplyRequest(BaseModel):
    job_id: str
    items: list[RedactionItem]
    operator: str = Field(min_length=1, max_length=120)
    # Confirmação explícita de que o operador sabe que a operação é irreversível no arquivo gerado.
    confirm_irreversible: bool


class AuditLogEntry(BaseModel):
    """Registro de auditoria. Nunca contém o conteúdo tarjado, apenas metadados."""

    audit_id: str
    job_id: str
    event: Literal["ANALYZE", "REVIEW_SAVED", "SANITIZE"]
    operator: str
    timestamp: datetime
    filename: str
    service_type: str
    categories: dict[str, int] = {}
    approved_count: int = 0
    rejected_count: int = 0
    manual_count: int = 0
    legal_bases: list[str] = []
    original_sha256: str
    sanitized_sha256: str | None = None
    llm_provider: str | None = None
