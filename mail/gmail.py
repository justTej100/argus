from __future__ import annotations

"""Send study flashcards to the user's Gmail inbox via SMTP."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from citations import LEGACY_CITATION_PATTERN, PAGE_CITATION_PATTERN, pdf_href, resolve_document_id

_PAGE_TAG = PAGE_CITATION_PATTERN


class EmailNotConfiguredError(RuntimeError):
    """Raised when Gmail SMTP credentials are missing."""


def _smtp_settings() -> tuple[str, str]:
    user = (os.environ.get('GMAIL_USER') or '').strip()
    password = (os.environ.get('GMAIL_APP_PASSWORD') or '').strip()
    if not user or not password:
        raise EmailNotConfiguredError(
            'Gmail is not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD in .env '
            '(use a Google App Password — see README).'
        )
    return user, password


def _app_base_url() -> str:
    return (os.environ.get('APP_BASE_URL') or 'http://localhost:8000').rstrip('/')


def _format_citation_links(citations: list[str], sources: list[dict]) -> str:
    if not citations:
        return ''
    parts: list[str] = []
    for tag in citations:
        page_match = _PAGE_TAG.search(tag) or LEGACY_CITATION_PATTERN.search(tag)
        if not page_match:
            parts.append(escape(tag))
            continue
        page = int(page_match.group(1))
        document_id = resolve_document_id(page, sources)
        if not document_id:
            parts.append(escape(tag))
            continue
        href = f'{_app_base_url()}{pdf_href(document_id, page)}'
        parts.append(f'<a href="{escape(href)}">p{page}</a>')
    return ' · '.join(parts)


def build_flashcards_html(*, topic: str, items: list[dict], sources: list[dict]) -> str:
    """Render a simple HTML email body for flashcard decks."""
    cards_html: list[str] = []
    for index, item in enumerate(items, start=1):
        front = escape(str(item.get('front', '')))
        back = escape(str(item.get('back', ''))).replace('\n', '<br>')
        citations = item.get('citations') or []
        cite_html = _format_citation_links(citations, sources)
        cite_block = f'<p style="margin:8px 0 0;font-size:12px;color:#5b7a94;">{cite_html}</p>' if cite_html else ''
        cards_html.append(
            f"""
            <div style="margin:16px 0;padding:14px 16px;border:1px solid #c5e8ef;border-radius:10px;background:#f4fcfd;">
              <p style="margin:0 0 8px;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#2a7f8f;">Card {index}</p>
              <p style="margin:0 0 10px;font-weight:600;color:#0a2530;">{front}</p>
              <p style="margin:0;color:#1a3a4a;">{back}</p>
              {cite_block}
            </div>
            """
        )

    topic_html = escape(topic)
    return f"""
    <html>
      <body style="font-family:Inter,Arial,sans-serif;background:#eef7fa;color:#0a2530;padding:24px;">
        <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #b8e0ea;border-radius:14px;padding:24px;">
          <p style="margin:0 0 6px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#2a7f8f;">Argus Study Buddy</p>
          <h1 style="margin:0 0 8px;font-size:22px;">Flashcards: {topic_html}</h1>
          <p style="margin:0 0 20px;color:#5b7a94;">Grounded in your textbook library. Tap citations to open the PDF.</p>
          {''.join(cards_html)}
        </div>
      </body>
    </html>
    """


def build_flashcards_plain(*, topic: str, items: list[dict]) -> str:
    """Plain-text fallback for mail clients without HTML."""
    lines = [f'Argus flashcards — {topic}', '']
    for index, item in enumerate(items, start=1):
        lines.append(f'Card {index}')
        lines.append(f"Q: {item.get('front', '')}")
        lines.append(f"A: {item.get('back', '')}")
        citations = item.get('citations') or []
        if citations:
            lines.append('Citations: ' + ', '.join(citations))
        lines.append('')
    return '\n'.join(lines)


def send_flashcards_email(
    *,
    to_email: str,
    topic: str,
    items: list[dict],
    sources: list[dict],
) -> None:
    """Send a flashcard deck to the signed-in user's inbox."""
    if not items:
        raise ValueError('No flashcards to email.')
    sender, password = _smtp_settings()
    recipient = to_email.strip()
    if not recipient:
        raise ValueError('Recipient email is required.')

    message = MIMEMultipart('alternative')
    message['Subject'] = f'Argus flashcards — {topic[:80]}'
    message['From'] = sender
    message['To'] = recipient

    plain = build_flashcards_plain(topic=topic, items=items)
    html = build_flashcards_html(topic=topic, items=items, sources=sources)
    message.attach(MIMEText(plain, 'plain', 'utf-8'))
    message.attach(MIMEText(html, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, [recipient], message.as_string())
