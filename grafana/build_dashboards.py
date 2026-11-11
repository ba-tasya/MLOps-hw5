import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
PG = {"type": "grafana-postgresql-datasource", "uid": "postgres"}
SWITCH = {"name": "Model switch", "datasource": PROM, "enable": True, "iconColor": "orange", "step": "1s",
          "expr": "fraud_detector_model_switches_total unless fraud_detector_model_switches_total offset 30s",
          "titleFormat": "New model: {{version}}"}
HEATMAP = {"calculate": False, "color": {"scheme": "Oranges", "mode": "scheme"}}
FILTER = "us_state IN (${state:sqlstring}) AND merch IN (${merch:sqlstring})"


def prom(expr, legend="", fmt="time_series"):
    return {"datasource": PROM, "expr": expr, "legendFormat": legend, "format": fmt}


def sql(query, fmt="table"):
    return {"datasource": PG, "editorMode": "code", "format": fmt, "rawQuery": True, "rawSql": query}


def panel(kind, title, targets, x, y, w, h, ds=PROM, unit=None, options=None):
    for i, target in enumerate(targets):
        target["refId"] = "ABC"[i]
    return {"type": kind, "title": title, "datasource": ds, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": targets, "fieldConfig": {"defaults": {"unit": unit} if unit else {}, "overrides": []},
            "options": options or {}}


def variable(name, column):
    query = f"SELECT DISTINCT {column} FROM scores WHERE {column} IS NOT NULL ORDER BY 1"
    return {"name": name, "type": "query", "datasource": PG, "query": query, "definition": query,
            "multi": True, "includeAll": True, "refresh": 2, "current": {"text": ["All"], "value": ["$__all"]}}


def dashboard(uid, title, panels, annotations=(), variables=(), refresh="5s"):
    for i, p in enumerate(panels, start=1):
        p["id"] = i
    return {"uid": uid, "title": title, "editable": False, "schemaVersion": 39, "refresh": refresh,
            "time": {"from": "now-15m", "to": "now"}, "annotations": {"list": list(annotations)},
            "templating": {"list": list(variables)}, "panels": panels}


dashboards = {
    "processing": dashboard("fraud-processing", "1. Transaction processing", [
        panel("stat", "Processed transactions", [prom("fraud_detector_transactions_processed_total")], 0, 0, 6, 4),
        panel("stat", "Flagged as fraud", [prom("fraud_detector_fraud_flagged_total")], 6, 0, 6, 4),
        panel("stat", "Fraud share since start", [prom("fraud_detector_fraud_share")], 12, 0, 6, 4, unit="percentunit"),
        panel("stat", "Processing errors", [prom("fraud_detector_errors_total")], 18, 0, 6, 4),
        panel("timeseries", "Stream speed, transactions/s",
              [prom("rate(fraud_detector_transactions_processed_total[10s])", "TPS")], 0, 4, 12, 8, unit="reqps"),
        panel("timeseries", "Processing time of one transaction", [
            prom("histogram_quantile(0.95, sum(rate(fraud_detector_processing_seconds_bucket[30s])) by (le))", "p95"),
            prom("rate(fraud_detector_processing_seconds_sum[30s]) / rate(fraud_detector_processing_seconds_count[30s])",
                 "avg")], 12, 4, 12, 8, unit="s"),
        panel("timeseries", "Fraud share", [
            prom("sum(rate(fraud_detector_fraud_flagged_total[1m])) / "
                 "sum(rate(fraud_detector_transactions_processed_total[1m]))", "last 1 min"),
            prom("fraud_detector_fraud_share", "since start")], 0, 12, 12, 8, unit="percentunit"),
        panel("heatmap", "Score distribution over time",
              [prom("sum(increase(fraud_detector_score_bucket[10s])) by (le)", "{{le}}", "heatmap")],
              12, 12, 12, 8, options=HEATMAP),
        panel("timeseries", "Amount of transactions flagged as fraud, $ per minute",
              [prom("increase(fraud_detector_flagged_amount_total[1m])", "flagged amount")], 0, 20, 12, 8,
              unit="currencyUSD"),
        panel("table", "Scores and fraud share by model version (PostgreSQL)", [
            sql("SELECT model_version, count(*) AS scores, round(avg(fraud_flag)::numeric, 4) AS fraud_share, "
                "min(created_at) AS first_score, max(created_at) AS last_score FROM scores "
                "GROUP BY model_version ORDER BY min(created_at) DESC")], 12, 20, 12, 8, ds=PG),
    ], annotations=[SWITCH]),

    "writing": dashboard("fraud-writing", "2. Results writing", [
        panel("timeseries", "Write speed, scores/s",
              [prom("rate(scoring_writer_scores_written_total[10s])", "written/s")], 0, 0, 12, 8, unit="reqps"),
        panel("timeseries", "Write time to PostgreSQL", [
            prom("histogram_quantile(0.95, sum(rate(scoring_writer_write_seconds_bucket[30s])) by (le))", "p95"),
            prom("rate(scoring_writer_write_seconds_sum[30s]) / rate(scoring_writer_write_seconds_count[30s])", "avg")],
              12, 0, 12, 8, unit="s"),
        panel("stat", "Fraud written to DB", [prom("scoring_writer_fraud_written_total")], 0, 8, 6, 8),
        panel("timeseries", "Fraud written per minute",
              [prom("increase(scoring_writer_fraud_written_total[1m])", "fraud/min")], 6, 8, 6, 8),
        panel("heatmap", "Written score distribution over time",
              [prom("sum(increase(scoring_writer_score_bucket[10s])) by (le)", "{{le}}", "heatmap")],
              12, 8, 12, 8, options=HEATMAP),
    ], annotations=[SWITCH]),

    "system": dashboard("fraud-system", "3. System metrics", [
        panel("timeseries", "CPU usage",
              [prom('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[30s])))', "CPU")], 0, 0, 12, 8,
              unit="percent"),
        panel("timeseries", "Memory usage", [
            prom("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "used"),
            prom("node_memory_MemTotal_bytes", "total")], 12, 0, 12, 8, unit="bytes"),
        panel("timeseries", "Network traffic", [
            prom('sum(rate(node_network_receive_bytes_total{device!="lo"}[30s]))', "receive"),
            prom('sum(rate(node_network_transmit_bytes_total{device!="lo"}[30s]))', "transmit")],
              0, 8, 12, 8, unit="Bps"),
        panel("timeseries", "Disk I/O", [
            prom("sum(rate(node_disk_read_bytes_total[30s]))", "read"),
            prom("sum(rate(node_disk_written_bytes_total[30s]))", "write")], 12, 8, 12, 8, unit="Bps"),
    ]),

    "business": dashboard("fraud-business", "4. Fraud business analytics", [
        panel("histogram", "Score density",
              [sql("SELECT score FROM scores WHERE $__timeFilter(created_at) AND " + FILTER)],
              0, 0, 12, 9, ds=PG, options={"bucketSize": 0.02}),
        panel("timeseries", "TPS of filtered transactions", [
            sql("SELECT $__timeGroupAlias(created_at, '10s'), count(*) / 10.0 AS tps FROM scores "
                "WHERE $__timeFilter(created_at) AND " + FILTER + " GROUP BY 1 ORDER BY 1", "time_series")],
              12, 0, 12, 9, ds=PG, unit="reqps"),
        panel("barchart", "Fraud share by category (last 1000 transactions)", [
            sql("SELECT cat_id, avg(fraud_flag) AS fraud_share FROM "
                "(SELECT cat_id, fraud_flag FROM scores ORDER BY id DESC LIMIT 1000) AS last_scores "
                "GROUP BY cat_id ORDER BY fraud_share DESC")],
              0, 9, 12, 9, ds=PG, unit="percentunit", options={"xField": "cat_id", "orientation": "horizontal"}),
        panel("barchart", "Amount flagged as fraud by state, $ (potential loss)", [
            sql("SELECT us_state, sum(amount) AS flagged_amount FROM scores "
                "WHERE $__timeFilter(created_at) AND fraud_flag = 1 AND " + FILTER + " "
                "GROUP BY us_state ORDER BY flagged_amount DESC LIMIT 15")],
              12, 9, 12, 9, ds=PG, unit="currencyUSD", options={"xField": "us_state", "orientation": "horizontal"}),
    ], variables=[variable("state", "us_state"), variable("merch", "merch")], refresh="10s"),
}

out = Path(__file__).parent / "dashboards"
out.mkdir(exist_ok=True)
for name, d in dashboards.items():
    (out / f"{name}.json").write_text(json.dumps(d, indent=2) + "\n")
    print(f"grafana/dashboards/{name}.json: {len(d['panels'])} panels")