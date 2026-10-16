"""Leitura de documentos (PDF via PyMuPDF, DOCX via python-docx, DOC via LibreOffice) e extração
estruturada via LLM.

Provedores:
- gemini   → Gemini (responseJsonSchema); aceita PDF escaneado sem camada de texto.
- openai   → OpenAI Structured Outputs (json_schema strict).
- heuristic→ regex para documentos com layout padronizado (dev/testes, sem chave de API).
"""

import asyncio
import base64
import copy
import io
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, TypeVar

import docx
import pymupdf
from docx.table import Table as DocxTable
import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.geo_schema import (
    MemorialExtraction,
    PropertyAddress,
    RegistryAct,
    RegistryExtraction,
    TitleExtraction,
    TopoVertex,
)

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class ExtractionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Documentos: PDF, DOCX e DOC
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = "PDF, DOCX ou DOC"


def detect_format(data: bytes) -> str:
    """Identifica pelo conteúdo (assinatura), não pela extensão."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04" and b"word/" in data[:4096]:
        return "docx"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # OLE2 (Word 97-2003)
        return "doc"
    raise ExtractionError(f"Formato de arquivo não suportado. Envie {SUPPORTED_FORMATS}.")


def pdf_to_text(data: bytes) -> str:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text("text") for page in doc).strip()
    except Exception as exc:  # PyMuPDF levanta vários tipos
        raise ExtractionError(f"PDF inválido ou corrompido: {exc}") from exc


def docx_to_text(data: bytes) -> str:
    """Parágrafos e tabelas na ordem do documento; células de tabela separadas por ' | '."""
    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"DOCX inválido ou corrompido: {exc}") from exc
    lines: list[str] = []
    for block in doc.iter_inner_content():
        if isinstance(block, DocxTable):
            for row in block.rows:
                cells: list[str] = []
                for cell in row.cells:  # células mescladas se repetem em python-docx
                    t = " ".join(cell.text.split())
                    if not cells or cells[-1] != t:
                        cells.append(t)
                lines.append(" | ".join(cells))
        else:
            lines.append(block.text)
    return "\n".join(lines).strip()


def doc_to_docx(data: bytes) -> bytes:
    """Converte .doc (Word 97-2003) para .docx com LibreOffice headless."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ExtractionError("Arquivos .doc exigem o LibreOffice instalado no servidor. Salve como .docx ou PDF.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "documento.doc"
        src.write_bytes(data)
        # Perfil isolado: permite conversões simultâneas e não interfere no LibreOffice do usuário
        profile = f"-env:UserInstallation=file://{tmp}/lo-profile"
        try:
            subprocess.run(
                [soffice, profile, "--headless", "--convert-to", "docx", "--outdir", tmp, str(src)],
                check=True, capture_output=True, timeout=90,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise ExtractionError(f"Falha ao converter .doc com LibreOffice: {exc}") from exc
        out = Path(tmp) / "documento.docx"
        if not out.exists():
            raise ExtractionError("LibreOffice não gerou o .docx (arquivo .doc corrompido?).")
        return out.read_bytes()


async def document_to_text(data: bytes) -> tuple[str, str]:
    """Devolve (texto, formato)."""
    fmt = detect_format(data)
    if fmt == "pdf":
        return pdf_to_text(data), fmt
    if fmt == "doc":
        data = await asyncio.to_thread(doc_to_docx, data)
    return docx_to_text(data), fmt


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

REGISTRY_PROMPT = """Você é um escrevente de Registro de Imóveis. Extraia da certidão de matrícula abaixo
TODOS os atos (R-n e AV-n) em ordem. Para cada ato:
- is_ownership_transfer=true apenas para atos que transmitem a propriedade (compra e venda, doação,
  partilha, adjudicação, arrematação, usucapião, permuta, dação, integralização).
- is_encumbrance=true para ônus/restrições: hipoteca, penhora, arresto, sequestro, indisponibilidade,
  usufruto, alienação fiduciária, cláusulas restritivas, servidão.
- Para cancelamentos, preencha cancels_act_code com o código do ato cancelado.
- grantors = transmitentes/devedores; grantees = adquirentes/credores. Nomes completos em maiúsculas.
- Para partilha, grantors é o falecido (ex: "ESPÓLIO DE FULANO") e grantees os herdeiros/meeiros.
Também extraia o número da matrícula, o cartório e a área declarada do imóvel em m².
Do texto de descrição do imóvel extraia ainda:
- property_address: logradouro (com o tipo: Rua, Avenida...), número, lote, quadra, loteamento, bairro,
  município e UF. Se o município do imóvel não for citado, use o da comarca do cartório.
- vertices: SOMENTE se a descrição trouxer o perímetro por vértices (coordenadas UTM/geográficas e/ou
  azimutes/rumos e distâncias), na ordem do percurso, com o confrontante de cada lado. Números no
  formato brasileiro (7.465.432,98) devem virar decimal (7465432.98). Não invente vértices a partir de
  medidas de frente/fundos.
- utm_zone e datum, se as coordenadas os informarem."""

MEMORIAL_PROMPT = """Você é um engenheiro agrimensor. Extraia do memorial descritivo abaixo a sequência de
vértices do perímetro, NA ORDEM em que são percorridos. Para cada vértice informe as coordenadas
(UTM E/N ou latitude/longitude, em números decimais), e para o segmento que PARTE dele: azimute (ou rumo,
copiado literalmente), distância em metros, o confrontante e a matrícula do confrontante se citada.
Números no formato brasileiro (7.465.432,98) devem ser convertidos para decimal (7465432.98).
Informe também área (m²), perímetro, fuso UTM e datum declarados."""

TITLE_PROMPT = """Extraia do título/contrato/escritura abaixo os nomes completos dos VENDEDORES
(transmitentes/outorgantes) e COMPRADORES (adquirentes/outorgados), em maiúsculas."""


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


def active_engine() -> str:
    p = settings.llm_provider
    if p == "auto":
        if settings.gemini_api_key:
            return "gemini"
        if settings.openai_api_key:
            return "openai"
        return "heuristic"
    return p


def _strict_schema(schema: dict) -> dict:
    """Adapta o JSON Schema do Pydantic ao modo strict do OpenAI Structured Outputs."""
    schema = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = (2, 5, 12)  # segundos; 503 "high demand" do Gemini costuma passar rápido
MAX_RETRY_WAIT_S = 30  # cota diária esgotada pede horas de espera: não adianta repetir


def _retry_after_seconds(r: httpx.Response) -> Optional[float]:
    """Lê Retry-After ou o RetryInfo.retryDelay ("25177s") do corpo de erro do Google."""
    if r.headers.get("retry-after", "").isdigit():
        return float(r.headers["retry-after"])
    try:
        for detail in r.json()["error"].get("details", []):
            if detail.get("@type", "").endswith("RetryInfo"):
                return float(detail["retryDelay"].rstrip("s"))
    except (ValueError, KeyError, AttributeError, TypeError):
        pass
    return None


async def _post_with_retry(
    url: str, body: dict, headers: dict, delays: tuple[int, ...] = RETRY_DELAYS
) -> httpx.Response:
    """Repete em sobrecarga/erro de rede. Devolve a última resposta; erro de rede final vira ExtractionError."""
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as client:
        for delay in (*delays, None):
            try:
                r = await client.post(url, json=body, headers=headers)
            except httpx.TransportError as exc:
                if delay is None:
                    raise ExtractionError(f"Falha de rede/timeout ao chamar o LLM: {exc!r}") from exc
                log.warning("Erro de rede no LLM (%r); nova tentativa em %ss", exc, delay)
            else:
                if r.status_code not in RETRY_STATUS or delay is None:
                    return r
                wait = _retry_after_seconds(r)
                if wait is not None and wait > MAX_RETRY_WAIT_S:
                    log.warning("LLM retornou %s pedindo espera de %.0fs; desistindo", r.status_code, wait)
                    return r
                delay = max(delay, wait or 0)
                log.warning("LLM retornou %s; nova tentativa em %ss", r.status_code, delay)
            await asyncio.sleep(delay)
    raise AssertionError("inalcançável")


async def _call_gemini(prompt: str, model_cls: type[T], text: str, pdf: Optional[bytes]) -> T:
    parts: list[dict] = [{"text": prompt}]
    if text:
        parts.append({"text": f"<documento>\n{text}\n</documento>"})
    elif pdf:
        parts.append({"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}})
    generation_config: dict = {
        "temperature": 0,
        "responseMimeType": "application/json",
        "responseJsonSchema": model_cls.model_json_schema(),
    }
    if settings.gemini_thinking_level:
        generation_config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": generation_config}

    models = [settings.gemini_model, *settings.gemini_fallback_models]
    failures: list[str] = []
    for i, model in enumerate(models):
        is_last = i == len(models) - 1
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            # Com fallback disponível, desiste rápido do modelo sobrecarregado
            r = await _post_with_retry(
                url, body, {"x-goog-api-key": settings.gemini_api_key}, RETRY_DELAYS if is_last else (2,)
            )
        except ExtractionError as exc:
            failures.append(f"{model}: {exc}")
            if is_last:
                raise ExtractionError("Nenhum modelo Gemini respondeu. " + " | ".join(failures)) from exc
            log.warning("Gemini %s falhou (%s); usando %s", model, exc, models[i + 1])
            continue
        if r.status_code == 200:
            break
        failures.append(f"{model}: HTTP {r.status_code} {_error_message(r)}")
        if r.status_code in RETRY_STATUS and not is_last:
            log.warning("Gemini %s indisponível (%s); usando %s", model, r.status_code, models[i + 1])
            continue
        raise ExtractionError("Gemini não concluiu a extração. " + " | ".join(failures))

    try:
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as exc:
        raise ExtractionError(f"Resposta inesperada do Gemini ({model}): {r.text[:500]}") from exc
    log.info("Extração %s feita com %s", model_cls.__name__, model)
    return _validate(model_cls, raw)


def _error_message(r: httpx.Response) -> str:
    try:
        return r.json()["error"]["message"].split("\n")[0][:200]
    except (ValueError, KeyError, TypeError):
        return r.text[:200]


async def _call_openai(prompt: str, model_cls: type[T], text: str, pdf: Optional[bytes]) -> T:
    if text:
        user_content: list[dict] = [{"type": "text", "text": f"<documento>\n{text}\n</documento>"}]
    else:
        user_content = [{
            "type": "file",
            "file": {"filename": "documento.pdf",
                     "file_data": "data:application/pdf;base64," + base64.b64encode(pdf).decode()},
        }]
    body = {
        "model": settings.openai_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": model_cls.__name__,
                "strict": True,
                "schema": _strict_schema(model_cls.model_json_schema()),
            },
        },
    }
    r = await _post_with_retry(
        "https://api.openai.com/v1/chat/completions",
        body,
        {"Authorization": f"Bearer {settings.openai_api_key}"},
    )
    if r.status_code != 200:
        raise ExtractionError(f"OpenAI retornou {r.status_code}: {r.text[:500]}")
    msg = r.json()["choices"][0]["message"]
    if msg.get("refusal"):
        raise ExtractionError(f"OpenAI recusou a extração: {msg['refusal']}")
    return _validate(model_cls, msg["content"])


def _validate(model_cls: type[T], raw: str) -> T:
    try:
        return model_cls.model_validate_json(raw)
    except ValidationError as exc:
        raise ExtractionError(f"LLM devolveu JSON fora do schema {model_cls.__name__}: {exc}") from exc


async def _extract(prompt: str, model_cls: type[T], data: bytes, heuristic) -> T:
    text, fmt = await document_to_text(data)
    engine = active_engine()
    if not text:
        if fmt != "pdf":
            raise ExtractionError("Documento Word sem texto (contém apenas imagens?). Envie o PDF digitalizado.")
        if engine == "heuristic":
            raise ExtractionError(
                "PDF sem camada de texto (provavelmente escaneado). Configure GEMINI_API_KEY ou "
                "OPENAI_API_KEY para leitura de documentos digitalizados."
            )
    # O PDF original só vai ao LLM quando não há texto extraível (PDF escaneado)
    pdf = data if fmt == "pdf" else None
    if engine == "gemini":
        return await _call_gemini(prompt, model_cls, text, pdf)
    if engine == "openai":
        return await _call_openai(prompt, model_cls, text, pdf)
    return heuristic(text)


async def extract_registry(data: bytes) -> RegistryExtraction:
    return await _extract(REGISTRY_PROMPT, RegistryExtraction, data, heuristic_registry)


async def extract_memorial(data: bytes) -> MemorialExtraction:
    return await _extract(MEMORIAL_PROMPT, MemorialExtraction, data, heuristic_memorial)


async def extract_title(data: bytes) -> TitleExtraction:
    return await _extract(TITLE_PROMPT, TitleExtraction, data, heuristic_title)


# ---------------------------------------------------------------------------
# Extrator heurístico (layout padronizado)
# ---------------------------------------------------------------------------


def parse_br_number(s: str) -> float:
    s = s.strip().rstrip(".")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    return float(s)


_NUM = r"\d[\d.]*(?:,\d+)?"
_ACT_SPLIT = re.compile(r"(?m)^\s*((?:R|AV)[-.\s]?\d+)\s*[-–—:/]?", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")

_ACT_KEYWORDS: list[tuple[str, str, bool, bool]] = [
    # (regex, tipo, transmite_propriedade, é_ônus)
    (r"CANCELAMENTO|CANCELAD[OA]", "CANCELAMENTO", False, False),
    (r"INDISPONIBILIDADE", "INDISPONIBILIDADE", False, True),
    (r"PENHORA", "PENHORA", False, True),
    (r"ARRESTO", "ARRESTO", False, True),
    (r"HIPOTECA", "HIPOTECA", False, True),
    (r"ALIENA[ÇC][ÃA]O FIDUCI[ÁA]RIA", "ALIENACAO_FIDUCIARIA", False, True),
    (r"USUFRUTO", "USUFRUTO", False, True),
    (r"PARTILHA|INVENT[ÁA]RIO|ARROLAMENTO", "PARTILHA", True, False),
    (r"DOA[ÇC][ÃA]O", "DOACAO", True, False),
    (r"ARREMATA[ÇC][ÃA]O", "ARREMATACAO", True, False),
    (r"ADJUDICA[ÇC][ÃA]O", "ADJUDICACAO", True, False),
    (r"USUCAPI[ÃA]O", "USUCAPIAO", True, False),
    (r"PERMUTA", "PERMUTA", True, False),
    (r"COMPRA E VENDA|VENDA", "COMPRA_E_VENDA", True, False),
    (r"CONSTRU[ÇC][ÃA]O", "AVERBACAO_CONSTRUCAO", False, False),
    (r"CASAMENTO|DIV[ÓO]RCIO", "ESTADO_CIVIL", False, False),
]

_PARTY_PATTERNS = {
    "grantors": r"(?:TRANSMITENTE|VENDEDOR|DOADOR|DEVEDOR|EXECUTADO|AUTOR DA HERAN[ÇC]A|DE CUJUS|OUTORGANTE)\w*\s*:\s*(.+)",
    "grantees": r"(?:ADQUIRENTE|COMPRADOR|DONAT[ÁA]RIO|HERDEIRO|CREDOR|EXEQUENTE|ARREMATANTE|USUFRUTU[ÁA]RIO|OUTORGADO)\w*\s*:\s*(.+)",
}


def _split_names(raw: str) -> list[str]:
    raw = re.split(r"\s*[,;(]\s*(?:brasileir|CPF|RG|casad|solteir|portador|residente|inscrit)", raw, maxsplit=1, flags=re.IGNORECASE)[0]
    names = re.split(r"\s*;\s*|\s+e\s+|\s+E\s+", raw)
    return [n.strip(" .,") for n in names if len(n.strip(" .,")) > 2]


def heuristic_registry(text: str) -> RegistryExtraction:
    m = re.search(r"MATR[ÍI]CULA\s*(?:N[º°o.]*)?\s*:?\s*(\d[\d.]*\d)", text, re.IGNORECASE)
    if not m:
        raise ExtractionError("Número da matrícula não encontrado no documento.")
    office = re.search(r"^.*Registro de Im[óo]veis.*$", text, re.IGNORECASE | re.MULTILINE)
    area = re.search(r"[áa]rea\s+(?:total\s+|superficial\s+)?de\s+(" + _NUM + r")\s*m", text, re.IGNORECASE)

    acts: list[RegistryAct] = []
    pieces = _ACT_SPLIT.split(text)
    for code, body in zip(pieces[1::2], pieces[2::2]):
        upper = body.upper()
        act_type, transfer, enc = "OUTRO", False, False
        for pattern, t, tr, en in _ACT_KEYWORDS:
            if re.search(pattern, upper):
                act_type, transfer, enc = t, tr, en
                break
        parties = {}
        for key, pat in _PARTY_PATTERNS.items():
            found = re.findall(pat, body, re.IGNORECASE)
            parties[key] = [n for f in found for n in _split_names(f)]
        cancels = None
        if act_type == "CANCELAMENTO":
            ref = re.search(r"cancela\w*.*?\b((?:R|AV)[-.\s]?\d+)", body, re.IGNORECASE | re.DOTALL)
            cancels = ref.group(1) if ref else None
        court = re.search(r"(\d+[ªa]\s+Vara[^,.\n]*|Tribunal[^,.\n]*|Banco[^,\n]*)", body, re.IGNORECASE)
        date = _DATE.search(body)
        acts.append(
            RegistryAct(
                act_code=re.sub(r"[.\s]", "-", code.upper()),
                act_date=date.group(1) if date else None,
                act_type=act_type,
                is_ownership_transfer=transfer,
                is_encumbrance=enc,
                grantors=parties["grantors"],
                grantees=parties["grantees"],
                cancels_act_code=cancels,
                court_or_creditor=court.group(1).strip(" .") if court else None,
                summary=" ".join(body.split())[:200],
            )
        )
    # Perímetro georreferenciado descrito na própria matrícula (antes do primeiro ato)
    description = pieces[0] if pieces else text
    perimeter = heuristic_memorial(description)
    return RegistryExtraction(
        registry_number=m.group(1),
        registry_office=office.group(0).strip() if office else None,
        declared_area_m2=parse_br_number(area.group(1)) if area else None,
        property_address=heuristic_address(description, office.group(0) if office else ""),
        utm_zone=perimeter.utm_zone,
        datum=perimeter.datum,
        vertices=perimeter.vertices,
        acts=acts,
    )


_STREET_TYPES = r"Rua|Avenida|Av\.|Alameda|Travessa|Estrada|Rodovia|Praça|Viela"


def heuristic_address(description: str, office_line: str) -> PropertyAddress:
    def grab(pattern: str, source: str = description) -> Optional[str]:
        mm = re.search(pattern, source, re.IGNORECASE)
        return " ".join(mm.group(1).split()).strip(' ,."') if mm else None

    street = grab(r"((?:" + _STREET_TYPES + r")\s+[^,\n;]+)")
    number = grab(r"(?:" + _STREET_TYPES + r")\s+[^,\n;]+,\s*n[º°o.]*\s*(\d+)")
    city, state = None, None
    for source in (description, office_line):  # município do imóvel; senão o da comarca
        mm = re.search(r"([A-ZÀ-Úa-zà-ú' ]+?)\s*/\s*([A-Z]{2})\b", source)
        if mm:
            # "1º OFICIAL DE REGISTRO DE IMÓVEIS DE CAMPINAS/SP" -> "CAMPINAS"
            city = re.sub(
                r"^.*\b(?:(?:IM[ÓO]VEIS|COMARCA|MUNIC[ÍI]PIO)\s+D[AEO]S?|EM|NO|NA)\s+", "", mm.group(1), flags=re.IGNORECASE
            )
            city, state = city.strip().title(), mm.group(2)
            break
    return PropertyAddress(
        street=street,
        number=number,
        lot=grab(r"\blote\s+(?:n[º°o.]*\s*)?(\w+)"),
        block=grab(r"\bquadra\s+(?:n[º°o.]*\s*)?(\w+)"),
        subdivision=grab(r'loteamento\s+"?([^",\n]+)'),
        neighborhood=grab(r"\bbairro\s+(?:d[aoe]s?\s+)?([^,\n;]+)"),
        city=city,
        state=state,
    )


_VERTEX_LINE = re.compile(r"(?m)^\s*(?:v[ée]rtice\s+)?([PVM][-\s]?\d+[A-Z]?)\b(.*)$", re.IGNORECASE)


def _join_wrapped_vertex_lines(text: str) -> str:
    """O PDF quebra linhas longas; reanexa continuações à linha do vértice anterior."""
    out: list[str] = []
    in_vertex = False
    for line in text.splitlines():
        if _VERTEX_LINE.match(line):
            out.append(line)
            in_vertex = True
        elif (
            in_vertex
            and line.strip()
            and not re.match(r"\s*([ÁA]rea|Per[íi]metro)", line, re.IGNORECASE)
            and not re.match(r"\s*[A-ZÀ-Ú][A-ZÀ-Ú ]{3,}:", line)  # novo campo: "PROPRIETÁRIA:", "REGISTRO ANTERIOR:"
            and not _ACT_SPLIT.match(line)
        ):
            out[-1] += " " + line.strip()
        else:
            out.append(line)
            in_vertex = False
    return "\n".join(out)


_TABLE_COLUMNS = [  # (campo, regex do cabeçalho)
    ("point_name", r"v[ée]rtice|ponto"),
    ("utm_e", r"\bE\b|este|leste|coord\w*\.?\s*e\b"),
    ("utm_n", r"\bN\b|norte|coord\w*\.?\s*n\b"),
    ("azimuth", r"azimute|rumo"),
    ("distance_meters", r"dist"),
    ("confrontant", r"confront"),
]


def _heuristic_vertex_table(text: str) -> list[TopoVertex]:
    """Tabela de vértices vinda de DOCX (linhas 'V-01 | 288.627,507 | ...'), mapeada pelo cabeçalho."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if "|" not in line:
            continue
        headers = [h.strip() for h in line.split("|")]
        mapping: dict[int, str] = {}
        for col, header in enumerate(headers):
            for field, pattern in _TABLE_COLUMNS:
                if field not in mapping.values() and re.search(pattern, header, re.IGNORECASE):
                    mapping[col] = field
                    break
        if "point_name" not in mapping.values() or len(mapping) < 3:
            continue
        vertices: list[TopoVertex] = []
        for row in lines[idx + 1:]:
            cells = [c.strip() for c in row.split("|")]
            if "|" not in row or not re.match(r"[PVM][-\s]?\d+", cells[0], re.IGNORECASE):
                break
            data: dict = {}
            for col, field in mapping.items():
                if col >= len(cells) or not cells[col]:
                    continue
                value = cells[col]
                if field in ("utm_e", "utm_n", "distance_meters"):
                    data[field] = parse_br_number(re.sub(r"[^\d.,]", "", value))
                elif field == "point_name":
                    data[field] = value.upper().replace(" ", "-")
                else:
                    data[field] = value
            vertices.append(TopoVertex(**data))
        if len(vertices) >= 3:
            return vertices
    return []


def heuristic_memorial(text: str) -> MemorialExtraction:
    vertices: list[TopoVertex] = _heuristic_vertex_table(text)
    for name, rest in ([] if vertices else _VERTEX_LINE.findall(_join_wrapped_vertex_lines(text))):
        def num(pattern: str) -> Optional[float]:
            mm = re.search(pattern, rest, re.IGNORECASE)
            return parse_br_number(mm.group(1)) if mm else None

        az = re.search(r"(?:Az(?:imute)?|Rumo)\.?\s*[=:]?\s*([NS]?\s*\d+°\s*\d+['′]\s*(?:[\d,.]+\s*[\"″])?\s*[EWLO]?)", rest, re.IGNORECASE)
        conf = re.search(r"confronta(?:nte|ndo)?(?:\s+com)?\s*:?\s*(.+?)\s*$", rest, re.IGNORECASE)
        direction = re.search(r"\b(Norte|Sul|Leste|Oeste|Frente|Fundos)\b", rest, re.IGNORECASE)
        vertices.append(
            TopoVertex(
                point_name=name.upper().replace(" ", "-"),
                utm_e=num(r"\bE\s*[=:]\s*(" + _NUM + ")"),
                utm_n=num(r"\bN\s*[=:]\s*(" + _NUM + ")"),
                azimuth=az.group(1).strip() if az else None,
                distance_meters=num(r"(?:dist[âa]ncia(?:\s+de)?|\bD)\s*[=:]?\s*(" + _NUM + r")\s*m"),
                confrontant=conf.group(1).strip(" .;") if conf else None,
                direction=direction.group(1).capitalize() if direction else None,
            )
        )
    area = re.search(r"[áa]rea\s+(?:total\s+|superficial\s+)?(?:de\s+)?[:=]?\s*(" + _NUM + r")\s*m", text, re.IGNORECASE)
    perim = re.search(r"per[íi]metro\s+(?:de\s+)?[:=]?\s*(" + _NUM + r")\s*m", text, re.IGNORECASE)
    zone = re.search(r"(?:fuso|zona)\s*(?:UTM\s*)?[:=]?\s*(\d{2})", text, re.IGNORECASE)
    datum = re.search(r"(SIRGAS\s*2000|SAD[-\s]?69|WGS[-\s]?84)", text, re.IGNORECASE)
    return MemorialExtraction(
        declared_area_m2=parse_br_number(area.group(1)) if area else None,
        declared_perimeter_m=parse_br_number(perim.group(1)) if perim else None,
        utm_zone=int(zone.group(1)) if zone else None,
        datum=datum.group(1).upper() if datum else None,
        vertices=vertices,
    )


def heuristic_title(text: str) -> TitleExtraction:
    def grab(pattern: str) -> list[str]:
        return [n for f in re.findall(pattern, text, re.IGNORECASE) for n in _split_names(f)]

    return TitleExtraction(
        sellers=grab(r"(?:VENDEDOR|OUTORGANTE|TRANSMITENTE|CEDENTE)\w*(?:\s+VENDEDOR\w*)?\s*:\s*(.+)"),
        buyers=grab(r"(?:COMPRADOR|OUTORGADO|ADQUIRENTE|CESSION[ÁA]RIO)\w*(?:\s+COMPRADOR\w*)?\s*:\s*(.+)"),
    )
