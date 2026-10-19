from fastapi import APIRouter
from apps.api.models.context import UserContext

router = APIRouter()

@router.post("/onboard")
async def onboard_user(context: UserContext):
    # In a real app, we'd save this to a database and return a session token
    return {"status": "success", "context_received": True}
