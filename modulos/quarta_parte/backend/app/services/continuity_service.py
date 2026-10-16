"""Continuidade dominial subjetiva (art. 195 e 237 da Lei 6.015/73) e ônus vigentes."""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from app.schemas.geo_schema import (
    ActiveLien,
    ChainLink,
    RegistryAct,
    RegistryExtraction,
    SubjectiveContinuity,
)

_NAME_PREFIXES = re.compile(
    r"^(ESPOLIO|ESPÓLIO|HERDEIROS|SUCESSORES)\s+(DE|DO|DA)\s+", re.IGNORECASE
)
_NAME_NOISE = re.compile(r"\b(SR|SRA|DR|DRA)\.?\s+|[,.;:()]")
_CODE_RE = re.compile(r"(R|AV)\s*[-.]?\s*0*(\d+)", re.IGNORECASE)

FUZZY_THRESHOLD = 0.88


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper().strip()
    s = _NAME_PREFIXES.sub("", s)
    s = _NAME_NOISE.sub(" ", s)
    return " ".join(s.split())


def names_match(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    return na == nb or SequenceMatcher(None, na, nb).ratio() >= FUZZY_THRESHOLD


def normalize_code(code: str) -> str:
    m = _CODE_RE.search(code or "")
    return f"{m.group(1).upper()}-{int(m.group(2))}" if m else (code or "").strip().upper()


def _act_order(act: RegistryAct) -> int:
    m = _CODE_RE.search(act.act_code)
    return int(m.group(2)) if m else 0


def _in(name: str, group: list[str]) -> bool:
    return any(names_match(name, g) for g in group)


def analyze_continuity(
    registry: RegistryExtraction, sellers_in_title: Optional[list[str]] = None
) -> SubjectiveContinuity:
    acts = sorted(registry.acts, key=_act_order)
    sellers = [s for s in (sellers_in_title or []) if s and s.strip()]

    # --- Cadeia de transmissões -------------------------------------------
    chain: list[ChainLink] = []
    holders: list[str] = []
    holder_act: Optional[str] = None
    chain_breaks: list[str] = []

    for act in acts:
        if not act.is_ownership_transfer:
            continue
        code = normalize_code(act.act_code)
        if not holders:
            link_ok, note = True, "Primeira transmissão registrada nesta matrícula (origem na matrícula/transcrição anterior)."
        else:
            missing = [g for g in act.grantors if not _in(g, holders)]
            link_ok = not missing and bool(act.grantors)
            note = None
            if missing:
                note = f"Transmitente(s) {', '.join(missing)} não figurava(m) como titular(es) em {holder_act}."
                chain_breaks.append(f"{code}: {note}")
            elif not act.grantors:
                note = "Transmitente não identificado no ato."
                chain_breaks.append(f"{code}: {note}")
        chain.append(
            ChainLink(
                act_code=code,
                act_date=act.act_date,
                act_type=act.act_type,
                grantors=act.grantors,
                grantees=act.grantees,
                is_continuous=link_ok,
                note=note,
            )
        )
        holders = list(act.grantees)
        holder_act = code

    # --- Ônus vigentes -----------------------------------------------------
    cancelled = {normalize_code(a.cancels_act_code) for a in acts if a.cancels_act_code}
    liens = [
        ActiveLien(
            act_code=normalize_code(a.act_code),
            type=a.act_type,
            court_or_creditor=a.court_or_creditor,
            summary=a.summary,
        )
        for a in acts
        if a.is_encumbrance and normalize_code(a.act_code) not in cancelled
    ]

    # --- Confronto com o título -------------------------------------------
    current_owner = (
        f"{' e '.join(holders)} ({holder_act})" if holders else "NÃO IDENTIFICADO"
    )
    observations: list[str] = []
    status = "REGULAR"

    if not holders:
        status = "ALERTA"
        observations.append("Nenhum ato de transmissão identificado; titular atual não determinado.")

    if sellers and holders:
        strangers = [s for s in sellers if not _in(s, holders)]
        absent_owners = [h for h in holders if not _in(h, sellers)]
        if strangers:
            status = "QUEBRA_DETECTADA"
            observations.append(
                f"O vendedor no título apresentado ({', '.join(strangers)}) não coincide com o "
                f"proprietário registral atual ({' e '.join(holders)}, {holder_act}). Necessário "
                "registro prévio do título aquisitivo do transmitente (ex.: formal de partilha, "
                "escritura de cessão ou compra e venda)."
            )
        elif absent_owners:
            status = "ALERTA"
            observations.append(
                f"Coproprietário(s) {', '.join(absent_owners)} não figura(m) como vendedor(es): "
                "verifique se a alienação é de fração ideal ou se falta anuência."
            )
    elif not sellers:
        if status == "REGULAR":
            status = "ALERTA"
        observations.append("Título/contrato não informado: continuidade com o vendedor não verificada.")

    if chain_breaks:
        status = "QUEBRA_DETECTADA"
        observations.append("Quebra interna na cadeia dominial: " + " ".join(chain_breaks))

    if liens:
        if status == "REGULAR":
            status = "ALERTA"
        observations.append(
            "Ônus/restrições vigentes: "
            + ", ".join(f"{lien.type} ({lien.act_code})" for lien in liens)
            + "."
        )

    if status == "REGULAR":
        observations.append("Vendedor coincide com o titular registral e não há ônus vigentes.")

    return SubjectiveContinuity(
        status=status,
        current_registered_owner=current_owner,
        current_owner_act=holder_act,
        seller_in_contract=" e ".join(sellers) if sellers else None,
        active_liens=liens,
        chain=chain,
        observation=" ".join(observations),
    )
