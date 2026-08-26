"""Anomaly detection based on simple statistical rules (no AI dependency).

For each client error code, the current run count is compared with a historical
baseline (average and standard deviation from the last N runs stored in Postgres).
It is marked as an anomaly when:

  1. The current count exceeds the absolute minimum threshold (avoids 1-2 error noise).
  2. The percentage increase over the historical average exceeds ANOMALY_PCT_THRESHOLD.
  3. There is a streak of at least ANOMALY_MIN_STREAK consecutive increasing runs,
      distinguishing a sustained trend from an isolated spike.
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
        # Without history, any new occurrence above the minimum is treated as a
        # 100% increase to avoid division by zero.
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
            "%s/%s: count %s is below minimum %s; skipping",
            client_id, error_code, current_count, settings.anomaly_min_count,
        )
        return None

    history = db.get_recent_counts(client_id, error_code, settings.baseline_window)

    if len(history) < 2:
        # There is not enough baseline data for reliable classification yet.
        log.debug(
            "%s/%s: insufficient history (%s runs); skipping",
            client_id, error_code, len(history),
        )
        return None

    baseline_avg = statistics.mean(history)
    baseline_stddev = statistics.pstdev(history) if len(history) > 1 else 0.0

    pct = _pct_increase(current_count, baseline_avg)
    if pct < settings.anomaly_pct_threshold:
        log.debug(
            "%s/%s: increase %.1f%% is below threshold %.1f%%; skipping",
            client_id, error_code, pct, settings.anomaly_pct_threshold,
        )
        return None

    streak = db.get_recent_streak_increasing(
        client_id, error_code, settings.anomaly_min_streak
    )
    if streak < settings.anomaly_min_streak:
        log.debug(
            "%s/%s: streak %s is below minimum %s; skipping",
            client_id, error_code, streak, settings.anomaly_min_streak,
        )
        return None

    log.info(
        "%s/%s: qualifying anomaly (current=%s baseline=%.1f increase=%.1f%% streak=%s)",
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
    log.debug("Evaluating %s error codes for %s", len(current_counts), client_id)
    anomalies = []
    for error_code, count in current_counts.items():
        anomaly = evaluate_error_code(db, settings, client_id, error_code, count)
        if anomaly is not None:
            anomalies.append(anomaly)
    log.info("%s: detected %s anomalies", client_id, len(anomalies))
    return anomalies
