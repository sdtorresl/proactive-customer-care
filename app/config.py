"""Load configuration from environment variables and the client roster."""

import json
import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Client:
    name: str
    twilio_account_sid: str
    twilio_auth_token: str
    notify_email: str
    zendesk_organization_id: Optional[str] = None


@dataclass(frozen=True)
class Settings:
    database_url: str

    zendesk_subdomain: str
    zendesk_client_id: str
    zendesk_client_secret: str
    zendesk_oauth_scope: str
    zendesk_ticket_priority: str

    sendgrid_api_key: str
    sendgrid_from_email: str
    sendgrid_from_name: str

    lookback_hours: int
    baseline_window: int
    anomaly_pct_threshold: float
    anomaly_min_count: int
    anomaly_min_streak: int
    incident_cooldown_hours: int

    clients_config_path: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        zendesk_subdomain=os.environ.get("ZENDESK_SUBDOMAIN", ""),
        zendesk_client_id=os.environ.get("ZENDESK_CLIENT_ID", ""),
        zendesk_client_secret=os.environ.get("ZENDESK_CLIENT_SECRET", ""),
        zendesk_oauth_scope=os.environ.get("ZENDESK_OAUTH_SCOPE", "tickets:write"),
        zendesk_ticket_priority=os.environ.get("ZENDESK_TICKET_PRIORITY", "high"),
        sendgrid_api_key=os.environ.get("SENDGRID_API_KEY", ""),
        sendgrid_from_email=os.environ.get("SENDGRID_FROM_EMAIL", "alerts@proactive-customer-care.com"),
        sendgrid_from_name=os.environ.get("SENDGRID_FROM_NAME", "proactive-customer-care Monitoring"),
        lookback_hours=_env_int("LOOKBACK_HOURS", 1),
        baseline_window=_env_int("BASELINE_WINDOW", 24),
        anomaly_pct_threshold=_env_float("ANOMALY_PCT_THRESHOLD", 50),
        anomaly_min_count=_env_int("ANOMALY_MIN_COUNT", 5),
        anomaly_min_streak=_env_int("ANOMALY_MIN_STREAK", 2),
        incident_cooldown_hours=_env_int("INCIDENT_COOLDOWN_HOURS", 12),
        clients_config_path=os.environ.get("CLIENTS_CONFIG_PATH", "/app/clients.json"),
    )


def load_clients(path: str) -> List[Client]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Client file not found at '{path}'. "
            "Copy clients.example.json to clients.json and complete it."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    clients = []
    for entry in raw:
        clients.append(
            Client(
                name=entry["name"],
                twilio_account_sid=entry["twilio_account_sid"],
                twilio_auth_token=entry["twilio_auth_token"],
                notify_email=entry["notify_email"],
                zendesk_organization_id=entry.get("zendesk_organization_id"),
            )
        )
    return clients
