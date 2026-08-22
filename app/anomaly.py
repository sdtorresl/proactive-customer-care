"""Detección de anomalías basada en reglas estadísticas simples (sin dependencia de IA).

Para cada código de error de un cliente, se compara el conteo de la corrida
actual contra una línea base histórica (promedio y desviación estándar de las
últimas N corridas almacenadas en Postgres). Se marca como anomalía cuando:

  1. El conteo actual supera el umbral mínimo absoluto (evita ruido de 1-2 errores).
  2. El incremento porcentual sobre el promedio histórico supera ANOMALY_PCT_THRESHOLD.
  3. Existe una racha de al menos ANOMALY_MIN_STREAK corridas consecutivas al alza,
     para distinguir una tendencia sostenida de un pico aislado.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import List, Optional

from app.config import Settings
from app.database import Database

log = logging.getLogger("proactive-customer-care.anomaly")


@dataclass
class Anomaly:
    client_id: str
    error_code: str
    current_count: int
    baseline_avg: float
    baseline_stddev: float
    pct_increase: float
    streak: int


def _pct_increase(current: int, baseline_avg: float) -> float:
    if baseline_avg <= 0:
        # Sin historial previo: cualquier ocurrencia nueva y por encima del mínimo
        # se trata como 100% de incremento para no dividir por cero.
        return 100.0 if current > 0 else 0.0
    return ((current - baseline_avg) / baseline_avg) * 100.0


def evaluate_error_code(
    db: Database,
    settings: Settings,
    client_id: str,
    error_code: str,
    current_count: int,
) -> Optional[Anomaly]:
    if current_count < settings.anomaly_min_count:
        log.debug(
            "%s/%s: conteo %s por debajo del mínimo %s, se descarta",
            client_id, error_code, current_count, settings.anomaly_min_count,
        )
        return None

    history = db.get_recent_counts(client_id, error_code, settings.baseline_window)

    if len(history) < 2:
        # No hay suficiente línea base todavía para calificar de forma confiable.
        log.debug(
            "%s/%s: histórico insuficiente (%s corridas), se descarta",
            client_id, error_code, len(history),
        )
        return None

    baseline_avg = statistics.mean(history)
    baseline_stddev = statistics.pstdev(history) if len(history) > 1 else 0.0

    pct = _pct_increase(current_count, baseline_avg)
    if pct < settings.anomaly_pct_threshold:
        log.debug(
            "%s/%s: incremento %.1f%% por debajo del umbral %.1f%%, se descarta",
            client_id, error_code, pct, settings.anomaly_pct_threshold,
        )
        return None

    streak = db.get_recent_streak_increasing(
        client_id, error_code, settings.anomaly_min_streak
    )
    if streak < settings.anomaly_min_streak:
        log.debug(
            "%s/%s: racha %s por debajo del mínimo %s, se descarta",
            client_id, error_code, streak, settings.anomaly_min_streak,
        )
        return None

    log.info(
        "%s/%s: anomalía calificada (actual=%s baseline=%.1f incremento=%.1f%% racha=%s)",
        client_id, error_code, current_count, baseline_avg, pct, streak,
    )
    return Anomaly(
        client_id=client_id,
        error_code=error_code,
        current_count=current_count,
        baseline_avg=baseline_avg,
        baseline_stddev=baseline_stddev,
        pct_increase=pct,
        streak=streak,
    )


def detect_anomalies(
    db: Database,
    settings: Settings,
    client_id: str,
    current_counts: dict,
) -> List[Anomaly]:
    log.debug("Evaluando %s códigos de error para %s", len(current_counts), client_id)
    anomalies = []
    for error_code, count in current_counts.items():
        anomaly = evaluate_error_code(db, settings, client_id, error_code, count)
        if anomaly is not None:
            anomalies.append(anomaly)
    log.info("%s: %s anomalías detectadas", client_id, len(anomalies))
    return anomalies
