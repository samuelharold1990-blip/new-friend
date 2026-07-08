"""Memory viewer: facts CRUD + relationship status."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import now_ms
from ..deps import get_db, get_relationship
from ..models import FactUpdate

router = APIRouter(prefix="/api/memory")


@router.get("/facts")
async def get_facts(request: Request):
    db = get_db(request)
    facts = db.query("SELECT id, category, content, created_at, updated_at "
                     "FROM facts WHERE active = 1 ORDER BY category, updated_at DESC")
    state = get_relationship(request).get()
    return {
        "facts": facts,
        "relationship": {
            "stage": state["stage"], "score": state["score"],
            "since": state["stage_entered_at"], "first_chat_at": state["first_chat_at"],
        },
    }


@router.put("/facts/{fact_id}")
async def update_fact(request: Request, fact_id: int, body: FactUpdate):
    db = get_db(request)
    if not db.query_one("SELECT id FROM facts WHERE id = ? AND active = 1", (fact_id,)):
        return JSONResponse({"error": "not found"}, status_code=404)
    db.execute("UPDATE facts SET content = ?, updated_at = ? WHERE id = ?",
               (body.content.strip(), now_ms(), fact_id))
    return {"ok": True}


@router.delete("/facts/{fact_id}")
async def delete_fact(request: Request, fact_id: int):
    get_db(request).execute("UPDATE facts SET active = 0 WHERE id = ?", (fact_id,))
    return {"ok": True}
