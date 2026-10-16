"""Armazenamento de arquivos sensíveis criptografado em repouso (Fernet / AES-128-CBC + HMAC).

Documentos de identificação, assinaturas e mapas forenses nunca ficam em texto claro no disco.
"""
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = get_settings().storage_encryption_key
        if not key:
            raise RuntimeError(
                "STORAGE_ENCRYPTION_KEY não configurada. Gere uma com "
                "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`"
            )
        _fernet = Fernet(key.encode())
    return _fernet


def _root() -> Path:
    root = get_settings().storage_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def save(data: bytes, category: str, suffix: str = ".jpg") -> str:
    """Grava bytes criptografados e devolve a chave relativa (ex.: 'documents/<uuid>.jpg')."""
    if category not in {"documents", "signatures", "heatmaps", "signature_cards"}:
        raise ValueError(f"Categoria inválida: {category}")
    key = f"{category}/{uuid.uuid4().hex}{suffix}"
    path = _root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_get_fernet().encrypt(data))
    return key


def _resolve(key: str) -> Path:
    root = _root().resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise ValueError("Chave de arquivo inválida")
    return path


def load(key: str) -> bytes:
    path = _resolve(key)
    if not path.is_file():
        raise FileNotFoundError(key)
    return _get_fernet().decrypt(path.read_bytes())


def delete(key: str) -> None:
    path = _resolve(key)
    path.unlink(missing_ok=True)


def media_type(key: str) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
        Path(key).suffix.lower(), "application/octet-stream"
    )
