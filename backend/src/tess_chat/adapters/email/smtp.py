import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class SmtpEmailSender:
    host: str
    port: int
    username: str
    password: str
    sender: str

    async def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        await asyncio.to_thread(self._deliver, message)

    def _deliver(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(self.username, self.password)
            smtp.send_message(message)


class LogEmailSender:
    async def send(self, to: str, subject: str, body: str) -> None:
        log.info("email_not_sent", to=to, subject=subject, body=body)
