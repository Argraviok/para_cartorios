from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import embedder_dep, precedent_repo_dep
from app.repositories.precedents import PrecedentRepository
from app.schemas.precedent_schema import PrecedentBase, PrecedentCreate, PrecedentOut
from app.services.embedding_service import Embedder

router = APIRouter(prefix="/api/precedents", tags=["precedents"])


@router.get("", response_model=list[PrecedentOut])
async def list_precedents(repo: Annotated[PrecedentRepository, Depends(precedent_repo_dep)]):
    return await repo.list_all()


@router.post("", response_model=PrecedentOut, status_code=201)
async def create_precedent(
    body: PrecedentCreate,
    repo: Annotated[PrecedentRepository, Depends(precedent_repo_dep)],
    embedder: Annotated[Embedder, Depends(embedder_dep)],
):
    data = PrecedentBase.model_validate(body.model_dump(exclude={"id"}))
    embedding = await embedder.embed(data.build_embedding_text(), task="document")
    return await repo.upsert(body.id, data, embedding, embedder.model)
