from typing import List, Optional

from fastapi import APIRouter

from app.core.database import db
from app.schemas.qualification import Rule

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=List[Rule])
async def list_rules(act_type: Optional[str] = None):
    query = {"active": {"$ne": False}}
    if act_type:
        query["act_type"] = act_type
    return await db["act_rules"].find(query).sort("rule_code", 1).to_list(500)
