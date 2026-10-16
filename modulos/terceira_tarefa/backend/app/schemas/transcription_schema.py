from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

BookType = Literal["transcricao_imobiliaria", "nascimento", "casamento", "obito"]
RecordStatus = Literal["analyzed", "verified"]


# ---------- Saída estruturada exigida do VLM ----------

class PartyEntity(BaseModel):
    role: str = Field(description="Ex: transmitente, adquirente, nubente, pai, mãe, declarante, falecido, registrado")
    name_standardized: str = Field(description="Nome completo com grafia contemporânea padronizada em CAIXA ALTA, sem abreviações")
    name_original: str = Field(description="Nome exatamente como escrito no manuscrito original, preservando abreviações (ex: M.el, Snr., d'Oliveira)")


class HistoricalTranscriptionResult(BaseModel):
    entry_number: Optional[str] = Field(description="Número do assento/registro/transcrição como aparece na página, ou null")
    entry_date_text: Optional[str] = Field(description="Data do assento exatamente como escrita (por extenso), ou null")
    entry_date_iso: Optional[str] = Field(description="Data normalizada no formato YYYY-MM-DD, ou null se não for possível determinar")
    transcription_raw: str = Field(description="Transcrição literal paleográfica de todo o assento, com [ilegível] nos trechos não decifráveis")
    parties: List[PartyEntity] = Field(description="Todas as pessoas com papel jurídico no ato")
    confrontants_or_parents: List[str] = Field(description="Confrontantes do imóvel (Registro de Imóveis) ou filiação/avós (Registro Civil)")
    confidence_score: float = Field(description="Nível de confiança global da leitura, de 0.0 a 1.0")


# ---------- Persistência / API ----------

class PartyRecord(PartyEntity):
    phonetic: str = ""


class HistoricalRecord(BaseModel):
    id: str = Field(alias="_id")
    book_type: BookType
    book_number: str
    page_number: int
    entry_number: Optional[str] = None
    entry_date_text: Optional[str] = None
    entry_date_iso: Optional[str] = None
    image_url: str
    image_enhanced_url: Optional[str] = None
    transcription_raw: str
    status: RecordStatus
    parties: List[PartyRecord] = []
    confrontants_or_relatives: List[str] = []
    confidence_score: float
    vlm_model: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}


class PartyUpdate(BaseModel):
    role: str
    name_standardized: str
    name_original: str


class RecordUpdate(BaseModel):
    """Correção humana. Campos omitidos permanecem inalterados."""
    entry_number: Optional[str] = None
    entry_date_text: Optional[str] = None
    entry_date_iso: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    transcription_raw: Optional[str] = None
    parties: Optional[List[PartyUpdate]] = None
    confrontants_or_relatives: Optional[List[str]] = None
    status: Optional[RecordStatus] = None


class SearchHit(HistoricalRecord):
    score: Optional[float] = None
    highlights: List[str] = []


class SearchResponse(BaseModel):
    total: int
    engine: Literal["atlas_search", "fallback"]
    results: List[SearchHit]
