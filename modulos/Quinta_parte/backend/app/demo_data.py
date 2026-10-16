"""Atendimentos de demonstração para o painel (documentos fictícios gerados com Pillow, sem chamar a IA)."""

import io
from datetime import timedelta
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.core.database import get_repository
from app.schemas.triage_schema import ChatMessage, Triage
from app.services.chat_service import _build_checklist, _new_protocol, _save_upload, fee_text, now
from app.services.fee_calculator_service import estimate_for_act


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "DejaVuSerif.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fake_document(title: str, lines: list[str], blur: bool = False) -> bytes:
    img = Image.new("RGB", (1200, 850), (250, 247, 238))
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, 1170, 820], outline=(60, 70, 90), width=4)
    d.text((600, 90), "REPÚBLICA FEDERATIVA DO BRASIL", font=_font(30), fill=(40, 40, 40), anchor="mm")
    d.text((600, 150), title.upper(), font=_font(38), fill=(20, 30, 70), anchor="mm")
    y = 240
    for line in lines:
        d.text((90, y), line, font=_font(28), fill=(30, 30, 30))
        y += 60
    d.text((600, 780), "DOCUMENTO FICTÍCIO — DEMONSTRAÇÃO", font=_font(24), fill=(170, 40, 40), anchor="mm")
    if blur:
        from PIL import ImageFilter

        img = img.filter(ImageFilter.GaussianBlur(9))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


async def _create(name: str, contact: str, channel: str, act_type: str, declared: Optional[float],
                  conversation: list[tuple[str, str]], docs: dict[int, dict], minutes_ago: int,
                  status: str, human_requested: bool = False) -> str:
    repo = get_repository()
    requirement = await repo.get_requirement(act_type)
    start = now() - timedelta(minutes=minutes_ago)
    protocol = _new_protocol()
    fee = await estimate_for_act(requirement, "SP", declared)
    checklist = _build_checklist(requirement)
    for idx, info in docs.items():
        url = _save_upload(protocol, fake_document(info["title"], info["lines"], info.get("blur", False)),
                           "image/jpeg")
        checklist[idx] = checklist[idx].model_copy(update={
            "status": info["status"], "image_url": url, "content_type": "image/jpeg",
            "ai_feedback": info["feedback"], "document_type_identified": info["title"],
            "issue_date": info.get("issue_date"),
            "rejection_reason": info["feedback"] if info["status"] == "REJEITADO" else None,
            "validated_by": "ai" if info["status"] == "VALIDADO" else None,
            "uploaded_at": start + timedelta(minutes=5),
        })
    history = [ChatMessage(sender=s, message=t.replace("{fee}", fee_text(fee)),
                           timestamp=start + timedelta(seconds=40 * i))
               for i, (s, t) in enumerate(conversation)]
    triage = Triage(
        protocol_id=protocol, customer_name=name, customer_contact=contact, channel=channel, state="SP",
        act_type=act_type, act_name=requirement["name"], stage="collect_docs", status=status,
        human_requested=human_requested, declared_value=declared, estimated_total=fee.total_estimate,
        fee_estimate=fee, checklist=checklist, chat_history=history,
        created_at=start, updated_at=history[-1].timestamp,
    )
    await repo.insert_triage(triage.model_dump())
    return protocol


async def create_demo_triages() -> list[str]:
    ok = "Documento legível e dentro do prazo."
    protocols = [
        await _create(
            "Juliana Santos", "+5511988887777", "whatsapp", "inventario_extrajudicial", 450000.0,
            [("bot", "Olá! Sou o assistente virtual do cartório. Para começar, qual é o seu nome?"),
             ("user", "Juliana Santos"),
             ("bot", "Prazer, Juliana! Em que posso ajudar?"),
             ("user", "Quanto custa um inventário de 450 mil?"),
             ("bot", "{fee}"),
             ("user", "📎 Foto enviada: Certidão de Óbito do Autor da Herança"),
             ("bot", "✅ Certidão de Óbito do Autor da Herança: " + ok),
             ("user", "📎 Foto enviada: Certidão de Casamento do Falecido (atualizada 90 dias)"),
             ("bot", "⚠️ Certidão de Casamento do Falecido (atualizada 90 dias): Documento emitido em 2021 — "
                     "o prazo máximo é de 90 dias. Por favor, solicite uma via atualizada.")],
            {0: {"title": "Certidão de Óbito", "status": "VALIDADO", "feedback": ok, "issue_date": "2026-09-30",
                 "lines": ["Nome: JOSÉ SANTOS (fictício)", "Data do óbito: 12/09/2026",
                           "Data de emissão: 30/09/2026"]},
             2: {"title": "Certidão de Casamento", "status": "REJEITADO", "issue_date": "2021",
                 "feedback": "Documento emitido em 2021 — o prazo máximo é de 90 dias.",
                 "lines": ["Cônjuges: JOSÉ SANTOS e MARIA SANTOS", "Emitida em 2021"]}},
            minutes_ago=35, status="in_progress"),
        await _create(
            "Carlos Pereira", "carlos@example.com", "webchat", "habilitacao_casamento", None,
            [("bot", "Olá, Carlos! Em que posso ajudar hoje?"),
             ("user", "Quero me casar, o que preciso?"),
             ("bot", "{fee}"),
             ("bot", "🎉 Todos os documentos foram conferidos!")],
            {0: {"title": "Certidão de Nascimento", "status": "VALIDADO", "feedback": ok, "issue_date": "2026-09-20",
                 "lines": ["Nome: CARLOS PEREIRA (fictício)", "Data de emissão: 20/09/2026"]},
             1: {"title": "Carteira de Identidade", "status": "VALIDADO", "feedback": ok,
                 "lines": ["Nome: CARLOS PEREIRA", "RG: 00.000.000-0"]},
             2: {"title": "Comprovante de Residência", "status": "VALIDADO", "feedback": ok,
                 "issue_date": "2026-10-01", "lines": ["Conta de luz — outubro/2026", "Rua Fictícia, 100"]}},
            minutes_ago=80, status="ready_for_counter"),
        await _create(
            "Marcos Oliveira", "+5511977776666", "whatsapp", "procuracao_imovel", None,
            [("bot", "Olá, Marcos! Em que posso ajudar hoje?"),
             ("user", "Preciso de uma procuração para vender o apartamento da minha mãe"),
             ("bot", "{fee}"),
             ("user", "📎 Foto enviada: RG e CPF do Outorgante"),
             ("bot", "⚠️ RG e CPF do Outorgante: Não consegui ler o documento porque a foto parece borrada."),
             ("user", "minha mãe está internada, ela consegue assinar no hospital? quero falar com um atendente"),
             ("bot", "Tudo bem! Já avisei nossa equipe e um atendente vai continuar esta conversa por aqui.")],
            {0: {"title": "Carteira de Identidade", "status": "REJEITADO", "blur": True,
                 "feedback": "Não consegui ler o documento porque a foto parece borrada.",
                 "lines": ["Nome: HELENA OLIVEIRA (fictício)"]}},
            minutes_ago=12, status="human_takeover", human_requested=True),
    ]
    return protocols


async def ensure_demo_data() -> None:
    if not await get_repository().list_triages(None, 1):
        await create_demo_triages()

