from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.deps import generator_dep, note_repo_dep, settings_dep
from app.core.config import Settings
from app.repositories.notes import NoteConflict, NoteNotFound, NoteRepository
from app.schemas.devolution_schema import (
    DevolutionNote,
    DevolutionNoteResponse,
    GenerateNoteRequest,
    NotePatch,
    PreviewRequest,
    PreviewResponse,
    Requirement,
    RequirementEdit,
)
from app.services.generator_service import GenerationError, LLMNotConfigured, NoteGenerator
from app.services.render_service import markdown_to_plain_text, render_note

router = APIRouter(prefix="/api/devolution-notes", tags=["devolution-notes"])

Repo = Annotated[NoteRepository, Depends(note_repo_dep)]
Config = Annotated[Settings, Depends(settings_dep)]


def _renumber(edits: list[RequirementEdit]) -> list[Requirement]:
    return [Requirement(order=n, **e.model_dump()) for n, e in enumerate(edits, start=1)]


def _render(settings: Settings, note: DevolutionNote, requirements: list[Requirement],
            note_number: str | None = None, issue_date: date | None = None) -> str:
    return render_note(
        settings=settings,
        protocol_number=note.protocol_number,
        protocol_date=note.protocol_date,
        act_type=note.act_type,
        presenter_name=note.presenter_name,
        requirements=requirements,
        note_number=note_number or note.note_number,
        issue_date=issue_date or (note.issued_at.date() if note.issued_at else None),
    )


async def _get_or_404(repo: NoteRepository, note_id: str) -> DevolutionNote:
    try:
        return await repo.get(note_id)
    except NoteNotFound:
        raise HTTPException(404, "Nota não encontrada")


@router.post("/generate", response_model=DevolutionNoteResponse, status_code=201)
async def generate_devolution_note(
    req: GenerateNoteRequest,
    repo: Repo,
    settings: Config,
    generator: Annotated[NoteGenerator, Depends(generator_dep)],
):
    try:
        result = await generator.generate(req)
    except LLMNotConfigured as exc:
        raise HTTPException(503, str(exc))
    except GenerationError as exc:
        raise HTTPException(502, str(exc))

    full_text = render_note(
        settings=settings,
        protocol_number=req.protocol_number,
        protocol_date=req.protocol_date,
        act_type=req.act_type,
        presenter_name=req.presenter_name,
        requirements=result.requirements,
    )
    note = await repo.create({
        "protocol_number": req.protocol_number,
        "protocol_date": req.protocol_date,
        "act_type": req.act_type,
        "presenter_name": req.presenter_name,
        "uf": req.uf,
        "requirements": [r.model_dump(mode="json") for r in result.requirements],
        "full_compiled_text": full_text,
        "llm_model": result.llm_model,
        "prompt_version": settings.prompt_version,
    })
    return DevolutionNoteResponse(**note.model_dump(), warnings=result.warnings)


@router.get("/{note_id}", response_model=DevolutionNote)
async def get_note(note_id: str, repo: Repo):
    return await _get_or_404(repo, note_id)


@router.patch("/{note_id}", response_model=DevolutionNote)
async def update_note(note_id: str, body: NotePatch, repo: Repo, settings: Config):
    note = await _get_or_404(repo, note_id)
    requirements = _renumber(body.requirements)
    try:
        return await repo.update_draft(note_id, body.version, {
            "requirements": [r.model_dump(mode="json") for r in requirements],
            "full_compiled_text": _render(settings, note, requirements),
        })
    except NoteConflict as exc:
        raise HTTPException(409, str(exc))
    except NoteNotFound:
        raise HTTPException(404, "Nota não encontrada")


@router.post("/{note_id}/preview", response_model=PreviewResponse)
async def preview_note(note_id: str, body: PreviewRequest, repo: Repo, settings: Config):
    note = await _get_or_404(repo, note_id)
    requirements = _renumber(body.requirements) if note.status == "draft" else note.requirements
    return PreviewResponse(markdown=_render(settings, note, requirements))


@router.post("/{note_id}/issue", response_model=DevolutionNote)
async def issue_note(note_id: str, repo: Repo, settings: Config):
    try:
        note = await repo.claim_for_issue(note_id)
    except NoteNotFound:
        raise HTTPException(404, "Nota não encontrada")
    except NoteConflict as exc:
        raise HTTPException(409, str(exc))

    if not note.requirements:
        await repo.release_issue_claim(note_id)
        raise HTTPException(422, "A nota não possui exigências.")
    incomplete = [r.order for r in note.requirements if not r.legal_basis.strip() or not r.suggested_solution.strip()]
    if incomplete:
        await repo.release_issue_claim(note_id)
        raise HTTPException(422, f"Complete fundamentação e providência das exigências: {incomplete}")

    today = date.today()
    seq = await repo.next_number(today.year)
    number = f"{seq}/{today.year}"
    return await repo.finalize_issue(note_id, {
        "note_number": number,
        "full_compiled_text": _render(settings, note, note.requirements, note_number=number, issue_date=today),
    })


@router.get("/{note_id}/export.md", response_class=PlainTextResponse)
async def export_markdown(note_id: str, repo: Repo):
    note = await _get_or_404(repo, note_id)
    return _download(note, note.full_compiled_text, "md", "text/markdown")


@router.get("/{note_id}/export.txt", response_class=PlainTextResponse)
async def export_text(note_id: str, repo: Repo):
    note = await _get_or_404(repo, note_id)
    return _download(note, markdown_to_plain_text(note.full_compiled_text), "txt", "text/plain")


def _download(note: DevolutionNote, content: str, ext: str, media_type: str) -> PlainTextResponse:
    label = note.note_number.replace("/", "-") if note.note_number else f"minuta-protocolo-{note.protocol_number}"
    return PlainTextResponse(
        content,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="nota-devolutiva-{label}.{ext}"'},
    )
