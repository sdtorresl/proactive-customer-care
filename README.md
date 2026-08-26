# proactive-customer-care - Multi-client anomaly detection (Twilio)

System that monitors a set of Twilio accounts (one per client) for a
a **sustained increase** in errors. If it detects a real anomaly (not an isolated
spike):

1. Opens a **Zendesk** ticket with client details, error code, counts, and time.
2. Notifies the client by email through **SendGrid**.
3. Stores the complete history in **Postgres** to calculate reliable baselines
  in future runs.

It does not depend on any AI provider: anomaly classification is purely
statistical (comparison against the historical average plus consecutive
increasing runs), so behavior is deterministic, reproducible, and consumes no
LLM quota.

## Structure

```
app/
  config.py            Load environment variables and client roster
  database.py          Postgres access (snapshots, incidents, run log)
  twilio_source.py     Read Twilio Monitor Alerts for each client
  anomaly.py           Anomaly detection rules
  zendesk_client.py    Create Zendesk tickets
  sendgrid_client.py   Notify clients by email
  main.py              Run orchestrator (run entrypoint)
db/
  schema.sql           Postgres schema (applied automatically on startup)
clients.example.json  Example client roster (copy to clients.json)
.env.example          Example environment variables (copy to .env)
docker-compose.yml     App + Postgres
Dockerfile
entrypoint.sh          Modo "once" (una corrida) o "loop" (bucle con intervalo)
```

## Getting started

1. Copy the example files and fill them with your real credentials:
   ```bash
   cp .env.example .env
   cp clients.example.json clients.json
   ```
  In `clients.json`, add one entry for each client/Twilio account you want to
  monitor (the subaccount SID and auth token, plus a contact email).

2. Start everything with Docker:
   ```bash
   docker compose up --build
   ```
  This creates Postgres, applies the schema automatically, and runs one
  cycle (`RUN_MODE=once` by default).

## Periodic execution

There are two options, both supported by the same `entrypoint.sh`:

**Option A - host cron (recommended for production):**
```cron
# Every hour
0 * * * * cd /ruta/al/proyecto && docker compose run --rm app
```

**Option B - loop inside the container**, without relying on external cron:
```bash
RUN_MODE=loop LOOP_INTERVAL_SECONDS=3600 docker compose up -d app
```

## Adjust detection sensitivity

Everything is controlled through environment variables (see `.env.example`):

- `LOOKBACK_HOURS`: size of the window for each run.
- `BASELINE_WINDOW`: number of historical runs used as the baseline.
- `ANOMALY_PCT_THRESHOLD`: percentage increase over the baseline required to qualify.
- `ANOMALY_MIN_COUNT`: absolute minimum count (avoids 1-2 error noise).
- `ANOMALY_MIN_STREAK`: number of consecutive increasing runs required before
  escalation, distinguishing a **sustained trend** from an isolated spike.
- `INCIDENT_COOLDOWN_HOURS`: prevents duplicate tickets for the same client/error
  within a short period.

## Production notes

- Twilio credentials are **per client** (subaccounts), rather than one global
  account, so the application can support multiple clients.
- `clients.json` is never copied into the Docker image (it is mounted as a
  read-only volume) to avoid baking credentials into the build.
- The complete history of counts and incidents remains in Postgres, so you can
  build dashboards or reports separately without calling the Twilio API again.
