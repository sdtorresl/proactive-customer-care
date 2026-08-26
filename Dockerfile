FROM python:3.11-slim

WORKDIR /app

# Without this, the root CA certificate bundle can become outdated and HTTPS
# calls (for example, to Zendesk) fail with SSLCertVerificationError.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY db/ ./db/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# clients.json is mounted as a volume in docker-compose.yml (it is not baked into
# the image because it contains per-client Twilio credentials).

ENTRYPOINT ["./entrypoint.sh"]
