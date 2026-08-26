#!/.venv/bin/python3
"""Test mode: create a Zendesk ticket directly without going through anomaly
detection, Twilio, or SendGrid. Useful for validating credentials and
connectivity with the Zendesk API in isolation.

Usage:
    python3 app/force_ticket.py
    docker compose run --rm app python3 app/force_ticket.py
"""

import sys

from app import config
from app.anomaly import Anomaly
from app.twilio_source import fetch_account_balance
from app.zendesk_client import create_ticket


def main() -> int:
    settings = config.load_settings()
    clients = config.load_clients(settings.clients_config_path)

    if not clients:
        print("No clients are configured in clients.json")
        return 1

    client = clients[0]

    anomaly = Anomaly(
        client_id=client.twilio_account_sid,
        error_code="TEST_TICKET",
        current_count=999,
        baseline_avg=100.0,
        baseline_stddev=10.0,
        pct_increase=899.0,
        streak=settings.anomaly_min_streak,
    )

    try:
        account_balance = fetch_account_balance(client)
    except Exception as e:
        print("Could not retrieve the Twilio balance; using N/A:", e)
        account_balance = "N/A"

    ticket_id, ticket_url = create_ticket(client, anomaly, settings, account_balance)

    if ticket_id is None:
        print("Ticket was not created (check ZENDESK_SUBDOMAIN and credentials).")
        return 1

    print(f"Ticket created: id={ticket_id} url={ticket_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
