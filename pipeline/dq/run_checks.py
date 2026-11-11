"""Data quality checks for labeled_transactions."""

import logging
from datetime import datetime, timezone

from pipeline.db import get_conn
from pipeline.settings import HISTORY_YEARS

logger = logging.getLogger(__name__)

DQ_RULES = [
    {
        "name": "not_null_key_columns",
        "description": "No nulls in transaction_time, amount, cat_id, us_state, target",
        "sql": """
            SELECT count(*) FROM labeled_transactions
            WHERE transaction_time IS NULL OR amount IS NULL OR cat_id IS NULL
               OR us_state IS NULL OR target IS NULL
        """,
    },
    {
        "name": "positive_amount",
        "description": "amount is > 0",
        "sql": "SELECT count(*) FROM labeled_transactions WHERE amount <= 0",
    },
    {
        "name": "binary_target",
        "description": "target is only 0 or 1",
        "sql": "SELECT count(*) FROM labeled_transactions WHERE target NOT IN (0, 1)",
    },
    {
        "name": "valid_coordinates",
        "description": "Latitude in [-90, 90], longitude in [-180, 180] for client and merchant",
        "sql": """
            SELECT count(*) FROM labeled_transactions
            WHERE lat NOT BETWEEN -90 AND 90 OR lon NOT BETWEEN -180 AND 180
               OR merchant_lat NOT BETWEEN -90 AND 90 OR merchant_lon NOT BETWEEN -180 AND 180
        """,
    },
    {
        "name": "valid_gender",
        "description": "gender is not null and is M or F",
        "sql": "SELECT count(*) FROM labeled_transactions WHERE gender IS NULL OR gender NOT IN ('M', 'F')",
    },
    {
        "name": "history_depth",
        "description": f"No rows older than {HISTORY_YEARS} years from the newest month",
        "sql": """
            SELECT count(*) FROM labeled_transactions
            WHERE transaction_time < (
                SELECT date_trunc('month', max(transaction_time)) FROM labeled_transactions
            ) - make_interval(years => %s)
        """,
        "params": (HISTORY_YEARS,),
    },
]


def run_dq_checks() -> dict:
    """Reads: labeled_transactions table (SELECT only).
    Writes: nothing, returns check results.
    Rerun is safe: data is not changed, results are just recalculated.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM labeled_transactions")
            total_rows = cur.fetchone()[0]
            results = []
            for rule in DQ_RULES:
                cur.execute(rule["sql"], rule.get("params"))
                violations = int(cur.fetchone()[0])
                results.append({
                    "name": rule["name"],
                    "description": rule["description"],
                    "violations": violations,
                    "passed": violations == 0,
                })
                logger.info("Rule %s: %s violations", rule["name"], violations)
    finally:
        conn.close()

    return {
        "checked_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"),
        "total_rows": int(total_rows),
        "results": results,
    }