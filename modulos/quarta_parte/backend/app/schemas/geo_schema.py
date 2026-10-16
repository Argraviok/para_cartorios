"""Schemas Pydantic compartilhados entre extração (LLM), serviços, API e MongoDB."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ContinuityStatus = Literal["REGULAR", "QUEBRA_DETECTADA", "ALERTA"]


# ---------------------------------------------------------------------------
# Saídas estruturadas da LLM
# ---------------------------------------------------------------------------


class RegistryAct(BaseModel):
    """Um ato lançado na matrícula (R-1, AV-2, ...)."""

    act_code: str = Field(description="Código do ato, ex: 'R-1', 'AV-2'")
    act_date: Optional[str] = Field(default=None, description="Data do ato (DD/MM/AAAA)")
    act_type: str = Field(
        description="Natureza do ato: COMPRA_E_VENDA, DOACAO, PARTILHA, ARREMATACAO, "
        "USUCAPIAO, HIPOTECA, PENHORA, INDISPONIBILIDADE, USUFRUTO, ALIENACAO_FIDUCIARIA, "
        "CANCELAMENTO, AVERBACAO_CONSTRUCAO, CASAMENTO, OUTRO"
    )
    is_ownership_transfer: bool = Field(description="True se o ato transmite a propriedade")
    is_encumbrance: bool = Field(description="True se o ato constitui ônus/gravame/restrição")
    grantors: list[str] = Field(default_factory=list, description="Transmitentes/devedores")
    grantees: list[str] = Field(default_factory=list, description="Adquirentes/credores")
    cancels_act_code: Optional[str] = Field(
        default=None, description="Se for cancelamento, o código do ato cancelado (ex: 'R-3')"
    )
    court_or_creditor: Optional[str] = Field(default=None, description="Vara/juízo ou credor")
    summary: str = Field(description="Resumo de uma linha do ato")


class TopoVertex(BaseModel):
    point_name: str = Field(description="Nome do vértice, ex: 'P-01', 'V-01'")
    utm_e: Optional[float] = None
    utm_n: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    azimuth: Optional[str] = Field(
        default=None, description="Azimute do segmento que PARTE deste vértice, ex: 45°30'15\""
    )
    distance_meters: Optional[float] = Field(
        default=None, description="Distância do segmento que PARTE deste vértice até o próximo"
    )
    confrontant: Optional[str] = Field(
        default=None, description="Confrontante ao longo do segmento que parte deste vértice"
    )
    confrontant_registry: Optional[str] = Field(
        default=None, description="Matrícula do confrontante, se citada"
    )
    direction: Optional[str] = Field(default=None, description="Norte, Sul, Leste, Oeste, Frente...")


class MemorialExtraction(BaseModel):
    declared_area_m2: Optional[float] = None
    declared_perimeter_m: Optional[float] = None
    utm_zone: Optional[int] = Field(default=None, description="Fuso UTM (ex: 23)")
    datum: Optional[str] = Field(default=None, description="Datum (SIRGAS 2000, SAD-69...)")
    vertices: list[TopoVertex] = Field(default_factory=list)


class PropertyAddress(BaseModel):
    """Localização textual do imóvel, usada para geocodificação aproximada."""

    street: Optional[str] = Field(default=None, description="Logradouro com tipo, ex: 'Rua das Acácias'")
    number: Optional[str] = Field(default=None, description="Número predial, se houver")
    lot: Optional[str] = Field(default=None, description="Lote, ex: '13'")
    block: Optional[str] = Field(default=None, description="Quadra, ex: 'F'")
    subdivision: Optional[str] = Field(default=None, description="Loteamento/condomínio, ex: 'Jardim das Acácias'")
    neighborhood: Optional[str] = Field(default=None, description="Bairro")
    city: Optional[str] = Field(default=None, description="Município (do imóvel; se omisso, o do cartório)")
    state: Optional[str] = Field(default=None, description="UF com 2 letras, ex: 'SP'")


class RegistryExtraction(BaseModel):
    registry_number: str = Field(description="Número da matrícula, ex: '89.214'")
    registry_office: Optional[str] = Field(default=None, description="Cartório de Registro de Imóveis")
    property_description: Optional[str] = None
    declared_area_m2: Optional[float] = Field(default=None, description="Área declarada em m²")
    property_address: Optional[PropertyAddress] = None
    utm_zone: Optional[int] = Field(default=None, description="Fuso UTM, se a descrição trouxer coordenadas")
    datum: Optional[str] = Field(default=None, description="Datum das coordenadas (SIRGAS 2000, SAD-69...)")
    vertices: list[TopoVertex] = Field(
        default_factory=list,
        description="Vértices do perímetro SE a descrição do imóvel na matrícula os trouxer "
        "(coordenadas e/ou azimutes e distâncias); vazio caso contrário",
    )
    acts: list[RegistryAct] = Field(default_factory=list)


class TitleExtraction(BaseModel):
    """Título apresentado (contrato/escritura) — quem está vendendo."""

    sellers: list[str] = Field(default_factory=list)
    buyers: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resultados de análise
# ---------------------------------------------------------------------------


class ChainLink(BaseModel):
    act_code: str
    act_date: Optional[str] = None
    act_type: str
    grantors: list[str]
    grantees: list[str]
    is_continuous: bool = Field(description="Transmitente deste ato era titular no ato anterior?")
    note: Optional[str] = None


class ActiveLien(BaseModel):
    act_code: str
    type: str
    court_or_creditor: Optional[str] = None
    summary: str
    status: Literal["VIGENTE"] = "VIGENTE"


class SubjectiveContinuity(BaseModel):
    status: ContinuityStatus
    current_registered_owner: str
    current_owner_act: Optional[str] = None
    seller_in_contract: Optional[str] = None
    active_liens: list[ActiveLien] = Field(default_factory=list)
    chain: list[ChainLink] = Field(default_factory=list)
    observation: str


class Confrontant(BaseModel):
    direction: Optional[str] = None
    name: str
    segment: str
    registry: Optional[str] = None


class Segment(BaseModel):
    from_point: str
    to_point: str
    azimuth: Optional[str] = None
    declared_distance_m: Optional[float] = None
    computed_distance_m: float
    confrontant: Optional[str] = None
    coordinates: Optional[list[list[float]]] = Field(
        default=None, description="[[lon, lat], [lon, lat]] para renderização"
    )


class GeometryAnalysis(BaseModel):
    source: Literal["MEMORIAL", "MATRICULA"] = "MEMORIAL"
    georeference_method: Literal["COORDINATES", "MANUAL_ANCHOR", "NONE"] = "NONE"
    is_closed: bool
    gap_meters: float
    closure_method: Literal["TRAVERSE", "COORDINATES", "NONE"]
    declared_area: Optional[float] = None
    calculated_area: float
    area_difference_percent: Optional[float] = None
    perimeter_m: float
    is_valid_polygon: bool
    is_georeferenced: bool
    location_geojson: Optional[dict] = None
    closure_gap_line: Optional[list[list[float]]] = Field(
        default=None,
        description="[vértice inicial, ponto onde a poligonal termina] quando não fecha (mesmo sistema de Segment)",
    )
    segments: list[Segment] = Field(default_factory=list)
    confrontants: list[Confrontant] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ApproximateLocation(BaseModel):
    lat: float
    lon: float
    precision: Literal["ENDERECO", "RUA", "BAIRRO", "CIDADE"]
    query: str
    display_name: Optional[str] = None
    source: str = "OpenStreetMap Nominatim"


class Alert(BaseModel):
    level: Literal["INFO", "WARNING", "CRITICAL"]
    code: str
    message: str


class ParcelAnalysis(BaseModel):
    id: Optional[str] = None
    registry_number: str
    registry_office: Optional[str] = None
    document_filename: str
    memorial_filename: Optional[str] = None
    subjective_continuity: SubjectiveContinuity
    geometry: Optional[GeometryAnalysis] = None
    approximate_location: Optional[ApproximateLocation] = None
    property_address: Optional[PropertyAddress] = None
    registry_declared_area: Optional[float] = None
    # Vértices extraídos (memorial ou matrícula): permitem reposicionar o polígono sem nova chamada ao LLM
    geometry_input: Optional[MemorialExtraction] = None
    alerts: list[Alert] = Field(default_factory=list)
    extraction_engine: str
    created_at: datetime
