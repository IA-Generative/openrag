"""Email (SMTP) notification dispatcher."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.logger import get_logger

from .base import BaseDispatcher, DispatchResult

logger = get_logger()


class EmailDispatcher(BaseDispatcher):
    """Sends notifications via SMTP email.

    Config:
        host: SMTP server hostname
        port: SMTP port (default 587)
        username: SMTP username
        password: SMTP password
        from_addr: Sender email address
        to_addrs: List of recipient email addresses (for broadcast)
        use_tls: Whether to use STARTTLS (default True)
    """

    async def send(self, title: str, body: str, url: str | None = None) -> DispatchResult:
        host = self.config.get("host")
        port = self.config.get("port", 587)
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        from_addr = self.config.get("from_addr", username)
        to_addrs = self.config.get("to_addrs", [])
        use_tls = self.config.get("use_tls", True)

        if not host or not to_addrs:
            return DispatchResult(success=False, error="Missing SMTP host or recipients")

        html_body = f"<h2>{title}</h2><p>{body}</p>"
        if url:
            html_body += f'<p><a href="{url}">Open</a></p>'

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = title
            msg["From"] = from_addr
            msg["To"] = ", ".join(to_addrs)
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if username and password:
                    server.login(username, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())

            return DispatchResult(success=True, message=f"Email sent to {len(to_addrs)} recipients")
        except Exception as e:
            logger.warning("Email dispatch failed", error=str(e))
            return DispatchResult(success=False, error=str(e))
