#!/usr/bin/env python3
"""Main orchestrator.

Designed to run periodically (cron / docker-compose run / external scheduler).
On each run:

  1. Loads the client list (Twilio accounts) from clients.json.
  2. For each client, retrieves real errors from Twilio Monitor Alerts
      for the configured time window (LOOKBACK_HOURS).
  3. Stores the snapshot in Postgres (historical baseline data).
  4. Evaluates whether there is a sustained increasing error trend.
  5. If there is an anomaly without a recent ticket for the same client/error
      (cooldown), creates a Zendesk ticket and notifies the client through SendGrid.
"""

import argparse
import datetime
import logging
import os
import sys

from app import config
from app.anomaly import Anomaly, detect_anomalies
from app.database import Database
from app.sendgrid_client import notify_client
from app.twilio_source import fetch_account_balance, fetch_error_counts, get_period
from app.zendesk_client import create_ticket

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("proactive-customer-care.anomaly")

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def process_client(db: Database, settings: config.Settings, client: config.Client,
                    period_start: datetime.datetime, period_end: datetime.datetime) -> int:
    log.info("Processing client %s (%s)", client.name, client.twilio_account_sid)

    try:
        error_counts = fetch_error_counts(client, period_start, period_end)
    except Exception:
        log.exception("Failed to retrieve Twilio alerts for %s", client.twilio_account_sid)
        return 0

    # Store a snapshot of every error code observed in this run.
    for error_code, count in error_counts.items():
        db.insert_snapshot(client.twilio_account_sid, error_code, period_start, period_end, count)

    if not error_counts:
        log.info("No errors in the analyzed window for %s", client.twilio_account_sid)
        return 0

    anomalies = detect_anomalies(db, settings, client.twilio_account_sid, dict(error_counts))
    if not anomalies:
        log.info("No anomalies for %s", client.twilio_account_sid)
        return 0

    anomalies_escalated = 0
    for anomaly in anomalies:
        if db.has_recent_incident(
            client.twilio_account_sid, anomaly.error_code, settings.incident_cooldown_hours
        ):
            log.info(
                "Anomaly in %s/%s already has a recent incident; skipping (cooldown).",
                client.twilio_account_sid, anomaly.error_code,
            )
            continue

        log.warning(
            "ANOMALY detected: client=%s error=%s current=%s baseline=%.1f increase=%.1f%%",
            client.twilio_account_sid, anomaly.error_code, anomaly.current_count,
            anomaly.baseline_avg, anomaly.pct_increase,
        )

        account_balance = fetch_account_balance(client)

        ticket_id, ticket_url = None, None
        try:
            ticket_id, ticket_url = create_ticket(client, anomaly, settings, account_balance)
        except Exception:
            log.exception("Failed to create Zendesk ticket for %s", client.twilio_account_sid)

        notified_at = None
        try:
            if notify_client(client, anomaly, ticket_url, settings):
                notified_at = datetime.datetime.utcnow()
        except Exception:
            log.exception("Failed to notify through SendGrid for %s", client.twilio_account_sid)

        db.insert_incident(
            client_id=client.twilio_account_sid,
            error_code=anomaly.error_code,
            current_count=anomaly.current_count,
            baseline_avg=anomaly.baseline_avg,
            baseline_stddev=anomaly.baseline_stddev,
            pct_increase=anomaly.pct_increase,
            streak=anomaly.streak,
            zendesk_ticket_id=ticket_id,
            zendesk_ticket_url=ticket_url,
            notified_at=notified_at,
        )
        anomalies_escalated += 1

    return anomalies_escalated


def force_escalation(db: Database, settings: config.Settings, client: config.Client) -> int:
    """Test mode: force an escalation (ticket + notification) for a client
    without relying on real Twilio data or the incident cooldown. Useful for
    end-to-end validation of the Zendesk and SendGrid integrations."""
    log.warning("TEST MODE: forcing escalation for %s", client.twilio_account_sid)

    anomaly = Anomaly(
        client_id=client.twilio_account_sid,
        error_code="TEST_ESCALATION",
        current_count=999,
        baseline_avg=100.0,
        baseline_stddev=10.0,
        pct_increase=899.0,
        streak=settings.anomaly_min_streak,
    )

    try:
        account_balance = fetch_account_balance(client)
    except Exception:
        log.exception("Failed to retrieve account balance for %s", client.twilio_account_sid)
        account_balance = "N/A"

    ticket_id, ticket_url = None, None
    try:
        ticket_id, ticket_url = create_ticket(client, anomaly, settings, account_balance)
    except Exception:
        log.exception("Failed to create Zendesk ticket for %s", client.twilio_account_sid)

    notified_at = None
    try:
        if notify_client(client, anomaly, ticket_url, settings):
            notified_at = datetime.datetime.utcnow()
    except Exception:
        log.exception("Failed to notify through SendGrid for %s", client.twilio_account_sid)

    db.insert_incident(
        client_id=client.twilio_account_sid,
        error_code=anomaly.error_code,
        current_count=anomaly.current_count,
        baseline_avg=anomaly.baseline_avg,
        baseline_stddev=anomaly.baseline_stddev,
        pct_increase=anomaly.pct_increase,
        streak=anomaly.streak,
        zendesk_ticket_id=ticket_id,
        zendesk_ticket_url=ticket_url,
        notified_at=notified_at,
    )
    return 1


def run(force: bool = False) -> int:
    settings = config.load_settings()
    clients = config.load_clients(settings.clients_config_path)

    db = Database(settings.database_url)
    db.ensure_schema(SCHEMA_PATH)

    run_id = db.start_run()
    period_start, period_end = get_period(settings.lookback_hours)

    total_anomalies = 0
    status = "ok"
    error_message = None

    try:
        for client in clients:
            if force:
                total_anomalies += force_escalation(db, settings, client)
            else:
                total_anomalies += process_client(db, settings, client, period_start, period_end)
    except Exception as exc:
        status = "error"
        error_message = str(exc)
        log.exception("Run aborted due to an unexpected error")
    finally:
        db.finish_run(run_id, len(clients), total_anomalies, status, error_message)

    log.info(
        "Run finished: %s clients processed, %s anomalies escalated",
        len(clients), total_anomalies,
    )
    return 0 if status == "ok" else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="proactive-customer-care orchestrator")
    parser.add_argument(
        "--force-escalation",
        action="store_true",
        default=os.environ.get("FORCE_ESCALATION", "").lower() in ("1", "true", "yes"),
        help="Test mode: force ticket creation and notification for every client.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(run(force=args.force_escalation))
