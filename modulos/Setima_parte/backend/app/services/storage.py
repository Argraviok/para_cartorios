"""Armazenamento local dos binários. O original é gravado uma vez e nunca sobrescrito."""

import hashlib
import os
from pathlib import Path

from app.core.config import get_settings


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dir(kind: str) -> Path:
    path = get_settings().storage_dir / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def original_path(job_id: str) -> Path:
    return _dir("originals") / f"{job_id}.pdf"


def sanitized_path(job_id: str) -> Path:
    return _dir("sanitized") / f"{job_id}.pdf"


def save_original(job_id: str, data: bytes) -> None:
    path = original_path(job_id)
    # "x": falha se já existir — garante que o original jamais seja sobrescrito.
    with open(path, "xb") as f:
        f.write(data)
    os.chmod(path, 0o440)


def save_source(job_id: str, data: bytes, ext: str) -> None:
    """Documento Word enviado, preservado tal como recebido."""
    path = _dir("originals") / f"{job_id}.{ext}"
    with open(path, "xb") as f:
        f.write(data)
    os.chmod(path, 0o440)


def save_sanitized(job_id: str, data: bytes) -> None:
    tmp = sanitized_path(job_id).with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(sanitized_path(job_id))


def read_original(job_id: str) -> bytes:
    return original_path(job_id).read_bytes()


def read_sanitized(job_id: str) -> bytes:
    return sanitized_path(job_id).read_bytes()
