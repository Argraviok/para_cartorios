"""Engine de diálogo da triagem.

A máquina de estados (ask_name → identify_act → ask_value → collect_docs → done) é determinística.
O LLM só é usado para *entender* a mensagem (intenção, ato, valor declarado) e para responder dúvidas
livres com base no contexto fornecido. Valores de emolumentos e o checklist vêm sempre do banco.
Sem LLM configurado, um interpretador por regras assume.
"""

import logging
import re
import secrets
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_repository
from app.schemas.triage_schema import (
    ChatMessage,
    ChecklistItem,
    DocumentVerificationResult,
    FeeEstimateResult,
    Triage,
    TriageSummary,
)
from app.services.doc_vision_service import (
    STATUS_TO_CHECKLIST,
    ExpectedDocument,
    sniff_content_type,
    verify_document,
)
from app.services.fee_calculator_service import FeeError, brl, estimate_for_act
from app.services.llm_client import LLMError, active_engine, call_structured

log = logging.getLogger(__name__)


class TriageNotFound(LookupError):
    pass


class TriageConflict(ValueError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def _msg(sender: str, text: str, **extra) -> ChatMessage:
    return ChatMessage(sender=sender, message=text, timestamp=now(), **extra)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# Interpretação da mensagem
# ---------------------------------------------------------------------------


class TurnUnderstanding(BaseModel):
    intent: Literal["choose_act", "inform_value", "inform_name", "ask_question",
                    "request_human", "greeting", "other"]
    act_type: Optional[str] = Field(None, description="act_type do catálogo, só se o cidadão escolheu o serviço")
    declared_value: Optional[float] = Field(None, description="Valor em reais informado pelo cidadão")
    customer_name: Optional[str] = Field(None, description="Nome que o cidadão informou, se informou")
    answer: Optional[str] = Field(None, description="Resposta curta em português para dúvidas e saudações")


_HUMAN_RE = re.compile(
    r"\b(atendente|humano|humana|pessoa real|escrevente|tabeliao|falar com (alguem|uma pessoa|o cartorio|voces))\b"
)
_GREETING_RE = re.compile(r"^(oi+|ola|bom dia|boa tarde|boa noite|e ai|opa|hello)\b[!. ]*$")
_NAME_PREFIX_RE = re.compile(r"^(meu nome e|me chamo|sou o|sou a|sou|aqui e o|aqui e a|eu sou)\s+", re.I)
_NOT_NAME_WORDS = {"quero", "queria", "preciso", "gostaria", "fazer", "qual", "quanto", "como", "onde", "um",
                   "uma", "para", "com", "sim", "nao", "ok", "obrigado", "obrigada", "tudo", "bem", "certidao",
                   "documento", "cartorio", "o", "a", "e", "que", "por", "favor"}
_MONEY_HINT_RE = re.compile(r"r\$|\bmil\b|milh|\breais\b|\d\s*k\b")


def parse_brl_amount(text: str, require_hint: bool = False) -> Optional[float]:
    """Extrai um valor em reais: "450 mil", "R$ 450.000,00", "1,2 milhão", "450000", "300k"."""
    t = _norm(text)
    if require_hint and not _MONEY_HINT_RE.search(t):
        return None
    best: Optional[float] = None
    for m in re.finditer(r"(\d+(?:[.,]\d+)*)\s*(milhoes|milhao|mi\b|mil\b|k\b)?", t):
        num, mult = m[1], m[2]
        if "," in num:
            num = num.replace(".", "").replace(",", ".")
        elif "." in num:
            groups = num.split(".")[1:]
            num = num.replace(".", "") if all(len(g) == 3 for g in groups) else num
        try:
            value = float(num)
        except ValueError:
            continue
        if mult in ("milhoes", "milhao", "mi"):
            value *= 1_000_000
        elif mult in ("mil", "k"):
            value *= 1_000
        if best is None or value > best:
            best = value
    return best


def detect_act(text: str, catalog: list[dict]) -> Optional[str]:
    t = _norm(text)
    best, best_score = None, 0
    for act in catalog:
        score = sum(len(k) for k in {_norm(k) for k in act["keywords"]} if k in t)
        if score > best_score:
            best, best_score = act["act_type"], score
    return best


def _looks_like_name(text: str) -> Optional[str]:
    cleaned = _NAME_PREFIX_RE.sub("", _norm(text).strip()).strip(" .!")
    original = text.strip().strip(" .!")
    words = original.split()
    # Mantém a grafia original (com acentos) quando possível
    n = len(cleaned.split())
    if n == 0 or n > 6 or not re.fullmatch(r"[a-z' ]+", cleaned) or set(cleaned.split()) & _NOT_NAME_WORDS:
        return None
    return " ".join(w.capitalize() for w in words[-n:])


def understand_heuristic(text: str, triage: Triage, catalog: list[dict]) -> TurnUnderstanding:
    t = _norm(text).strip()
    if _HUMAN_RE.search(t):
        return TurnUnderstanding(intent="request_human")
    act = detect_act(text, catalog) if triage.stage in ("ask_name", "identify_act") else None
    if triage.stage == "ask_name" and not act:
        if _GREETING_RE.match(t):
            return TurnUnderstanding(intent="greeting")
        if name := _looks_like_name(text):
            return TurnUnderstanding(intent="inform_name", customer_name=name)
    value = parse_brl_amount(text, require_hint=triage.stage != "ask_value")
    if act:
        return TurnUnderstanding(intent="choose_act", act_type=act, declared_value=value)
    if value is not None and (triage.stage == "ask_value" or triage.declared_value is not None):
        return TurnUnderstanding(intent="inform_value", declared_value=value)
    if _GREETING_RE.match(t):
        return TurnUnderstanding(intent="greeting")
    if "?" in text or re.search(r"\b(quanto|qual|quais|como|onde|quando|precis|prazo|horario)\b", t):
        return TurnUnderstanding(intent="ask_question")
    return TurnUnderstanding(intent="other")


UNDERSTAND_PROMPT = """Você é o assistente virtual de triagem do {office}, um cartório brasileiro.
Classifique a última mensagem do cidadão e, quando for dúvida ou saudação, escreva a resposta.

Serviços atendidos (act_type — nome — resumo):
{catalog}

Regras de classificação:
- choose_act: o cidadão quer iniciar ou trocar de serviço. Preencha act_type com um dos act_type acima.
  Mencionar um documento (ex.: "minha certidão de casamento") NÃO é escolher o serviço de casamento.
- inform_value: informou o valor dos bens/negócio. Preencha declared_value em reais (ex.: "450 mil" = 450000).
- inform_name: informou o próprio nome (preencha customer_name).
- request_human: pediu para falar com uma pessoa/atendente/escrevente.
- ask_question: fez uma pergunta. greeting: só cumprimentou. other: qualquer outra coisa.
- Se a mensagem também trouxer valor ou nome, preencha os campos correspondentes mesmo com outra intenção.

Regras para "answer" (só para ask_question, greeting e other):
- Português simples e acolhedor, sem jargão jurídico, no máximo 3 frases curtas.
- Use SOMENTE as informações do contexto. Nunca invente valores, prazos, endereços ou horários; se não souber,
  diga que um atendente pode confirmar.
- Não dê parecer jurídico. Não peça CPF, RG ou outros números de documento por mensagem.
"""


def _catalog_text(catalog: list[dict]) -> str:
    return "\n".join(f"- {a['act_type']} — {a['name']} — {a['summary']}" for a in catalog)


def _context_text(triage: Triage, requirement: Optional[dict]) -> str:
    lines = [f"Etapa atual: {triage.stage}", f"Nome do cidadão: {triage.customer_name or 'não informado'}"]
    if requirement:
        lines.append(f"Serviço escolhido: {requirement['name']} — {requirement['summary']}")
        lines += [f"Observação: {n}" for n in requirement.get("notes", [])]
    if triage.fee_estimate:
        f = triage.fee_estimate
        lines.append(
            f"Estimativa já calculada: total {brl(f.total_estimate)} (emolumentos {brl(f.base_fee)}, "
            f"fundos {brl(f.state_funds)}, ISSQN {brl(f.municipal_tax)}). Aviso obrigatório: {f.legal_disclaimer}"
        )
    if triage.checklist:
        lines.append("Checklist de documentos:")
        lines += [f"  - {c.doc_name}: {c.status}" + (f" ({c.rejection_reason})" if c.rejection_reason else "")
                  for c in triage.checklist]
    history = triage.chat_history[-10:]
    if history:
        lines.append("Últimas mensagens:")
        lines += [f"  [{m.sender}] {m.message[:400]}" for m in history]
    return "\n".join(lines)


async def understand(text: str, triage: Triage, catalog: list[dict],
                     requirement: Optional[dict]) -> TurnUnderstanding:
    fallback = understand_heuristic(text, triage, catalog)
    if active_engine() == "heuristic":
        return fallback
    system = UNDERSTAND_PROMPT.format(office=settings.office_name, catalog=_catalog_text(catalog))
    user = f"{_context_text(triage, requirement)}\n\nÚltima mensagem do cidadão:\n<mensagem>{text}</mensagem>"
    try:
        result, _ = await call_structured(system, user, TurnUnderstanding)
    except LLMError as exc:
        log.warning("LLM indisponível no diálogo, usando regras: %s", exc)
        return fallback
    valid_acts = {a["act_type"] for a in catalog}
    if result.act_type not in valid_acts:
        result.act_type = None
    if result.intent == "choose_act" and not result.act_type:
        result.intent = "other"
    # Pedido de atendente é seguro detectar por regra também
    if fallback.intent == "request_human":
        result.intent = "request_human"
    if result.declared_value is not None and result.declared_value < 0:
        result.declared_value = None
    return result


# ---------------------------------------------------------------------------
# Textos fixos
# ---------------------------------------------------------------------------


def greeting_text(name: Optional[str]) -> str:
    hello = f"Olá, {name.split()[0]}! " if name else "Olá! "
    text = f"{hello}Sou o assistente virtual do {settings.office_name}. "
    if not name:
        return text + "Para começar, qual é o seu nome?"
    return text + "Em que posso ajudar hoje?"


def services_text(catalog: list[dict]) -> str:
    items = "\n".join(f"• {a['name']}" for a in catalog)
    return f"Posso ajudar com estes serviços:\n{items}\n\nÉ só me dizer qual você precisa."


def fee_text(fee: FeeEstimateResult) -> str:
    head = f"Estimativa para {fee.service_name}"
    if fee.declared_value is not None:
        head += f" com valor declarado de {brl(fee.declared_value)}"
    pct = round(fee.municipal_tax / fee.base_fee * 100, 1) if fee.base_fee else 0
    return (
        f"{head}:\n"
        f"• Emolumentos do tabelião: {brl(fee.base_fee)}\n"
        f"• Fundos estaduais: {brl(fee.state_funds)}\n"
        f"• ISSQN ({pct:g}%): {brl(fee.municipal_tax)}\n"
        f"Total estimado: {brl(fee.total_estimate)}\n\n"
        f"⚠️ {fee.legal_disclaimer}"
    )


def checklist_text(requirement: dict) -> str:
    docs = "\n".join(f"{i}. {d['doc_name']}" for i, d in enumerate(requirement["documents"], 1))
    notes = "".join(f"\nℹ️ {n}" for n in requirement.get("notes", []))
    return (
        f"Para {requirement['name']}, vou precisar de fotos destes documentos:\n{docs}\n\n"
        "Envie uma foto por vez pelo botão de anexo (📎), com boa iluminação e mostrando o documento inteiro. "
        f"Eu confiro cada uma na hora.{notes}"
    )


def _heuristic_answer(text: str, triage: Triage) -> str:
    """Respostas fixas para dúvidas comuns quando não há LLM configurado."""
    t = _norm(text)
    if triage.fee_estimate and re.search(r"quanto|valor|custa|preco|pagar|taxa", t):
        return fee_text(triage.fee_estimate)
    if triage.checklist and re.search(r"document|falta|pendente|enviar|foto", t):
        lines = "\n".join(f"• {c.doc_name}: {c.status.lower()}" for c in triage.checklist)
        return f"Situação dos seus documentos:\n{lines}"
    return ("Essa dúvida é melhor confirmar com nossa equipe. Se quiser falar com um atendente, "
            "é só escrever \"atendente\".")


def _next_pending(checklist: list[ChecklistItem]) -> Optional[int]:
    for i, item in enumerate(checklist):
        if item.required and item.status in ("PENDENTE", "REJEITADO"):
            return i
    return None


def checklist_complete(checklist: list[ChecklistItem]) -> bool:
    return bool(checklist) and all(c.status == "VALIDADO" for c in checklist if c.required)


# ---------------------------------------------------------------------------
# Sessões
# ---------------------------------------------------------------------------


def _new_protocol() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return f"TRI-{date.today():%Y%m%d}-" + "".join(secrets.choice(alphabet) for _ in range(6))


async def load_triage(protocol_id: str) -> Triage:
    raw = await get_repository().get_triage(protocol_id)
    if raw is None:
        raise TriageNotFound(protocol_id)
    return Triage.model_validate(raw)


async def start_session(contact: str, name: Optional[str], channel: str) -> Triage:
    name = (name or "").strip() or None
    ts = now()
    triage = Triage(
        protocol_id=_new_protocol(),
        customer_name=name,
        customer_contact=contact.strip(),
        channel=channel,
        state=settings.office_state,
        stage="identify_act" if name else "ask_name",
        created_at=ts,
        updated_at=ts,
    )
    catalog = await get_repository().list_requirements()
    triage.chat_history.append(_msg("bot", greeting_text(name)))
    if name:
        triage.chat_history.append(_msg("bot", services_text(catalog)))
    await get_repository().insert_triage(triage.model_dump())
    return triage


async def _requirement(triage: Triage) -> Optional[dict]:
    return await get_repository().get_requirement(triage.act_type) if triage.act_type else None


def _build_checklist(requirement: dict) -> list[ChecklistItem]:
    return [ChecklistItem(doc_name=d["doc_name"], description=d.get("description", ""),
                          required=d.get("required", True), max_age_days=d.get("max_age_days"))
            for d in requirement["documents"]]


async def _enter_collect_docs(triage: Triage, requirement: dict, replies: list[str]) -> None:
    try:
        fee = await estimate_for_act(requirement, triage.state, triage.declared_value)
        triage.fee_estimate = fee
        triage.estimated_total = fee.total_estimate
        replies.append(fee_text(fee))
    except FeeError as exc:
        log.error("Falha no cálculo de emolumentos: %s", exc)
        replies.append("Não consegui calcular a estimativa de custos agora; um atendente vai informar o valor.")
    if not triage.checklist:
        triage.checklist = _build_checklist(requirement)
        replies.append(checklist_text(requirement))
    triage.stage = "collect_docs"


async def _apply(triage: Triage, u: TurnUnderstanding, catalog: list[dict], text: str) -> list[str]:
    """Aplica a intenção à máquina de estados e devolve os textos de resposta do bot."""
    replies: list[str] = []

    if u.intent == "request_human":
        triage.status = "human_takeover"
        triage.human_requested = True
        return ["Tudo bem! Já avisei nossa equipe e um atendente vai continuar esta conversa por aqui em instantes. "
                "Enquanto isso, se quiser, pode ir enviando as fotos dos documentos."]

    if u.customer_name and not triage.customer_name:
        triage.customer_name = u.customer_name.strip()[:120]

    if triage.stage == "ask_name":
        if triage.customer_name:
            triage.stage = "identify_act"
            if u.intent != "choose_act":
                return [f"Prazer, {triage.customer_name.split()[0]}! " + services_text(catalog)]
        elif u.intent != "choose_act":
            prefix = (u.answer + "\n\n") if u.answer and u.intent == "ask_question" else ""
            return [prefix + "Antes de continuar, como posso te chamar?"]
        else:
            triage.stage = "identify_act"

    switching = u.intent == "choose_act" and u.act_type and u.act_type != triage.act_type
    if switching and (triage.stage in ("identify_act", "ask_value") or active_engine() != "heuristic"):
        requirement = next(a for a in catalog if a["act_type"] == u.act_type)
        had_act = triage.act_type is not None
        triage.act_type, triage.act_name = requirement["act_type"], requirement["name"]
        triage.checklist, triage.fee_estimate, triage.estimated_total = [], None, None
        if not requirement["requires_declared_value"]:
            triage.declared_value = None
        elif u.declared_value is not None:
            triage.declared_value = u.declared_value
        elif had_act:
            triage.declared_value = None
        intro = ("Certo, vamos mudar para " if had_act else "Perfeito! ") + f"{requirement['name']}: {requirement['summary']}"
        replies.append(intro)
        if requirement["requires_declared_value"] and triage.declared_value is None:
            triage.stage = "ask_value"
            replies.append(requirement["value_question"])
        else:
            await _enter_collect_docs(triage, requirement, replies)
        return replies

    requirement = await _requirement(triage)

    if triage.stage == "identify_act":
        if u.answer and u.intent in ("ask_question", "greeting", "other"):
            replies.append(u.answer)
        replies.append(services_text(catalog) if not u.answer or u.intent != "ask_question"
                       else "Qual desses serviços você precisa? " + ", ".join(a["name"] for a in catalog) + ".")
        return replies

    if u.declared_value is not None and requirement and requirement["requires_declared_value"] \
            and u.intent in ("inform_value", "choose_act", "ask_question", "other"):
        changed = triage.declared_value is not None and triage.declared_value != u.declared_value
        triage.declared_value = u.declared_value
        if triage.stage == "ask_value":
            replies.append(f"Anotado: {brl(u.declared_value)}.")
            await _enter_collect_docs(triage, requirement, replies)
            return replies
        if changed:
            replies.append(f"Atualizei o valor declarado para {brl(u.declared_value)}.")
            await _enter_collect_docs(triage, requirement, replies)
            return replies

    if triage.stage == "ask_value":
        if u.answer:
            replies.append(u.answer)
        replies.append(requirement["value_question"] if requirement else "Qual é o valor aproximado?")
        return replies

    # collect_docs / done: dúvidas livres
    if u.answer:
        replies.append(u.answer)
    elif u.intent == "ask_question":
        replies.append(_heuristic_answer(text, triage))
    if triage.stage == "collect_docs":
        idx = _next_pending(triage.checklist)
        if idx is not None:
            replies.append(f"Quando puder, envie a foto de: {triage.checklist[idx].doc_name}.")
        elif not replies:
            replies.append("Seus documentos já foram recebidos. Se precisar de algo mais, é só falar.")
    if not replies:
        replies.append("Se precisar de algo mais, é só me dizer.")
    return replies


async def handle_user_message(protocol_id: Optional[str], text: str, contact: Optional[str],
                              name: Optional[str], channel: str) -> tuple[Triage, list[ChatMessage]]:
    repo = get_repository()
    if protocol_id:
        triage = await load_triage(protocol_id)
    else:
        if not contact:
            raise TriageConflict("Informe protocol_id ou customer_contact.")
        raw = await repo.find_open_triage_by_contact(contact.strip())
        triage = Triage.model_validate(raw) if raw else await start_session(contact, name, channel)

    user_msg = _msg("user", text.strip())
    if triage.status == "human_takeover":
        # Bot fica em silêncio enquanto o atendimento é humano
        await repo.push_messages(triage.protocol_id, [user_msg.model_dump()], {"updated_at": user_msg.timestamp})
        triage.chat_history.append(user_msg)
        return triage, []

    catalog = await repo.list_requirements()
    requirement = await _requirement(triage)
    u = await understand(text, triage, catalog, requirement)
    texts = await _apply(triage, u, catalog, text)

    # O escrevente pode ter assumido durante a chamada ao LLM: não sobrescreve
    fresh = await load_triage(triage.protocol_id)
    if fresh.status == "human_takeover" and u.intent != "request_human":
        await repo.push_messages(triage.protocol_id, [user_msg.model_dump()], {"updated_at": user_msg.timestamp})
        fresh.chat_history.append(user_msg)
        return fresh, []

    if triage.status != "human_takeover":
        triage.status = "ready_for_counter" if checklist_complete(triage.checklist) else "in_progress"
    replies = [_msg("bot", t) for t in texts]
    triage.updated_at = replies[-1].timestamp if replies else user_msg.timestamp
    fields = triage.model_dump(include={
        "customer_name", "act_type", "act_name", "stage", "status", "human_requested", "declared_value",
        "estimated_total", "fee_estimate", "checklist", "updated_at",
    })
    await repo.push_messages(triage.protocol_id, [user_msg.model_dump()] + [r.model_dump() for r in replies], fields)
    triage.chat_history += [user_msg, *replies]
    return triage, replies


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


def _save_upload(protocol_id: str, data: bytes, mime: str) -> str:
    folder = Path(settings.storage_dir) / "uploads" / protocol_id
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{now():%Y%m%d%H%M%S}-{secrets.token_hex(4)}.{_EXT[mime]}"
    (folder / name).write_bytes(data)
    return f"/media/uploads/{protocol_id}/{name}"


async def handle_upload(protocol_id: str, data: bytes, doc_index: Optional[int]) -> tuple[
        Triage, DocumentVerificationResult, int, list[ChatMessage]]:
    repo = get_repository()
    triage = await load_triage(protocol_id)
    if not triage.checklist:
        raise TriageConflict("Escolha primeiro o serviço desejado para que o checklist de documentos seja criado.")
    if doc_index is None:
        doc_index = _next_pending(triage.checklist)
        if doc_index is None:
            raise TriageConflict("Todos os documentos já foram enviados. Informe qual documento deseja substituir.")
    if not 0 <= doc_index < len(triage.checklist):
        raise TriageConflict("Documento do checklist inválido.")

    requirement = await _requirement(triage) or {"documents": []}
    spec = next((d for d in requirement["documents"] if d["doc_name"] == triage.checklist[doc_index].doc_name), {})
    item = triage.checklist[doc_index]
    expected = ExpectedDocument(item.doc_name, item.description, tuple(spec.get("accepted_types", [])),
                                item.max_age_days)
    result = await verify_document(data, expected)

    mime = sniff_content_type(data) or "application/octet-stream"
    url = _save_upload(protocol_id, data, mime)
    status = STATUS_TO_CHECKLIST[result.validation_status]
    item = item.model_copy(update={
        "status": status,
        "image_url": url,
        "content_type": mime,
        "rejection_reason": None if status != "REJEITADO" else result.feedback_to_user,
        "ai_feedback": result.feedback_to_user,
        "document_type_identified": result.document_type_identified,
        "issue_date": result.issue_date_identified,
        "validated_by": "ai" if status == "VALIDADO" else None,
        "uploaded_at": now(),
    })
    triage.checklist[doc_index] = item

    icon = {"VALIDADO": "✅", "ENVIADO": "📥", "REJEITADO": "⚠️"}[status]
    texts = [f"{icon} {item.doc_name}: {result.feedback_to_user}"]
    texts += _progress_texts(triage)
    user_msg = _msg("user", f"📎 Foto enviada: {item.doc_name}", attachment_url=url)
    replies = [_msg("bot", t) for t in texts] if triage.status != "human_takeover" else []
    fields = _status_fields(triage)
    fields[f"checklist.{doc_index}"] = item.model_dump()
    fields["updated_at"] = now()
    await repo.push_messages(protocol_id, [user_msg.model_dump()] + [r.model_dump() for r in replies], fields)
    triage.chat_history += [user_msg, *replies]
    return triage, result, doc_index, replies


def _progress_texts(triage: Triage) -> list[str]:
    if checklist_complete(triage.checklist):
        return [f"🎉 Todos os documentos foram conferidos! Seu protocolo é {triage.protocol_id}. "
                "Nossa equipe já pode dar andamento; você será chamado para o atendimento no balcão."]
    idx = _next_pending(triage.checklist)
    if idx is not None:
        return [f"Próximo documento: {triage.checklist[idx].doc_name}."]
    return ["Recebi todos os documentos. Alguns ainda serão conferidos por um atendente."]


def _status_fields(triage: Triage) -> dict:
    """Recalcula o status após mudança no checklist (não mexe em atendimento humano em curso)."""
    if triage.status != "human_takeover":
        triage.status = "ready_for_counter" if checklist_complete(triage.checklist) else "in_progress"
    return {"status": triage.status}


# ---------------------------------------------------------------------------
# Ações do escrevente
# ---------------------------------------------------------------------------


async def takeover(protocol_id: str, attendant: str) -> Triage:
    triage = await load_triage(protocol_id)
    msg = _msg("system", f"{attendant} assumiu o atendimento.")
    greet = _msg("attendant", f"Olá{', ' + triage.customer_name.split()[0] if triage.customer_name else ''}! "
                              f"Aqui é {attendant}, do {settings.office_name}. Vou continuar seu atendimento.",
                 attendant_name=attendant)
    fields = {"status": "human_takeover", "attendant_name": attendant, "updated_at": greet.timestamp}
    await get_repository().push_messages(protocol_id, [msg.model_dump(), greet.model_dump()], fields)
    return await load_triage(protocol_id)


async def release_to_bot(protocol_id: str) -> Triage:
    triage = await load_triage(protocol_id)
    status = "ready_for_counter" if checklist_complete(triage.checklist) else "in_progress"
    msg = _msg("system", "Atendimento devolvido ao assistente virtual.")
    fields = {"status": status, "human_requested": False, "attendant_name": None, "updated_at": msg.timestamp}
    await get_repository().push_messages(protocol_id, [msg.model_dump()], fields)
    return await load_triage(protocol_id)


async def attendant_message(protocol_id: str, text: str, attendant: str) -> Triage:
    triage = await load_triage(protocol_id)
    messages = []
    fields: dict = {}
    if triage.status != "human_takeover" or not triage.attendant_name:
        # Escrever no chat implica assumir o atendimento (o bot para de responder)
        messages.append(_msg("system", f"{attendant} assumiu o atendimento.").model_dump())
        fields.update(status="human_takeover", attendant_name=attendant)
    msg = _msg("attendant", text.strip(), attendant_name=attendant)
    messages.append(msg.model_dump())
    fields["updated_at"] = msg.timestamp
    await get_repository().push_messages(protocol_id, messages, fields)
    return await load_triage(protocol_id)


async def review_checklist_item(protocol_id: str, index: int, status: str, reason: Optional[str],
                                notify: bool) -> Triage:
    triage = await load_triage(protocol_id)
    if not 0 <= index < len(triage.checklist):
        raise TriageConflict("Documento do checklist inválido.")
    item = triage.checklist[index]
    if status == "REJEITADO" and not (reason or "").strip():
        raise TriageConflict("Informe o motivo da recusa.")
    item = item.model_copy(update={
        "status": status,
        "rejection_reason": reason.strip() if status == "REJEITADO" and reason else None,
        "validated_by": "attendant" if status == "VALIDADO" else None,
    })
    triage.checklist[index] = item
    fields = _status_fields(triage)
    fields[f"checklist.{index}"] = item.model_dump()
    fields["updated_at"] = now()
    messages = []
    if notify:
        if status == "VALIDADO":
            text = f"✅ {item.doc_name}: conferido pela nossa equipe."
        elif status == "REJEITADO":
            text = f"⚠️ {item.doc_name}: {item.rejection_reason} Por favor, envie novamente."
        else:
            text = f"Precisamos que você envie novamente: {item.doc_name}."
        sender = "attendant" if triage.status == "human_takeover" else "bot"
        messages.append(_msg(sender, text, attendant_name=triage.attendant_name if sender == "attendant" else None))
        if status == "VALIDADO" and checklist_complete(triage.checklist):
            messages.append(_msg(sender, _progress_texts(triage)[0],
                                 attendant_name=triage.attendant_name if sender == "attendant" else None))
    await get_repository().push_messages(protocol_id, [m.model_dump() for m in messages], fields)
    return await load_triage(protocol_id)


async def issue_counter_ticket(protocol_id: str) -> Triage:
    triage = await load_triage(protocol_id)
    if triage.counter_ticket:
        return triage
    seq = await get_repository().next_counter(f"ticket-{date.today():%Y%m%d}")
    ticket = f"P{seq:03d}"
    sender = "attendant" if triage.status == "human_takeover" else "bot"
    msg = _msg(sender, f"🎫 Sua senha prioritária de balcão é {ticket}. Apresente-a na recepção com os documentos "
                       "originais. Protocolo: " + triage.protocol_id + ".",
               attendant_name=triage.attendant_name if sender == "attendant" else None)
    fields = {"counter_ticket": ticket, "stage": "done", "updated_at": msg.timestamp}
    await get_repository().push_messages(protocol_id, [msg.model_dump()], fields)
    return await load_triage(protocol_id)


def summarize(triage: Triage) -> TriageSummary:
    required = [c for c in triage.checklist if c.required]
    last = next((m for m in reversed(triage.chat_history) if m.sender != "system"), None)
    return TriageSummary(
        protocol_id=triage.protocol_id,
        customer_name=triage.customer_name,
        customer_contact=triage.customer_contact,
        channel=triage.channel,
        act_name=triage.act_name,
        status=triage.status,
        human_requested=triage.human_requested,
        attendant_name=triage.attendant_name,
        estimated_total=triage.estimated_total,
        docs_validated=sum(c.status == "VALIDADO" for c in required),
        docs_required=len(required),
        docs_rejected=sum(c.status == "REJEITADO" for c in required),
        last_message=last.message[:140] if last else None,
        last_sender=last.sender if last else None,
        counter_ticket=triage.counter_ticket,
        created_at=triage.created_at,
        updated_at=triage.updated_at,
    )
