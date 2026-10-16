from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.enums import VicioCode

NoteStatus = Literal["draft", "issuing", "issued"]


# ---------- Request ----------
class IssueInput(BaseModel):
    vicio_code: VicioCode
    title: str | None = Field(default=None, description="Obrigatório quando vicio_code='outro'.")
    case_facts: str = Field(min_length=20, description="Fatos concretos observados pelo escrevente no título/matrícula.")

    @model_validator(mode="after")
    def _title_for_outro(self):
        if self.vicio_code == VicioCode.OUTRO and not (self.title and self.title.strip()):
            raise ValueError("title é obrigatório quando vicio_code='outro'")
        return self


class GenerateNoteRequest(BaseModel):
    protocol_number: str
    protocol_date: date
    act_type: str = Field(min_length=1)
    presenter_name: str = Field(min_length=1)
    uf: str = Field(pattern=r"^[A-Za-z]{2}$")
    issues: list[IssueInput] = Field(min_length=1)

    @field_validator("protocol_number")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if not digits:
            raise ValueError("protocol_number deve conter dígitos")
        return digits

    @field_validator("uf")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


# ---------- Schema que o LLM preenche (só o que é dele) ----------
class LLMRequirement(BaseModel):
    vicio_code: VicioCode = Field(description="Código do vício, exatamente como informado no bloco <fatos>.")
    legal_topic: str = Field(description="Título formal e conciso do vício registral/notarial.")
    precedent_ids: list[str] = Field(
        description="IDs das fichas fornecidas em <ficha id=...> que fundamentam esta exigência. Use apenas IDs fornecidos."
    )
    justification_draft: str = Field(
        description="Texto técnico e impessoal descrevendo o vício no caso concreto, usando exclusivamente os fatos fornecidos."
    )
    suggested_solution: str = Field(description="Providência clara e objetiva para o apresentante sanar o vício.")


class LLMNoteDraft(BaseModel):
    requirements: list[LLMRequirement]


# ---------- Nota ----------
class Requirement(BaseModel):
    order: int = Field(ge=1)
    vicio_code: VicioCode
    legal_topic: str
    precedent_ids: list[str] = []
    legal_basis: str = ""
    justification_draft: str
    user_edited_text: str | None = None
    suggested_solution: str
    source: Literal["ai", "manual"]
    grounded: bool

    @property
    def final_text(self) -> str:
        return self.user_edited_text if self.user_edited_text and self.user_edited_text.strip() else self.justification_draft


class DevolutionNote(BaseModel):
    id: str
    note_number: str | None = None
    protocol_number: str
    protocol_date: date
    act_type: str
    presenter_name: str
    uf: str
    status: NoteStatus
    requirements: list[Requirement]
    full_compiled_text: str
    llm_model: str | None = None
    prompt_version: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    issued_at: datetime | None = None


class DevolutionNoteResponse(DevolutionNote):
    warnings: list[str] = []


class RequirementEdit(BaseModel):
    """Exigência como enviada pelo editor; `order` é recalculado pela posição na lista."""

    vicio_code: VicioCode
    legal_topic: str = Field(min_length=1)
    precedent_ids: list[str] = []
    legal_basis: str = ""
    justification_draft: str
    user_edited_text: str | None = None
    suggested_solution: str
    source: Literal["ai", "manual"]
    grounded: bool


class NotePatch(BaseModel):
    version: int
    requirements: list[RequirementEdit]


class PreviewRequest(BaseModel):
    requirements: list[RequirementEdit]


class PreviewResponse(BaseModel):
    markdown: str
