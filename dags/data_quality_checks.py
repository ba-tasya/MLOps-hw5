"""DAG for data quality checks. 

Only builds the task graph, logic is in pipeline.dq."""

from datetime import datetime, timedelta

from airflow.decorators import dag, task

from pipeline.dq.make_report import make_dq_report
from pipeline.dq.run_checks import run_dq_checks


@dag(
    dag_id="data_quality_check",
    description="Checks labeled_transactions every 5 minutes and saves an HTML report",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=15),
    default_args={"retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["mlops", "dq"],
    doc_md="""
### Data quality check

1. Count violations of 6 DQ rules in `labeled_transactions`.
2. Save the results as an HTML report to `/opt/airflow/dq_reports`.
    """,
)
def data_quality_check():
    """Task graph: run_dq_checks -> make_dq_report."""
    results = task(run_dq_checks, task_id="run_dq_checks")()
    task(make_dq_report, task_id="make_dq_report")(results)


data_quality_check()