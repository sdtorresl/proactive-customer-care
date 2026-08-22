# proactive-customer-care — Detección de anomalías multi-cliente (Twilio)

Sistema que monitorea, para un conjunto de cuentas de Twilio (una por
cliente), si hay una **subida creciente y sostenida** de errores. Si detecta
una anomalía real (no un pico aislado):

1. Abre un ticket en **Zendesk** con el detalle del cliente, código de error,
   conteos y hora.
2. Notifica al cliente por correo vía **SendGrid**.
3. Guarda todo el histórico en **Postgres** para poder calcular líneas base
   confiables en corridas futuras.

No depende de ningún proveedor de IA: la clasificación de anomalías es
puramente estadística (comparación contra promedio histórico + racha de
corridas consecutivas al alza), por lo que el comportamiento es determinista,
reproducible y no consume cuota de ningún LLM.

## Estructura

```
app/
  config.py          Carga de variables de entorno y roster de clientes
  database.py         Acceso a Postgres (snapshots, incidentes, bitácora)
  twilio_source.py     Lectura real de Twilio Monitor Alerts por cliente
  anomaly.py           Reglas de detección de anomalías
  zendesk_client.py    Creación de tickets en Zendesk
  sendgrid_client.py   Notificación al cliente por correo
  main.py              Orquestador (entrypoint de la corrida)
db/
  schema.sql           Esquema de Postgres (se aplica automáticamente al iniciar)
clients.example.json  Roster de clientes de ejemplo (copiar a clients.json)
.env.example          Variables de entorno de ejemplo (copiar a .env)
docker-compose.yml     App + Postgres
Dockerfile
entrypoint.sh          Modo "once" (una corrida) o "loop" (bucle con intervalo)
```

## Puesta en marcha

1. Copia los archivos de ejemplo y complétalos con tus credenciales reales:
   ```bash
   cp .env.example .env
   cp clients.example.json clients.json
   ```
   En `clients.json` agrega una entrada por cada cliente/cuenta de Twilio que
   quieras monitorear (SID + auth token de esa subcuenta, correo de contacto).

2. Levanta todo con Docker:
   ```bash
   docker compose up --build
   ```
   Esto crea Postgres, aplica el esquema automáticamente y ejecuta una
   corrida (`RUN_MODE=once` por defecto).

## Cómo se ejecuta periódicamente

Hay dos formas, ambas soportadas por el mismo `entrypoint.sh`:

**Opción A — cron del host (recomendado para producción):**
```cron
# Cada hora
0 * * * * cd /ruta/al/proyecto && docker compose run --rm app
```

**Opción B — bucle dentro del contenedor**, sin depender de cron externo:
```bash
RUN_MODE=loop LOOP_INTERVAL_SECONDS=3600 docker compose up -d app
```

## Ajustar la sensibilidad de la detección

Todo se controla por variables de entorno (ver `.env.example`):

- `LOOKBACK_HOURS`: tamaño de la ventana de cada corrida.
- `BASELINE_WINDOW`: cuántas corridas históricas se usan como línea base.
- `ANOMALY_PCT_THRESHOLD`: % de incremento sobre la línea base para calificar.
- `ANOMALY_MIN_COUNT`: conteo mínimo absoluto (evita ruido de 1-2 errores).
- `ANOMALY_MIN_STREAK`: nº de corridas consecutivas al alza requeridas antes
  de escalar — esto es lo que distingue una **tendencia sostenida** de un
  pico aislado.
- `INCIDENT_COOLDOWN_HOURS`: evita abrir tickets duplicados para el mismo
  cliente/código de error en un período corto.

## Notas de producción

- Las credenciales de Twilio son **por cliente** (subcuentas), no una sola
  cuenta global — así se soporta el rango de clientes que mencionas.
- `clients.json` nunca se copia dentro de la imagen de Docker (se monta como
  volumen de solo lectura) para no hornear credenciales en el build.
- El histórico completo de conteos y de incidentes queda en Postgres, así que
  puedes construir dashboards o reportes aparte sin volver a golpear la API
  de Twilio.
