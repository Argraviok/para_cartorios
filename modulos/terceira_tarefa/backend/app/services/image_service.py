"""Pré-processamento de imagens de livros manuscritos/datilografados antigos."""
from dataclasses import dataclass

import cv2
import numpy as np

MAX_DESKEW_DEGREES = 10.0


class InvalidImageError(ValueError):
    pass


@dataclass
class ProcessedImage:
    original_jpeg: bytes  # cor original, para o visualizador do escrevente
    enhanced_jpeg: bytes  # tons de cinza + deskew + CLAHE, enviado ao VLM
    width: int
    height: int
    skew_angle: float


def decode_image(image_bytes: bytes) -> np.ndarray:
    np_arr = np.frombuffer(image_bytes, np.uint8)
    # IMREAD_COLOR também converte TIFF/PNG de digitalizadores TWAIN para BGR.
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise InvalidImageError("Arquivo não é uma imagem suportada (JPEG, PNG, TIFF, BMP, WEBP).")
    return img


def _projection_score(binary: np.ndarray, angle: float) -> float:
    h, w = binary.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(binary, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    # Com as linhas de texto na horizontal, as somas por linha alternam entre picos
    # (texto) e vales (entrelinhas), maximizando a variância.
    return float(np.var(rotated.sum(axis=1, dtype=np.float64)))


def estimate_skew(gray: np.ndarray) -> float:
    """Ângulo (graus) a aplicar com `rotate` para endireitar as linhas de texto."""
    scale = 1000 / max(gray.shape)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    # Otsu invertido isola a tinta; a binarização é usada só para medir o ângulo.
    small = cv2.GaussianBlur(small, (3, 3), 0)
    _, binary = cv2.threshold(small, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if binary.sum() < 500:
        return 0.0

    # Busca grossa (0.5°) seguida de refinamento (0.1°) em torno do melhor ângulo.
    coarse = np.arange(-MAX_DESKEW_DEGREES, MAX_DESKEW_DEGREES + 0.01, 0.5)
    best = max(coarse, key=lambda a: _projection_score(binary, a))
    fine = np.arange(best - 0.5, best + 0.51, 0.1)
    best = max(fine, key=lambda a: _projection_score(binary, a))
    return round(float(best), 2)


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = (255, 255, 255) if img.ndim == 3 else 255
    return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def limit_size(img: np.ndarray, max_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def preprocess_historical_image(image_bytes: bytes, max_side: int = 2400) -> ProcessedImage:
    img = decode_image(image_bytes)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    angle = estimate_skew(gray)
    if abs(angle) > 0.3:
        img = rotate(img, angle)
        gray = rotate(gray, angle)

    # Remove manchas finas do papel amarelado sem apagar traços de pena.
    denoised = cv2.fastNlMeansDenoising(gray, h=7)
    # CLAHE para equalizar o contraste da tinta ferrogálica desbotada. Não binarizamos a
    # imagem enviada ao VLM: os tons de cinza preservam traços finos que o Otsu apagaria.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = limit_size(clahe.apply(denoised), max_side)

    ok_o, original_jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    ok_e, enhanced_jpg = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not (ok_o and ok_e):
        raise InvalidImageError("Falha ao codificar a imagem processada.")
    return ProcessedImage(
        original_jpeg=original_jpg.tobytes(),
        enhanced_jpeg=enhanced_jpg.tobytes(),
        width=img.shape[1],
        height=img.shape[0],
        skew_angle=angle,
    )
