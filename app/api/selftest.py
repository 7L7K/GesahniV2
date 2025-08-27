from fastapi import APIRouter

router = APIRouter()


@router.get("/_selftest")
def selftest():
    return {"ok": True, "routers": ["/v1/spotify/*","/v1/spotify/devices","/v1/spotify/play","/v1/spotify/status","/v1/integrations/status"]}


