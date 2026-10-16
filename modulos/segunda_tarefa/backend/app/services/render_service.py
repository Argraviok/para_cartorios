import re
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.config import Settings
from app.schemas.devolution_schema import Requirement

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES),
    autoescape=False,  # saída é Markdown; o frontend sanitiza o HTML renderizado
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)

_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def format_date_long(d: date) -> str:
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


def format_protocol(number: str) -> str:
    return f"{int(number):,}".replace(",", ".") if number.isdigit() else number


def render_note(
    *,
    settings: Settings,
    protocol_number: str,
    protocol_date: date,
    act_type: str,
    presenter_name: str,
    requirements: list[Requirement],
    note_number: str | None = None,
    issue_date: date | None = None,
) -> str:
    text = _env.get_template("nota_devolutiva.md.j2").render(
        serventia={
            "nome": settings.serventia_nome,
            "cns": settings.serventia_cns,
            "endereco": settings.serventia_endereco,
            "cidade_uf": settings.serventia_cidade_uf,
            "oficial": settings.oficial_nome,
        },
        note_number=note_number,
        protocol_number=format_protocol(protocol_number),
        protocol_date=protocol_date.strftime("%d/%m/%Y"),
        act_type=act_type,
        presenter_name=presenter_name,
        requirements=sorted(requirements, key=lambda r: r.order),
        prenotacao_dias=settings.prenotacao_dias,
        issue_date=format_date_long(issue_date or date.today()),
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def markdown_to_plain_text(md: str) -> str:
    text = md.replace("&nbsp;", "")
    text = re.sub(r"\\(.)", r"\1", text)                       # escapes
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)           # títulos
    text = re.sub(r"^>\s?", "", text, flags=re.M)                # citações
    text = re.sub(r"^-{3,}\s*$", "-" * 40, text, flags=re.M)     # regras
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)              # negrito
    text = re.sub(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])", r"\2", text)  # itálico
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
