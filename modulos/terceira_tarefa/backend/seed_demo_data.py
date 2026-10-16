"""Popula `historical_records` com assentos de demonstração (sem chamar o VLM).

Gera imagens sintéticas de folhas manuscritas em papel amarelado para que o
visualizador e o fluxo de revisão possam ser testados sem acervo real.

Uso:  python seed_demo_data.py [--reset]
"""
import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from app.core import database
from app.core.config import get_settings
from app.schemas.transcription_schema import HistoricalTranscriptionResult, PartyEntity
from app.services import record_service
from app.services.image_service import preprocess_historical_image

DEMO = [
    {
        "book_type": "transcricao_imobiliaria", "book_number": "3-K", "page_number": 142,
        "entry_number": "18.490", "entry_date_text": "Aos dezoito dias do mez de maio de mil novecentos e quarenta e dois",
        "entry_date_iso": "1942-05-18", "confidence": 0.91,
        "text": (
            "Aos dezoito dias do mez de maio de mil novecentos e quarenta e dois, nesta cidade de Sao Paulo, "
            "transcrevo a escriptura de compra e venda lavrada nas notas do 4.o Tabelliao, pela qual "
            "Antonio Rodrigues d'Oliveira transmitte a Joaquim Ferreira Pinto um terreno sito a Rua do Lavradio, "
            "confrontando ao norte com herdeiros de Bento Jose, ao sul com Camillo Castello Branco, "
            "pelo preco de dez contos de reis. Testemunhas: Manoel da Silva e Jose Joaquim de Souza."
        ),
        "parties": [
            ("transmitente", "ANTONIO RODRIGUES DE OLIVEIRA", "Antonio Rodrigues d'Oliveira"),
            ("adquirente", "JOAQUIM FERREIRA PINTO", "Joaquim Ferreira Pinto"),
            ("testemunha", "MANOEL DA SILVA", "Manoel da Silva"),
            ("testemunha", "JOSE JOAQUIM DE SOUZA", "José Joaquim de Souza"),
        ],
        "relatives": ["Herdeiros de Bento José", "Camilo Castelo Branco"],
    },
    {
        "book_type": "nascimento", "book_number": "A-12", "page_number": 37,
        "entry_number": "1.204", "entry_date_text": "Aos tres dias do mez de março de mil oitocentos e noventa e oito",
        "entry_date_iso": "1898-03-03", "confidence": 0.74,
        "text": (
            "Aos tres dias do mez de Marco de mil oitocentos e noventa e oito, neste cartorio da freguezia de "
            "Santa Iphigenia, compareceu M.el Gonçalves Pinheiro e declarou que no dia vinte e oito de Fevereiro "
            "nasceu Thereza, filha legitima delle declarante e de sua mulher Maria Ignacia de Jesus. "
            "Avos paternos Christovao Goncalves e [ilegivel]; avos maternos Luiz Ferreyra e Anna Roza."
        ),
        "parties": [
            ("registrado", "THEREZA GONCALVES PINHEIRO", "Thereza"),
            ("pai", "MANOEL GONCALVES PINHEIRO", "M.el Gonçalves Pinheiro"),
            ("mae", "MARIA IGNACIA DE JESUS", "Maria Ignacia de Jesus"),
            ("declarante", "MANOEL GONCALVES PINHEIRO", "M.el Gonçalves Pinheiro"),
        ],
        "relatives": ["Christovão Gonçalves", "[ilegível]", "Luiz Ferreyra", "Anna Roza"],
    },
    {
        "book_type": "casamento", "book_number": "B-7", "page_number": 88,
        "entry_number": "512", "entry_date_text": "Aos vinte e cinco dias do mez de novembro de mil novecentos e quinze",
        "entry_date_iso": "1915-11-25", "confidence": 0.86,
        "text": (
            "Aos vinte e cinco dias do mez de Novembro de mil novecentos e quinze, nesta Villa, perante o Juiz de Paz, "
            "receberam-se em matrimonio Phelippe Augusto de Mattos, solteiro, lavrador, filho de Victorino de Mattos "
            "e Rosa Maria, e Ignez da Conceicao, solteira, filha de Jozé da Conceicao e Luiza Ferreira. "
            "Testemunhas: Snr. Bento Rodriguez e Joao Baptista Pinto."
        ),
        "parties": [
            ("nubente", "FELIPE AUGUSTO DE MATOS", "Phelippe Augusto de Mattos"),
            ("nubente", "INES DA CONCEICAO", "Ignez da Conceição"),
            ("testemunha", "BENTO RODRIGUES", "Snr. Bento Rodriguez"),
            ("testemunha", "JOAO BATISTA PINTO", "João Baptista Pinto"),
        ],
        "relatives": ["Victorino de Mattos", "Rosa Maria", "Jozé da Conceição", "Luiza Ferreira"],
    },
    {
        "book_type": "obito", "book_number": "C-4", "page_number": 15,
        "entry_number": "2.077", "entry_date_text": "Aos doze dias do mez de julho de mil novecentos e dezoito",
        "entry_date_iso": "1918-07-12", "confidence": 0.58,
        "text": (
            "Aos doze dias do mez de Julho de mil novecentos e dezoito, compareceu Manuel Antonio de Sousa e declarou "
            "que hontem, as [ilegivel] horas, em sua residencia a Rua da Pharmacia, falleceu de influenza "
            "hespanhola sua mulher Thereza de Jesus de Sousa, com quarenta annos, filha de [ilegivel] e de "
            "Anna Thereza. Attestado do Dr. Ignacio Pereira."
        ),
        "parties": [
            ("falecido", "TEREZA DE JESUS DE SOUSA", "Thereza de Jesus de Sousa"),
            ("declarante", "MANUEL ANTONIO DE SOUSA", "Manuel Antonio de Sousa"),
            ("medico", "INACIO PEREIRA", "Dr. Ignacio Pereira"),
        ],
        "relatives": ["[ilegível]", "Anna Thereza"],
    },
]


def synth_page(text: str, header: str, seed: int) -> bytes:
    rng = random.Random(seed)
    h, w = 2200, 1600
    paper = np.zeros((h, w, 3), np.uint8)
    paper[:] = (165, 205, 225)  # BGR amarelado
    noise = np.random.default_rng(seed).normal(0, 9, (h, w, 1)).astype(np.int16)
    paper = np.clip(paper.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    for _ in range(14):  # manchas de umidade
        c = (rng.randint(0, w), rng.randint(0, h))
        cv2.circle(paper, c, rng.randint(30, 140), (130, 175, 200), -1, lineType=cv2.LINE_AA)
    paper = cv2.GaussianBlur(paper, (31, 31), 0)

    ink = (45, 55, 95)  # sépia de tinta ferrogálica
    font = cv2.FONT_HERSHEY_SCRIPT_SIMPLEX
    cv2.putText(paper, header, (140, 200), font, 1.6, ink, 2, cv2.LINE_AA)
    y, line, max_w = 320, "", w - 280
    for word in text.split():
        trial = f"{line} {word}".strip()
        (tw, _), _ = cv2.getTextSize(trial, font, 1.15, 2)
        if tw > max_w:
            cv2.putText(paper, line, (140, y), font, 1.15, ink, 2, cv2.LINE_AA)
            y, line = y + 72, word
        else:
            line = trial
    cv2.putText(paper, line, (140, y), font, 1.15, ink, 2, cv2.LINE_AA)

    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-2.5, 2.5), 1.0)
    paper = cv2.warpAffine(paper, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return cv2.imencode(".jpg", paper, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


async def main(reset: bool) -> None:
    settings = get_settings()
    await database.init_db()
    coll = database.get_collection()
    if reset:
        await coll.delete_many({"_id": {"$regex": "^rec_demo_"}})
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    for i, d in enumerate(DEMO):
        record_id = f"rec_demo_{d['book_type']}_{d['book_number'].replace('-', '').lower()}_fl{d['page_number']}"
        header = f"Livro {d['book_number']}  -  fl. {d['page_number']}  -  N. {d['entry_number']}"
        processed = preprocess_historical_image(synth_page(d["text"], header, seed=i), settings.vlm_image_max_side)
        (settings.storage_dir / f"{record_id}.jpg").write_bytes(processed.original_jpeg)
        (settings.storage_dir / f"{record_id}_enhanced.jpg").write_bytes(processed.enhanced_jpeg)

        result = HistoricalTranscriptionResult(
            entry_number=d["entry_number"],
            entry_date_text=d["entry_date_text"],
            entry_date_iso=d["entry_date_iso"],
            transcription_raw=d["text"],
            parties=[PartyEntity(role=r, name_standardized=s, name_original=o) for r, s, o in d["parties"]],
            confrontants_or_parents=d["relatives"],
            confidence_score=d["confidence"],
        )
        doc = record_service.build_record(
            record_id=record_id,
            book_type=d["book_type"],
            book_number=d["book_number"],
            page_number=d["page_number"],
            image_url=f"{settings.media_url_prefix}/{record_id}.jpg",
            image_enhanced_url=f"{settings.media_url_prefix}/{record_id}_enhanced.jpg",
            result=result,
            vlm_model="demo-seed",
        )
        doc["created_at"] = datetime.now(timezone.utc) - timedelta(minutes=len(DEMO) - i)
        await coll.replace_one({"_id": record_id}, doc, upsert=True)
        print(f"  ✓ {record_id}  (deskew {processed.skew_angle:+.2f}°)")

    print(f"{len(DEMO)} assentos de demonstração gravados em {settings.mongo_db}.{settings.mongo_collection}.")
    database.close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="remove os assentos de demonstração antes de inserir")
    asyncio.run(main(parser.parse_args().reset))
