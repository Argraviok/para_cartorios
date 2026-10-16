"""Geradores de imagens sintéticas para testes (documento, montagem e assinaturas)."""
import io

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def make_document(seed: int = 1) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = 1000, 640
    yy, xx = np.mgrid[0:h, 0:w]
    bg = np.stack([200 + 25 * np.sin(xx / 23.0 + yy / 41.0), 215 + 20 * np.cos(yy / 17.0),
                   190 + 30 * np.sin((xx + yy) / 31.0)], axis=2)
    bg += rng.normal(0, 6, bg.shape)  # ruído de sensor/papel
    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    f = _font(30)
    d.text((40, 40), "REPUBLICA FEDERATIVA DO BRASIL", fill=(20, 30, 60), font=f)
    d.text((40, 120), "NOME: JOAO DA SILVA SAURO", fill=(10, 10, 10), font=f)
    d.text((40, 200), "CPF: 529.982.247-25", fill=(10, 10, 10), font=f)
    d.text((40, 280), "DATA NASC: 01/02/1970", fill=(10, 10, 10), font=f)
    d.rectangle((700, 120, 940, 420), outline=(60, 60, 60), width=3)
    return img


def jpeg(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def make_tampered(seed: int = 1) -> bytes:
    """Documento comprimido em q=70 (câmera) com o CPF reescrito digitalmente e salvo em q=95."""
    base = Image.open(io.BytesIO(jpeg(make_document(seed), 70))).convert("RGB")
    patch = make_document(seed).crop((150, 190, 520, 250))  # fundo sem compressão
    d = ImageDraw.Draw(patch)
    d.rectangle((0, 0, patch.width, patch.height), fill=(212, 222, 200))
    d.text((5, 8), "111.444.777-35", fill=(0, 0, 0), font=_font(32))
    base.paste(patch, (150, 190))
    return jpeg(base, 95)


def make_clean(seed: int = 1) -> bytes:
    base = Image.open(io.BytesIO(jpeg(make_document(seed), 70))).convert("RGB")
    return jpeg(base, 95)


def make_signature(variant: int = 0, style: str = "A", seed: int = 0) -> bytes:
    """Assinatura sintética: style A/B são pessoas diferentes; variant gera variação natural."""
    rng = np.random.default_rng(seed + 100 * variant)
    img = np.full((220, 700), 255, np.uint8)
    t = np.linspace(0, 1, 400)
    if style == "A":
        x = 40 + 600 * t
        y = 120 - 45 * np.sin(t * 18) * np.exp(-t) - 30 * t + 25 * np.sin(t * 5)
        slant = 0.35
    else:
        x = 60 + 560 * t
        y = 110 + 60 * np.sign(np.sin(t * 7)) * np.abs(np.sin(t * 7)) ** 0.3 * (1 - t / 2)
        slant = -0.25
    jitter = rng.normal(0, 1.5, size=t.shape)
    x = x + slant * (120 - y) + rng.normal(0, 4) + jitter
    y = y + rng.normal(0, 4) + jitter
    sx = 1 + rng.normal(0, 0.04)
    pts = np.stack([x * sx, y], axis=1).astype(np.int32)
    if style == "B":
        for seg in np.array_split(pts, 6):  # muitas interrupções de traço
            cv2.polylines(img, [seg], False, 0, 3, cv2.LINE_AA)
    else:
        cv2.polylines(img, [pts], False, 0, int(rng.integers(3, 6)), cv2.LINE_AA)
        cv2.line(img, (60, 170), (560, 175), 0, 3, cv2.LINE_AA)  # sublinhado característico
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()
