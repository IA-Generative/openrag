"""
title: MyRAG Feedback Collector
description: Captures user feedback (thumbs up/down) from Open WebUI and sends to MyRAG
version: 0.1.0
"""

from __future__ import annotations

import re
import threading

import requests
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        myrag_url: str = Field(default="http://myrag:8200")
        enabled: bool = Field(default=True)

    def __init__(self):
        self.valves = self.Valves()

    def outlet(self, body: dict, __user__: dict = {}) -> dict:
        """Intercept messages after LLM response. Detect feedback annotations."""
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        # Look for messages with annotations (feedback)
        for msg in messages:
            annotation = msg.get("annotation")
            if not annotation:
                continue

            rating = annotation.get("rating")
            if rating is None:
                continue

            # Extract the question (last user message before this assistant message)
            question = ""
            for prev in reversed(messages):
                if prev.get("role") == "user":
                    question = prev.get("content", "")
                    break

            # Extract collection from model name
            model = body.get("model", "")
            collection = ""
            match = re.search(r"openrag-(.+)", model)
            if match:
                collection = match.group(1)

            # Fire-and-forget — don't block the response
            threading.Thread(
                target=self._send_feedback,
                args=(collection, question, msg.get("content", ""),
                      1 if rating > 0 else -1,
                      annotation.get("reason", ""),
                      __user__.get("id", ""),
                      body.get("chat_id", ""),
                      msg.get("id", "")),
                daemon=True,
            ).start()

        return body

    def _send_feedback(self, collection: str, question: str, response: str,
                       rating: int, reason: str, user_id: str,
                       chat_id: str, message_id: str):
        """Send feedback to MyRAG API (runs in background thread)."""
        if not collection:
            return

        try:
            requests.post(
                f"{self.valves.myrag_url}/api/feedback/ingest",
                json={
                    "collection": collection,
                    "question": question,
                    "response": response,
                    "rating": rating,
                    "reason": reason,
                    "user_id": user_id,
                    "owui_chat_id": chat_id,
                    "owui_message_id": message_id,
                },
                timeout=5,
            )
        except Exception:
            pass  # silent — don't break the chat
