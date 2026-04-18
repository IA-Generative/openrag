"""Tchap (Matrix) notification dispatcher."""

import httpx
import uuid
from utils.logger import get_logger

from .base import BaseDispatcher, DispatchResult

logger = get_logger()


class TchapDispatcher(BaseDispatcher):
    """Sends notifications to a Tchap/Matrix room.

    Uses the Matrix client-server API to send messages.

    Config:
        homeserver: Matrix homeserver URL (e.g., https://matrix.agent.tchap.gouv.fr)
        room_id: Target room ID (e.g., !abc:agent.tchap.gouv.fr)
        access_token: Bot access token
    """

    async def send(self, title: str, body: str, url: str | None = None) -> DispatchResult:
        homeserver = self.config.get("homeserver", "").rstrip("/")
        room_id = self.config.get("room_id")
        access_token = self.config.get("access_token")

        if not all([homeserver, room_id, access_token]):
            return DispatchResult(success=False, error="Missing homeserver, room_id, or access_token")

        # Format message
        plain_text = f"{title}\n\n{body}"
        html_body = f"<strong>{title}</strong><br/><br/>{body}"
        if url:
            plain_text += f"\n\n{url}"
            html_body += f'<br/><br/><a href="{url}">Ouvrir</a>'

        txn_id = str(uuid.uuid4())
        send_url = f"{homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"

        payload = {
            "msgtype": "m.text",
            "body": plain_text,
            "format": "org.matrix.custom.html",
            "formatted_body": html_body,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.put(
                    send_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
            return DispatchResult(success=True, message=f"Sent to room {room_id}")
        except Exception as e:
            logger.warning("Tchap dispatch failed", room_id=room_id, error=str(e))
            return DispatchResult(success=False, error=str(e))
