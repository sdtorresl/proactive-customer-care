"""Notify the client through SendGrid when an anomaly is detected and escalated."""

from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.anomaly import Anomaly
from app.config import Client, Settings


def _build_email_body(client: Client, anomaly: Anomaly, ticket_url: Optional[str]) -> str:
    lines = [
        f"Hello {client.name} team,",
        "",
        "Our monitoring system detected a sustained increase in errors "
        f"(code {anomaly.error_code}) in your Twilio account.",
        "",
        f"- Current count: {anomaly.current_count}",
        f"- Historical average: {anomaly.baseline_avg:.1f}",
        f"- Increase: {anomaly.pct_increase:.1f}%",
        f"- Consecutive increasing runs: {anomaly.streak}",
        "",
    ]
    if ticket_url:
        lines.append(f"We created a follow-up ticket: {ticket_url}")
    else:
        lines.append("Our support team will contact you shortly.")
    lines += ["", "Regards,", "proactive-customer-care Monitoring Team"]
    return "\n".join(lines)


def notify_client(
    client: Client, anomaly: Anomaly, ticket_url: Optional[str], settings: Settings
) -> bool:
    if not settings.sendgrid_api_key:
        return False

    message = Mail(
        from_email=(settings.sendgrid_from_email, settings.sendgrid_from_name),
        to_emails=client.notify_email,
        subject=f"Alert: increase in errors {anomaly.error_code} in your account",
        plain_text_content=_build_email_body(client, anomaly, ticket_url),
    )

    sg = SendGridAPIClient(settings.sendgrid_api_key)
    response = sg.send(message)
    return 200 <= response.status_code < 300
