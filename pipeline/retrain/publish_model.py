"""Публикация бинарника модели и фиксация нового окна обучения."""

import json
import logging
import os
from datetime import date
from pathlib import Path

from pipeline.db import advance_training_state, get_conn
from pipeline.settings import CURRENT_DATASET, MODELS_DIR

logger = logging.getLogger(__name__)


def publish_model(train_info: dict) -> str:
    """Reads: decision from compare_with_prod, staging model, new training window.
    Writes: model file and latest.txt (only if approved), metrics json, current.parquet, training_state.
    Rerun is safe: already moved files are not moved again, training_state gets the same values.
    """
    version = train_info["version"]
    staging_model = Path(train_info["staging_model"])
    final_model = MODELS_DIR / f"my_catboost_{version}.cbm"
    metrics_path = MODELS_DIR / f"my_catboost_{version}.metrics.json"

    approved = train_info["approved"]
    if approved:
        if staging_model.exists():
            os.replace(staging_model, final_model)
        elif not final_model.exists():
            raise FileNotFoundError(f"No model file for publishing: {staging_model}")
    else:
        staging_model.unlink(missing_ok=True)
        logger.info("Model %s not better than prod, not publish", version)

    metrics_path.write_text(
        json.dumps(
            {
                "version": version,
                "batch_month": train_info["batch_month"],
                "train_months": train_info["train_months"],
                "test_month": train_info["test_month"],
                "train_rows": train_info["train_rows"],
                "test_rows": train_info["test_rows"],
                "roc_auc": train_info["roc_auc"],
                "f1": train_info["f1"],
                "metric": train_info["metric"],
                "new_value": train_info["new_value"],
                "prod_version": train_info["prod_version"],
                "prod_value": train_info["prod_value"],
                "approved": approved,
                "reason": train_info["reason"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if approved:
        latest_tmp = MODELS_DIR / f".latest.{version}.txt"
        latest_tmp.write_text(version + "\n", encoding="utf-8")
        os.replace(latest_tmp, MODELS_DIR / "latest.txt")
        logger.info("Опубликована модель %s (%s)", version, final_model)

    pending_window = Path(train_info["dataset_path"])
    if pending_window.exists():
        os.replace(pending_window, CURRENT_DATASET)
        logger.info("Окно обучения обновлено: %s", CURRENT_DATASET)
    elif not CURRENT_DATASET.exists():
        raise FileNotFoundError(f"Нет нового окна обучения: {pending_window}")
    else:
        logger.info("Окно уже перенесено в %s, повторно не сдвигаем.", CURRENT_DATASET)

    batch_month = date.fromisoformat(train_info["batch_month"])
    conn = get_conn()
    try:
        advance_training_state(conn, batch_month)
    finally:
        conn.close()
    return version if approved else train_info["prod_version"]
