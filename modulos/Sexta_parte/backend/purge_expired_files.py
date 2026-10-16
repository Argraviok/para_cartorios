"""Expurgo LGPD: remove arquivos de documentos/assinaturas de auditorias decididas cuja retenção venceu.

O registro da auditoria (laudo, scores e histórico de despachos) é mantido; apenas as imagens são
apagadas. Agende diariamente (cron/systemd timer): python purge_expired_files.py
"""
import asyncio
from datetime import datetime, timezone

from app.core import database, storage


async def main() -> None:
    await database.connect()
    db = database.get_db()
    now = datetime.now(timezone.utc)
    purged = 0
    async for doc in db.fraud_audits.find({"retention_until": {"$lte": now}, "files_purged_at": {"$exists": False}}):
        for kind, key in (doc.get("files") or {}).items():
            if key and kind != "signature_card":  # o cartão de firma pertence ao acervo da serventia
                storage.delete(key)
        await db.fraud_audits.update_one(
            {"_id": doc["_id"]},
            {"$set": {"files": {k: None for k in (doc.get("files") or {})}, "files_purged_at": now}},
        )
        purged += 1
    print(f"{purged} auditoria(s) expurgada(s)")
    await database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
