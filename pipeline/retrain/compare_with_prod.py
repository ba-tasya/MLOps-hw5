import logging

import pandas as pd

from pipeline.retrain.fit_catboost import prepare_features
from pipeline.settings import MODELS_DIR, SPLITS_DIR
from sklearn.metrics import f1_score, roc_auc_score
from catboost import CatBoostClassifier

logger = logging.getLogger(__name__)

BOOTSTRAP_VERSION = "initial"


def evaluate(model, test):
    """Reads: model and test dataframe.
    Writes: nothing, returns metric name and value.
    Rerun is safe: only calculates the metric.
    """
    x_test, y_test = prepare_features(test)
    proba = model.predict_proba(x_test[list(model.feature_names_)])[:, 1]
    if y_test.nunique() < 2:
        return "f1", float(f1_score(y_test, (proba > 0.5).astype(int), zero_division=0))

    return "roc_auc", float(roc_auc_score(y_test, proba))


def compare_with_prod(train_info):
    """Reads: new model, test_proc.parquet and prod model from latest.txt.
    Writes: nothing, returns the publish decision.
    Rerun is safe: no files are changed, the decision is the same.
    """
    test = pd.read_parquet(SPLITS_DIR / "test_proc.parquet")

    new_model = CatBoostClassifier()
    new_model.load_model(train_info["staging_model"])
    metric, new_value = evaluate(new_model, test)

    latest_file = MODELS_DIR / "latest.txt"
    prod_version = latest_file.read_text(encoding="utf-8").strip() if latest_file.exists() else ""
    prod_path = MODELS_DIR / f"my_catboost_{prod_version}.cbm"

    decision = dict(train_info)
    decision.update(metric=metric, new_value=new_value, prod_version=prod_version or None)

    if not prod_version or prod_version == BOOTSTRAP_VERSION or not prod_path.exists():
        decision.update(
            prod_value=None,
            approved=True,
            reason="changing without comparison",
        )
    else:
        prod_model = CatBoostClassifier()
        prod_model.load_model(str(prod_path))
        _, prod_value = evaluate(prod_model, test)
        decision.update(
            prod_value=prod_value,
            approved=new_value >= prod_value,
            reason=f"{metric}: new model {new_value:.4f}, prod {prod_value:.4f}",
        )

    logger.info(
        "Решение: %s. %s",
        "YES" if decision["approved"] else "NO",
        decision["reason"],
    )

    return decision