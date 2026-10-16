import io
import os
import tempfile

# Testes nunca chamam LLM nem MongoDB reais
# (TEST_MONGODB_URI opcional roda a mesma suíte contra um MongoDB descartável, num banco novo)
os.environ.update(LLM_PROVIDER="heuristic", MONGODB_URI=os.environ.get("TEST_MONGODB_URI", ""),
                  MONGODB_DB=f"triagem_test_{os.getpid()}", DEMO_DATA="false",
                  STORAGE_DIR=tempfile.mkdtemp(prefix="triagem-test-"))

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def make_doc_image(blur: bool = False, size=(1200, 850)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(18):
        d.text((60, 40 + i * 42), "CERTIDAO DE OBITO - TEXTO DE TESTE 0123456789 " * 2, fill="black")
        d.line([(40, 60 + i * 42), (1150, 60 + i * 42)], fill="gray")
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(10))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()
