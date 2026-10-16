import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from pymongo import ReturnDocument

from app.api.deps import parse_object_id, read_upload
from app.core import storage
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.fraud_schema import (
    AuditChecks, DecisionRequest, DocumentType, FraudAudit, FraudAuditSummary, OfficerDecision,
    ProcurationInput, RiskLevel, SignatureCheck,
)
from app.services import censec_checker_service, forensics_service, risk_service, signature_service
from app.services.cpf import format_cpf, is_valid_cpf, mask_cpf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fraud", tags=["Auditoria antifraude"])

FileKind = Literal["document", "heatmap", "ela", "signature", "signature_card"]
ACTION_TO_DECISION: dict[str, OfficerDecision] = {
    "APROVAR_FE_PUBLICA": "HOMOLOGADO",
    "SOLICITAR_PRESENCIAL": "PENDENTE",
    "REJEITAR_FALSIDADE": "RECUSADO",
}


def to_audit(doc: dict) -> FraudAudit:
    return FraudAudit(
        id=str(doc["_id"]),
        files={k: bool(v) for k, v in doc.get("files", {}).items()},
        **{k: v for k, v in doc.items() if k not in {"_id", "files"}},
    )


@router.post("/audit-document", response_model=FraudAudit, status_code=status.HTTP_201_CREATED)
async def audit_document(
    document: UploadFile = File(..., description="RG, CNH, procuração ou título (imagem ou PDF)"),
    signature_image: Optional[UploadFile] = File(None, description="Recorte da assinatura lançada no título"),
    protocol_number: str = Form(..., min_length=1, max_length=40),
    service_type: str = Form(..., min_length=1, max_length=80),
    document_type: DocumentType = Form("OUTRO"),
    presenter_name: Optional[str] = Form(None, max_length=200),
    presenter_cpf: Optional[str] = Form(None),
    procuration_book: Optional[str] = Form(None, max_length=20),
    procuration_page: Optional[str] = Form(None, max_length=20),
    procuration_act: Optional[str] = Form(None, max_length=40),
    procuration_origin_office: Optional[str] = Form(None, max_length=200),
    procuration_issued_on: Optional[date] = Form(None),
    procuration_revocation_declared: bool = Form(False),
    censec_confirmed_on: Optional[date] = Form(None),
):
    db = get_db()
    cpf = None
    if presenter_cpf:
        if not is_valid_cpf(presenter_cpf):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "CPF do apresentante inválido")
        cpf = format_cpf(presenter_cpf)

    doc_bytes = await read_upload(document, "Documento")
    sig_bytes = await read_upload(signature_image, "Assinatura") if signature_image and signature_image.filename else None

    # 1. Análise forense
    try:
        forensics = await forensics_service.analyze_document(doc_bytes, document.filename or "", document_type)
    except forensics_service.UnsupportedDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    # 2. Cotejo grafotécnico
    card = await db.signature_cards.find_one({"cpf": cpf}) if cpf else None
    sig_png = None
    if sig_bytes is None:
        sig_check = SignatureCheck(status="NAO_EXECUTADO", observation="Recorte de assinatura não enviado.")
    elif card is None:
        sig_check = SignatureCheck(status="NAO_EXECUTADO", observation=(
            "Cartão de firma não localizado para o CPF informado — cotejo impossível; exigir abertura de firma."
            if cpf else "CPF do apresentante não informado — cotejo com cartão de firma impossível."))
    else:
        try:
            card_bytes = storage.load(card["signature_sample_url"])
            sig_png = signature_service.crop_signature_png(sig_bytes)
            sig_check = await signature_service.compare(
                sig_bytes, card_bytes, card.get("card_number") or f"do CPF {mask_cpf(cpf)}", str(card["_id"]))
        except signature_service.InvalidSignatureImage as exc:
            sig_check = SignatureCheck(status="INCONCLUSIVO", observation=str(exc))

    # 3. Procuração / CENSEC
    proc_input = ProcurationInput(
        book=procuration_book, page=procuration_page, act=procuration_act,
        origin_office=procuration_origin_office, issued_on=procuration_issued_on,
        revocation_declared=procuration_revocation_declared, censec_confirmed_on=censec_confirmed_on,
    )
    proc_check = await censec_checker_service.check_procuration(proc_input, document_type)

    checks = AuditChecks(document_tampering=forensics.check, signature_matching=sig_check,
                         power_of_attorney_censec=proc_check)

    # 4. Reincidência + consolidação
    prior = await db.suspicious_patterns.find_one({"cpf": cpf}) if cpf else None
    prior_alerts = prior.get("alert_count", 0) if prior else 0
    score, level, factors, recommendation = risk_service.consolidate(checks, prior_alerts)

    files = {
        "document": storage.save(forensics.display_jpeg, "documents", ".jpg"),
        "heatmap": storage.save(forensics.heatmap_jpeg, "heatmaps", ".jpg"),
        "ela": storage.save(forensics.ela_jpeg, "heatmaps", ".jpg"),
        "signature": storage.save(sig_png, "signatures", ".png") if sig_png else None,
        "signature_card": card["signature_sample_url"] if card and sig_png else None,
    }
    now = datetime.now(timezone.utc)
    record = {
        "protocol_number": protocol_number.strip(),
        "service_type": service_type.strip(),
        "document_type": document_type,
        "presenter_name": presenter_name.strip() if presenter_name else None,
        "presenter_cpf": cpf,
        "risk_level": level,
        "risk_score": score,
        "tampering_detected": forensics.check.status == "SUSPEITO",
        "tampering_details": forensics.check.findings,
        "signature_match_score": sig_check.match_score,
        "procuration_verified": proc_check.verified_on_censec if proc_check.status != "NAO_APLICAVEL" else None,
        "recommendation_to_officer": recommendation,
        "risk_factors": factors,
        "checks": checks.model_dump(),
        "files": files,
        "officer_decision": "PENDENTE",
        "officer_notes": None,
        "in_person_requested": False,
        "decision_history": [],
        "created_at": now,
        "decided_at": None,
    }
    result = await db.fraud_audits.insert_one(record)
    record["_id"] = result.inserted_id

    if cpf and level in {"ALTO", "CRITICO"}:
        await db.suspicious_patterns.update_one(
            {"cpf": cpf},
            {"$inc": {"alert_count": 1}, "$push": {"audit_ids": result.inserted_id},
             "$set": {"last_alert_at": now, "last_risk_level": level}, "$setOnInsert": {"first_alert_at": now}},
            upsert=True,
        )
    logger.info("Auditoria %s protocolo=%s risco=%s(%s) cpf=%s", result.inserted_id, protocol_number,
                level, score, mask_cpf(cpf) if cpf else "-")
    return to_audit(record)


@router.get("/audits", response_model=list[FraudAuditSummary])
async def list_audits(
    risk_level: Optional[RiskLevel] = None,
    decision: Optional[OfficerDecision] = None,
    protocol: Optional[str] = Query(None, max_length=40),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    query: dict = {}
    if risk_level:
        query["risk_level"] = risk_level
    if decision:
        query["officer_decision"] = decision
    if protocol:
        query["protocol_number"] = protocol.strip()
    cursor = get_db().fraud_audits.find(query).sort("created_at", -1).skip(skip).limit(limit)
    return [FraudAuditSummary(id=str(d["_id"]), **{k: v for k, v in d.items() if k != "_id"}) async for d in cursor]


@router.get("/stats")
async def stats():
    db = get_db()
    by_level = {lvl: 0 for lvl in ("BAIXO", "MEDIO", "ALTO", "CRITICO")}
    async for row in db.fraud_audits.aggregate([{"$group": {"_id": "$risk_level", "n": {"$sum": 1}}}]):
        by_level[row["_id"]] = row["n"]
    pending = await db.fraud_audits.count_documents({"officer_decision": "PENDENTE"})
    return {"by_risk_level": by_level, "pending": pending, "total": sum(by_level.values())}


@router.get("/audits/{audit_id}", response_model=FraudAudit)
async def get_audit(audit_id: str):
    doc = await get_db().fraud_audits.find_one({"_id": parse_object_id(audit_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Auditoria não encontrada")
    return to_audit(doc)


@router.get("/audits/{audit_id}/files/{kind}")
async def get_audit_file(audit_id: str, kind: FileKind):
    doc = await get_db().fraud_audits.find_one({"_id": parse_object_id(audit_id)}, {"files": 1})
    key = (doc or {}).get("files", {}).get(kind)
    if not key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo indisponível (inexistente ou expurgado)")
    try:
        data = storage.load(key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo expurgado") from None
    return Response(data, media_type=storage.media_type(key), headers={"Cache-Control": "no-store"})


@router.patch("/audits/{audit_id}/decision", response_model=FraudAudit)
async def record_decision(audit_id: str, body: DecisionRequest):
    """Despacho do Oficial/Escrevente autorizado. Decisões finais (homologação/recusa) são imutáveis;
    todo despacho é acrescentado ao histórico (append-only) para fins de correição."""
    oid = parse_object_id(audit_id)
    now = datetime.now(timezone.utc)
    decision = ACTION_TO_DECISION[body.action]
    entry = {"action": body.action, "decision": decision, "officer_name": body.officer_name,
             "notes": body.notes, "decided_at": now}
    update: dict = {
        "$set": {"officer_decision": decision, "officer_notes": body.notes},
        "$push": {"decision_history": entry},
    }
    if body.action == "SOLICITAR_PRESENCIAL":
        update["$set"]["in_person_requested"] = True
    else:
        update["$set"]["decided_at"] = now
        update["$set"]["retention_until"] = now + timedelta(days=get_settings().retention_days)

    doc = await get_db().fraud_audits.find_one_and_update(
        {"_id": oid, "officer_decision": "PENDENTE"}, update, return_document=ReturnDocument.AFTER)
    if doc is None:
        exists = await get_db().fraud_audits.find_one({"_id": oid}, {"officer_decision": 1})
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Auditoria não encontrada")
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Ato já despachado como {exists['officer_decision']}; decisão final é imutável")
    return to_audit(doc)
