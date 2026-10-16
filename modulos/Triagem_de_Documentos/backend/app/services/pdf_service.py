import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, TypedDict

import pymupdf  # PyMuPDF (antigo `fitz`)


class PageText(TypedDict):
    page: int
    text: str


class InvalidPDFError(Exception):
    pass


class ConversionError(Exception):
    pass


def convert_word_to_pdf(data: bytes, suffix: str, soffice_path: str = "soffice") -> bytes:
    """Converte .doc/.docx em PDF com o LibreOffice, para que o documento tenha páginas fixas."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"documento{suffix}"
        source.write_bytes(data)
        try:
            subprocess.run(
                [
                    soffice_path, "--headless", "--norestore",
                    # Perfil isolado: não disputa o lock com um LibreOffice aberto pelo usuário.
                    f"-env:UserInstallation=file://{tmp}/profile",
                    "--convert-to", "pdf", "--outdir", tmp, str(source),
                ],
                check=True, capture_output=True, timeout=120,
            )
        except FileNotFoundError as exc:
            raise ConversionError("LibreOffice não está instalado no servidor.") from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ConversionError("O LibreOffice não conseguiu converter o documento.") from exc
        output = source.with_suffix(".pdf")
        if not output.exists():
            raise ConversionError("O LibreOffice não conseguiu converter o documento.")
        return output.read_bytes()


def extract_pages(pdf_bytes: bytes) -> List[PageText]:
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            return [
                {"page": page_idx + 1, "text": page.get_text("text")}
                for page_idx, page in enumerate(doc)
            ]
    except Exception as exc:
        raise InvalidPDFError(str(exc)) from exc


def _normalize(text: str) -> str:
    # A extração quebra linhas e hifeniza de forma diferente do texto corrido.
    return re.sub(r"\s+", " ", text.replace("-\n", "")).strip().casefold()


def locate_citation(
    citation: Optional[str], page_number: Optional[int], pages: List[PageText]
) -> Tuple[Optional[int], bool]:
    """Confere a citação contra o texto extraído. Retorna (página, verificada)."""
    needle = _normalize(citation or "")
    if not needle:
        return None, False
    # Começa pela página indicada pelo modelo e depois procura nas demais.
    for page in sorted(pages, key=lambda p: p["page"] != page_number):
        if needle in _normalize(page["text"]):
            return page["page"], True
    return page_number, False
