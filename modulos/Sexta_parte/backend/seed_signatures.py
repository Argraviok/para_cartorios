"""Popula `signature_cards` com cartões de firma sintéticos para demonstração.

Uso: python seed_signatures.py            (insere/atualiza 3 cartões de exemplo)
     python seed_signatures.py --samples  (também grava imagens de teste em ./samples)
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core import database, storage
from app.services.signature_service import crop_signature_png
from tests.fixtures import make_clean, make_signature, make_tampered

CARDS = [
    {"cpf": "529.982.247-25", "full_name": "João da Silva Sauro", "card_number": "44.912", "style": "A", "seed": 1},
    {"cpf": "111.444.777-35", "full_name": "Maria Aparecida Souza", "card_number": "44.913", "style": "B", "seed": 5},
    {"cpf": "390.533.447-05", "full_name": "Carlos Eduardo Lima", "card_number": "44.914", "style": "A", "seed": 9},
]


async def main(write_samples: bool) -> None:
    await database.connect()
    db = database.get_db()
    for c in CARDS:
        existing = await db.signature_cards.find_one({"cpf": c["cpf"]})
        if existing:
            storage.delete(existing["signature_sample_url"])
        key = storage.save(crop_signature_png(make_signature(0, c["style"], seed=c["seed"])), "signature_cards", ".png")
        await db.signature_cards.update_one(
            {"cpf": c["cpf"]},
            {"$set": {"full_name": c["full_name"], "card_number": c["card_number"], "signature_sample_url": key},
             "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        print(f"Cartão {c['card_number']} — {c['full_name']} ({c['cpf']})")
    await database.disconnect()

    if write_samples:
        out = Path("samples")
        out.mkdir(exist_ok=True)
        (out / "rg_autentico.jpg").write_bytes(make_clean(1))
        (out / "rg_adulterado_cpf.jpg").write_bytes(make_tampered(1))
        (out / "assinatura_joao_autentica.png").write_bytes(make_signature(2, "A", seed=1))
        (out / "assinatura_joao_falsa.png").write_bytes(make_signature(1, "B", seed=5))
        print(f"Amostras gravadas em {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main("--samples" in sys.argv))
