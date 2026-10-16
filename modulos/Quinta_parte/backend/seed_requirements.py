"""Grava o catálogo de atos (act_requirements) e as tabelas de emolumentos (fee_schedules) no MongoDB.

Uso:  .venv/bin/python seed_requirements.py          # substitui o catálogo atual
      .venv/bin/python seed_requirements.py --demo   # também cria 3 atendimentos de demonstração
"""

import asyncio
import sys

from app.catalog import ACT_REQUIREMENTS, FEE_SCHEDULES
from app.core.config import settings
from app.core.database import MongoRepository


async def main(demo: bool) -> None:
    if not settings.mongodb_uri:
        sys.exit("Defina MONGODB_URI no backend/.env (sem ela a API semeia o catálogo em memória sozinha).")
    repo = MongoRepository(settings.mongodb_uri)
    await repo.ensure_indexes()
    await repo.replace_catalog(ACT_REQUIREMENTS, FEE_SCHEDULES)
    print(f"{len(ACT_REQUIREMENTS)} atos e {len(FEE_SCHEDULES)} tabelas de emolumentos gravados em "
          f"{settings.mongodb_db}.")
    if demo:
        from app.core.database import set_repository
        from app.demo_data import create_demo_triages

        set_repository(repo)
        for protocol in await create_demo_triages():
            print("Atendimento de demonstração:", protocol)


if __name__ == "__main__":
    asyncio.run(main("--demo" in sys.argv))
