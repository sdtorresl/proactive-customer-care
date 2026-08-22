"""Retrieve real data from the Twilio API for a given client/account."""

import datetime
import logging
from collections import Counter
from typing import Tuple

from twilio.rest import Client as TwilioClient

from app.config import Client

log = logging.getLogger("proactive-customer-care.anomaly")


def get_period(lookback_hours: int) -> Tuple[datetime.datetime, datetime.datetime]:
    """Analysis window from `lookback_hours` hours ago until now (UTC)."""
    period_end = datetime.datetime.utcnow()
    period_start = period_end - datetime.timedelta(hours=lookback_hours)
    log.debug("Analysis period: %s -> %s", period_start, period_end)
    return period_start, period_end


def fetch_error_counts(client: Client, period_start: datetime.datetime,
                        period_end: datetime.datetime) -> Counter:
    """Query Twilio Monitor Alerts for the client account and return a
    Counter {error_code: count} within the given window."""
    log.info(
        "Querying Twilio Monitor Alerts for %s (%s -> %s)",
        client.twilio_account_sid, period_start, period_end,
    )
    twilio_client = TwilioClient(client.twilio_account_sid, client.twilio_auth_token)

    alerts = twilio_client.monitor.v1.alerts.list(
        start_date=period_start,
        end_date=period_end,
        limit=1000,
    )
    error_counts = Counter(alert.error_code for alert in alerts)
    log.info(
        "Retrieved %s distinct error codes for %s: %s",
        len(error_counts), client.twilio_account_sid, dict(error_counts),
    )
    return error_counts


def fetch_account_balance(client: Client) -> str:
    """Real client account balance (useful as context in the ticket/email)."""
    twilio_client = TwilioClient(client.twilio_account_sid, client.twilio_auth_token)
    try:
        balance = twilio_client.api.v2010.account.balance.fetch()
        formatted = f"${float(balance.balance):,.2f} {balance.currency}"
        log.info("Account balance for %s: %s", client.twilio_account_sid, formatted)
        return formatted
    except Exception:
        log.exception("Failed to retrieve account balance for %s", client.twilio_account_sid)
        return "Unavailable"
