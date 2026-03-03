"""Email send pipeline step: send sumula.md via MailerSend SMTP."""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ArtifactKind
from app.pipeline._helpers import add_event, get_artifact_path, get_job, load_manifest

logger = logging.getLogger(__name__)


def _send_smtp(
    to: str,
    subject: str,
    body_text: str,
    body_html: str,
    attachment_path: Path,
    attachment_name: str,
) -> None:
    """Send email with attachment via MailerSend SMTP (STARTTLS, port 587)."""
    sender_email = settings.mail_default_sender or settings.smtp_username
    sender_name = settings.mail_default_sender_name
    from_header = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = to

    # Body
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    alt.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alt)

    # Attachment
    data = attachment_path.read_bytes()
    part = MIMEBase("application", "octet-stream")
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
    msg.attach(part)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.sendmail(sender_email, [to], msg.as_string())


async def run(job_id: str, session: AsyncSession) -> None:
    """Send sumula.md to the job's email via MailerSend SMTP."""
    job = await get_job(session, job_id)
    manifest = load_manifest(job)

    await add_event(session, job_id, "SENDING_EMAIL", f"Enviando súmula para {job.email}")

    md_path = await get_artifact_path(session, job_id, ArtifactKind.output_md)
    if md_path is None or not md_path.exists():
        raise RuntimeError("sumula.md não encontrado para envio")

    # Build source summary
    files = manifest.get("files", [])
    urls = manifest.get("urls", {})
    source_lines = []
    for f in files:
        source_lines.append(f"- Arquivo: {f.get('name', 'desconhecido')}")
    for field, url in urls.items():
        if url:
            source_lines.append(f"- {field}: {url}")
    if manifest.get("bibtex"):
        source_lines.append("- BibTeX colado")
    if manifest.get("free_text"):
        source_lines.append("- Texto livre")
    sources_text = "\n".join(source_lines) if source_lines else "Nenhuma fonte registrada"

    body_html = f"""<h2>Súmula Curricular FAPESP</h2>
<p>Sua Súmula Curricular FAPESP foi gerada com sucesso e está anexada a este e-mail.</p>
<p><strong>Job ID:</strong> {job_id}</p>
<h3>Fontes utilizadas:</h3>
<pre>{sources_text}</pre>
<p>O arquivo <code>sumula.md</code> contém o Markdown formatado conforme o modelo FAPESP.</p>"""

    body_text = (
        f"Sua Súmula Curricular FAPESP foi gerada.\n"
        f"Job ID: {job_id}\n\n"
        f"Fontes:\n{sources_text}\n\n"
        f"O arquivo sumula.md está em anexo."
    )

    import asyncio
    await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _send_smtp(
            to=job.email,
            subject="Súmula Curricular FAPESP em Markdown",
            body_text=body_text,
            body_html=body_html,
            attachment_path=md_path,
            attachment_name="sumula.md",
        ),
    )

    await add_event(session, job_id, "SENDING_EMAIL", f"E-mail enviado para {job.email}")
