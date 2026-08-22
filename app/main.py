#!/usr/bin/env python3
"""Orquestador principal.

Diseñado para ejecutarse periódicamente (cron / docker-compose run / scheduler
externo). En cada corrida:

  1. Carga la lista de clientes (cuentas de Twilio) desde clients.json.
  2. Para cada cliente, obtiene los errores reales de Twilio Monitor Alerts
     de la ventana de tiempo configurada (LOOKBACK_HOURS).
  3. Guarda el snapshot en Postgres (histórico para la línea base).
  4. Evalúa si hay una subida creciente y sostenida de errores.
  5. Si hay anomalía y no hay un ticket reciente para ese mismo cliente/código
     (cooldown), crea un ticket en Zendesk y notifica al cliente por SendGrid.
"""

import datetime
import logging
import os
import sys

from app import config
from app.anomaly import detect_anomalies
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
    log.info("Procesando cliente %s (%s)", client.name, client.twilio_account_sid)

    try:
        error_counts = fetch_error_counts(client, period_start, period_end)
    except Exception:
        log.exception("Fallo al obtener alertas de Twilio para %s", client.twilio_account_sid)
        return 0

    # Guardar snapshot de todos los códigos de error observados en esta corrida.
    for error_code, count in error_counts.items():
        db.insert_snapshot(client.twilio_account_sid, error_code, period_start, period_end, count)

    if not error_counts:
        log.info("Sin errores en la ventana analizada para %s", client.twilio_account_sid)
        return 0

    anomalies = detect_anomalies(db, settings, client.twilio_account_sid, dict(error_counts))
    if not anomalies:
        log.info("Sin anomalías para %s", client.twilio_account_sid)
        return 0

    anomalies_escalated = 0
    for anomaly in anomalies:
        if db.has_recent_incident(
            client.twilio_account_sid, anomaly.error_code, settings.incident_cooldown_hours
        ):
            log.info(
                "Anomalía en %s/%s ya tiene un incidente reciente, se omite (cooldown).",
                client.twilio_account_sid, anomaly.error_code,
            )
            continue

        log.warning(
            "ANOMALÍA detectada: cliente=%s error=%s actual=%s baseline=%.1f incremento=%.1f%%",
            client.twilio_account_sid, anomaly.error_code, anomaly.current_count,
            anomaly.baseline_avg, anomaly.pct_increase,
        )

        account_balance = fetch_account_balance(client)

        ticket_id, ticket_url = None, None
        try:
            ticket_id, ticket_url = create_ticket(client, anomaly, settings, account_balance)
        except Exception:
            log.exception("Fallo al crear ticket en Zendesk para %s", client.twilio_account_sid)

        notified_at = None
        try:
            if notify_client(client, anomaly, ticket_url, settings):
                notified_at = datetime.datetime.utcnow()
        except Exception:
            log.exception("Fallo al notificar por SendGrid a %s", client.twilio_account_sid)

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


def run() -> int:
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
            total_anomalies += process_client(db, settings, client, period_start, period_end)
    except Exception as exc:
        status = "error"
        error_message = str(exc)
        log.exception("Corrida abortada por error inesperado")
    finally:
        db.finish_run(run_id, len(clients), total_anomalies, status, error_message)

    log.info(
        "Corrida finalizada: %s clientes procesados, %s anomalías escaladas",
        len(clients), total_anomalies,
    )
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(run())
