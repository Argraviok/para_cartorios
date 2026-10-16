"""Conversão de documentos Word (.docx/.doc) para PDF via LibreOffice headless.

O tarjamento sempre opera sobre o PDF gerado: o documento Word pode carregar
dados fora da página visível (revisões, comentários, campos ocultos), e o PDF
convertido contém exatamente o que o revisor vê.
"""

import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Literal

from app.core.config import Settings

SourceFormat = Literal["pdf", "docx", "doc"]

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class ConversionError(Exception):
    pass


def detect_format(data: bytes) -> SourceFormat | None:
    """Identifica o formato pelo conteúdo, não pela extensão informada pelo cliente."""
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(_OLE_MAGIC):
        return "doc"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
    return None


def convert_to_pdf(data: bytes, source_format: SourceFormat, settings: Settings) -> bytes:
    if source_format == "pdf":
        return data
    with tempfile.TemporaryDirectory(prefix="lgpd_conv_") as tmp:
        tmp_dir = Path(tmp)
        src = tmp_dir / f"documento.{source_format}"
        src.write_bytes(data)
        # Perfil de usuário isolado por conversão: permite conversões simultâneas
        # e não herda configurações (ex.: macros) do perfil do servidor.
        profile = (tmp_dir / "profile").as_uri()
        cmd = [
            settings.soffice_path,
            f"-env:UserInstallation={profile}",
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(tmp_dir),
            str(src),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=settings.conversion_timeout_seconds, check=True)
        except FileNotFoundError as exc:
            raise ConversionError("LibreOffice não encontrado no servidor (configure SOFFICE_PATH)") from exc
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("Tempo esgotado na conversão do documento Word") from exc
        except subprocess.CalledProcessError as exc:
            raise ConversionError("Falha ao converter o documento Word para PDF") from exc
        out = tmp_dir / "documento.pdf"
        if not out.exists() or out.stat().st_size == 0:
            raise ConversionError("Documento Word ilegível ou corrompido")
        return out.read_bytes()
