"""
title: OpenRAG Feedback Forwarder
description: Forwards user feedback (thumbs up/down) from Open WebUI to OpenRAG's feedback API
author: OpenRAG
version: 0.1.0
"""

import json
import threading

import requests
from pydantic import BaseModel, Field


class Pipe:
    """Open WebUI Function that intercepts feedback annotations and forwards them to OpenRAG."""

    class Valves(BaseModel):
        openrag_url: str = Field(
            default="http://openrag:8000",
            description="Base URL of the OpenRAG API",
        )
        service_key: str = Field(
            default="",
            description="Service key for OpenRAG feedback ingestion (X-Service-Key header)",
        )
        enabled: bool = Field(
            default=True,
            description="Enable/disable feedback forwarding",
        )

    def __init__(self):
        self.valves = self.Valves()

    def outlet(self, body: dict, __user__: dict = None, **kwargs) -> dict:
        """Called after each model response. Checks for feedback annotations.

        Open WebUI stores feedback as an 'annotation' field on messages:
        {"annotation": {"rating": -1, "reason": "...", "comment": "..."}}
        """
        if not self.valves.enabled:
            return body

        try:
            messages = body.get("messages", [])
            if not messages:
                return body

            # Look for messages with annotations (feedback)
            feedbacks_to_send = []
            for i, msg in enumerate(messages):
                annotation = msg.get("annotation")
                if not annotation or annotation.get("rating") is None:
                    continue

                rating_value = annotation["rating"]
                # Open WebUI uses various formats; normalize to -1/0/1
                if isinstance(rating_value, (int, float)):
                    if rating_value > 0:
                        normalized_rating = 1
                    elif rating_value < 0:
                        normalized_rating = -1
                    else:
                        normalized_rating = 0
                else:
                    continue

                # Find the preceding user message as the "question"
                question = ""
                for j in range(i - 1, -1, -1):
                    if messages[j].get("role") == "user":
                        question = messages[j].get("content", "")
                        break

                if not question:
                    continue

                feedback = {
                    "external_user_id": (__user__ or {}).get("id", ""),
                    "question": question,
                    "response": msg.get("content", ""),
                    "model": body.get("model", ""),
                    "rating": normalized_rating,
                    "reason": annotation.get("reason", "") or annotation.get("comment", ""),
                    "owui_chat_id": body.get("chat_id", ""),
                    "owui_message_id": msg.get("id", ""),
                }
                feedbacks_to_send.append(feedback)

            if feedbacks_to_send:
                # Fire-and-forget: send in background thread
                threading.Thread(
                    target=self._send_feedbacks,
                    args=(feedbacks_to_send,),
                    daemon=True,
                ).start()

        except Exception:
            pass  # Never block the response

        return body

    def _send_feedbacks(self, feedbacks: list[dict]):
        """Send feedbacks to OpenRAG API (runs in background thread)."""
        try:
            url = f"{self.valves.openrag_url.rstrip('/')}/admin/feedback/ingest"
            headers = {"Content-Type": "application/json"}
            if self.valves.service_key:
                headers["X-Service-Key"] = self.valves.service_key

            resp = requests.post(url, json={"feedbacks": feedbacks}, headers=headers, timeout=10)
            resp.raise_for_status()
        except Exception:
            pass  # Best-effort
