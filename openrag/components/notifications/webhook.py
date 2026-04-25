"""Webhook notification dispatcher."""

import httpx
from utils.logger import get_logger

from .base import BaseDispatcher, DispatchResult

logger = get_logger()


class WebhookDispatcher(BaseDispatcher):
    """Sends notifications via HTTP webhook POST.

    Config:
        url: Webhook URL
        headers: Optional dict of HTTP headers
        template: "markdown" (default), "json", or "html"
    """

    async def send(self, title: str, body: str, url: str | None = None) -> DispatchResult:
        webhook_url = self.config.get("url")
        if not webhook_url:
            return DispatchResult(success=False, error="No webhook URL configured")

        headers = self.config.get("headers", {})
        template = self.config.get("template", "markdown")

        if template == "json":
            payload = {"title": title, "body": body, "url": url}
        elif template == "html":
            html_body = f"<h2>{title}</h2><p>{body}</p>"
            if url:
                html_body += f'<p><a href="{url}">Open</a></p>'
            payload = {"html": html_body}
        else:  # markdown
            md = f"**{title}**\n\n{body}"
            if url:
                md += f"\n\n[Open]({url})"
            payload = {"text": md}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload, headers=headers)
                resp.raise_for_status()
            return DispatchResult(success=True, message=f"Sent to {webhook_url}")
        except Exception as e:
            logger.warning("Webhook dispatch failed", url=webhook_url, error=str(e))
            return DispatchResult(success=False, error=str(e))
