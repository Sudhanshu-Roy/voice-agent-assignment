"""
Mint LiveKit participant tokens and dispatch the phone agent into a fresh room.
"""

import os
import uuid
import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("vaiu.backend.routes.livekit")

router = APIRouter(prefix="/api/livekit", tags=["LiveKit"])

AGENT_NAME = os.getenv("AGENT_NAME", "vaiu-phone-agent")


class TokenResponse(BaseModel):
    success: bool = True
    serverUrl: str
    token: str
    roomName: str
    participantIdentity: str
    agentName: str


class TokenError(BaseModel):
    success: bool = False
    message: str


@router.post("/token", response_model=TokenResponse)
def create_voice_token():
    """
    Create a unique room + join token that auto-dispatches the voice agent.
    Frontend connects with livekit-client using serverUrl + token.
    """
    livekit_url = os.getenv("LIVEKIT_URL", "").strip()
    api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()

    if not livekit_url or not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "message": (
                    "LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                    "and LIVEKIT_API_SECRET in .env, then restart the backend."
                ),
            },
        )

    try:
        from livekit import api
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": f"livekit package missing: {exc}"},
        ) from exc

    room_name = f"phone-{uuid.uuid4().hex[:10]}"
    identity = f"caller-{uuid.uuid4().hex[:8]}"

    try:
        token = (
            api.AccessToken(api_key, api_secret)
            .with_identity(identity)
            .with_name("Caller")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_room_config(
                api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(agent_name=AGENT_NAME),
                    ]
                )
            )
            .to_jwt()
        )
    except Exception as exc:
        logger.error("Failed to mint LiveKit token: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": "Failed to create LiveKit token"},
        ) from exc

    logger.info(
        "Issued LiveKit token for room=%s identity=%s agent=%s",
        room_name,
        identity,
        AGENT_NAME,
    )

    return TokenResponse(
        serverUrl=livekit_url,
        token=token,
        roomName=room_name,
        participantIdentity=identity,
        agentName=AGENT_NAME,
    )
