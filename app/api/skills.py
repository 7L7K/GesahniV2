from __future__ import annotations

from fastapi import APIRouter, Depends

try:
    from app.skills.base import SKILLS as BUILTIN_CATALOG
except Exception:
    BUILTIN_CATALOG = []  # type: ignore

from app.deps.scopes import docs_security_with


router = APIRouter(tags=["Admin"], dependencies=[Depends(docs_security_with(["admin:write"]))])


@router.get("/skills/list")
async def skills_list():
    items = []
    for entry in BUILTIN_CATALOG:
        if isinstance(entry, tuple) and len(entry) == 2:
            keywords, SkillClass = entry
            name = getattr(SkillClass, "__name__", str(SkillClass))
            items.append({"name": name, "keywords": list(keywords) if isinstance(keywords, (list, set, tuple)) else [str(keywords)]})
    return {"items": items}


