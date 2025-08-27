from fastapi import APIRouter, Depends
from app.deps.user import get_current_user_id

router = APIRouter()


@router.get("/whoami")
def whoami(uid: str = Depends(get_current_user_id)):
    return {"user_id": uid}


