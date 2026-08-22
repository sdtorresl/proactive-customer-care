"""Postgres access layer for error snapshots, incidents, and run logs."""

import datetime
from contextlib import contextmanager
from typing import Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras


class Database:
    def __init__(self, database_url: str):
        self._dsn = database_url

    @contextmanager
    def _connect(self):
        conn = psycopg2.connect(self._dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self, schema_sql_path: str) -> None:
        with open(schema_sql_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)

    # ---------------------------------------------------------------
    # Snapshots (error count per run)
    # ---------------------------------------------------------------
    def insert_snapshot(
        self,
        client_id: str,
        error_code: str,
        period_start: datetime.datetime,
        period_end: datetime.datetime,
        count: int,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alert_snapshots
                        (client_id, error_code, period_start, period_end, count)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (client_id, error_code, period_start, period_end, count),
                )

    def get_recent_counts(
        self, client_id: str, error_code: str, limit: int
    ) -> List[int]:
        """Return the latest `limit` historical counts (excluding the current run),
        ordered from newest to oldest."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count FROM alert_snapshots
                    WHERE client_id = %s AND error_code = %s
                    ORDER BY period_start DESC
                    LIMIT %s
                    """,
                    (client_id, error_code, limit),
                )
                return [row[0] for row in cur.fetchall()]

    def get_recent_streak_increasing(
        self, client_id: str, error_code: str, max_streak: int
    ) -> int:
        """Count how many consecutive recent runs show a count greater than or
        equal to the previous one. Used to distinguish a sustained increase
        from an isolated spike."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count FROM alert_snapshots
                    WHERE client_id = %s AND error_code = %s
                    ORDER BY period_start DESC
                    LIMIT %s
                    """,
                    (client_id, error_code, max_streak + 1),
                )
                counts = [row[0] for row in cur.fetchall()]

        streak = 0
        for i in range(len(counts) - 1):
            if counts[i] >= counts[i + 1]:
                streak += 1
            else:
                break
        return streak

    # ---------------------------------------------------------------
    # Incidents (detected and escalated anomalies)
    # ---------------------------------------------------------------
    def has_recent_incident(
        self, client_id: str, error_code: str, cooldown_hours: int
    ) -> bool:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=cooldown_hours)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM incidents
                    WHERE client_id = %s AND error_code = %s AND detected_at >= %s
                    LIMIT 1
                    """,
                    (client_id, error_code, cutoff),
                )
                return cur.fetchone() is not None

    def insert_incident(
        self,
        client_id: str,
        error_code: str,
        current_count: int,
        baseline_avg: float,
        baseline_stddev: float,
        pct_increase: float,
        streak: int,
        zendesk_ticket_id: Optional[str] = None,
        zendesk_ticket_url: Optional[str] = None,
        notified_at: Optional[datetime.datetime] = None,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO incidents
                        (client_id, error_code, current_count, baseline_avg,
                         baseline_stddev, pct_increase, streak,
                         zendesk_ticket_id, zendesk_ticket_url, notified_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        client_id,
                        error_code,
                        current_count,
                        baseline_avg,
                        baseline_stddev,
                        pct_increase,
                        streak,
                        zendesk_ticket_id,
                        zendesk_ticket_url,
                        notified_at,
                    ),
                )
                return cur.fetchone()[0]

    # ---------------------------------------------------------------
    # Run log (for system observability)
    # ---------------------------------------------------------------
    def start_run(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO run_log (status) VALUES ('running') RETURNING id"
                )
                return cur.fetchone()[0]

    def finish_run(
        self, run_id: int, clients_processed: int, anomalies_found: int,
        status: str = "ok", error_message: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE run_log
                    SET finished_at = now(), clients_processed = %s,
                        anomalies_found = %s, status = %s, error_message = %s
                    WHERE id = %s
                    """,
                    (clients_processed, anomalies_found, status, error_message, run_id),
                )
