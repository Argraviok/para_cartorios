from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.enums import VicioCode


class NormativeRef(BaseModel):
    diploma: str = Field(examples=["Lei 6.015/1973"])
    artigo: str | None = Field(default=None, examples=["195"])


class JurisprudenceRef(BaseModel):
    orgao: str
    numero: str
    ementa: str
    source_url: str | None = None


class PrecedentBase(BaseModel):
    vicio_code: VicioCode
    title: str
    scope: Literal["nacional", "estadual"] = "nacional"
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    normative_refs: list[NormativeRef] = Field(min_length=1)
    jurisprudence: list[JurisprudenceRef] = []
    recommended_text: str
    suggested_solution: str
    vigente: bool = True

    @model_validator(mode="after")
    def _uf_for_state_scope(self):
        if self.scope == "estadual" and not self.uf:
            raise ValueError("uf é obrigatório quando scope='estadual'")
        if self.uf:
            self.uf = self.uf.upper()
        return self

    def build_embedding_text(self) -> str:
        parts = [self.title, self.recommended_text, *(j.ementa for j in self.jurisprudence)]
        return "\n".join(parts)


class PrecedentCreate(PrecedentBase):
    id: str = Field(pattern=r"^prec_[a-z0-9_]+$", examples=["prec_outorga_conjugal_02"])


class PrecedentOut(PrecedentBase):
    id: str
    verified: bool
    verified_by: str | None = None
    verified_at: datetime | None = None
    embedding_model: str | None = None
    updated_at: datetime | None = None
