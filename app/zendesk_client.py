"""Creación de tickets en Zendesk vía su API REST cuando se detecta una anomalía."""

import datetime
from typing import Optional, Tuple

import requests

from app.anomaly import Anomaly
from app.config import Client, Settings

# Cache del access token OAuth en memoria del proceso: {subdomain: (token, expira_en_utc)}.
_token_cache = {}


def _get_access_token(settings: Settings) -> str:
    """Obtiene un access token OAuth vía client_credentials, reutilizándolo
    mientras no haya expirado."""
    cached = _token_cache.get(settings.zendesk_subdomain)
    if cached and cached[1] > datetime.datetime.utcnow():
        return cached[0]

    url = f"https://{settings.zendesk_subdomain}.zendesk.com/oauth/tokens"
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.zendesk_client_id,
        "client_secret": settings.zendesk_client_secret,
        "scope": settings.zendesk_oauth_scope,
    }
    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()

    token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    # Margen de seguridad de 60s para evitar usar un token a punto de expirar.
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=max(expires_in - 60, 0))
    _token_cache[settings.zendesk_subdomain] = (token, expires_at)
    return token


def _build_description(client: Client, anomaly: Anomaly, account_balance: str) -> str:
    return (
        f"Se detectó una tendencia creciente de errores en la cuenta de Twilio del cliente.\n\n"
        f"Cliente: {client.name} ({client.twilio_account_sid})\n"
        f"Twilio Account SID: {client.twilio_account_sid}\n"
        f"Código de error: {anomaly.error_code}\n"
        f"Conteo actual (última corrida): {anomaly.current_count}\n"
        f"Promedio histórico (línea base): {anomaly.baseline_avg:.1f}\n"
        f"Desviación estándar histórica: {anomaly.baseline_stddev:.1f}\n"
        f"Incremento sobre línea base: {anomaly.pct_increase:.1f}%\n"
        f"Corridas consecutivas con tendencia al alza: {anomaly.streak}\n"
        f"Balance de la cuenta al momento de la detección: {account_balance}\n"
        f"Hora de detección (UTC): {datetime.datetime.utcnow().isoformat()}\n\n"
        f"Este ticket fue generado automáticamente por el sistema de monitoreo "
        f"de anomalías de proactive-customer-care."
    )


def create_ticket(
    client: Client, anomaly: Anomaly, settings: Settings, account_balance: str
) -> Tuple[Optional[str], Optional[str]]:
    """Crea un ticket en Zendesk. Devuelve (ticket_id, ticket_url) o (None, None) si falla."""
    if not settings.zendesk_subdomain:
        return None, None

    url = f"https://{settings.zendesk_subdomain}.zendesk.com/api/v2/tickets.json"
    headers = {"Authorization": f"Bearer {_get_access_token(settings)}"}

    payload = {
        "ticket": {
            "subject": (
                f"[Monitoreo] Incremento de errores ({anomaly.error_code}) "
                f"en cuenta de {client.name}"
            ),
            "comment": {"body": _build_description(client, anomaly, account_balance)},
            "priority": settings.zendesk_ticket_priority,
            "tags": ["anomaly-detection", "twilio", "auto-generated", client.twilio_account_sid],
        }
    }
    if client.zendesk_organization_id:
        payload["ticket"]["organization_id"] = client.zendesk_organization_id

    response = requests.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()

    data = response.json()
    ticket_id = str(data["ticket"]["id"])
    ticket_url = f"https://{settings.zendesk_subdomain}.zendesk.com/agent/tickets/{ticket_id}"
    return ticket_id, ticket_url
