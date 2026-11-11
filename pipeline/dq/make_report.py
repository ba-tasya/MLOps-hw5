"""HTML report with data quality check results."""

import html
import logging
import os

from pipeline.settings import DQ_REPORTS_DIR

logger = logging.getLogger(__name__)


def make_dq_report(dq_info: dict) -> str:
    """Reads: check results from run_dq_checks.
    Writes: dq_report_<time>.html to DQ_REPORTS_DIR.
    Rerun is safe: the same file is overwritten with the same results.
    """
    DQ_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    results = dq_info["results"]
    passed = sum(result["passed"] for result in results)

    rows = []
    for result in results:
        color = "#17e04666" if result["passed"] else "#ec15276d"
        status = "OK" if result["passed"] else "FAIL"
        rows.append(
            f'<tr style="background:{color}">'
            f"<td>{html.escape(result['name'])}</td>"
            f"<td>{html.escape(result['description'])}</td>"
            f"<td>{result['violations']}</td>"
            f"<td>{status}</td></tr>"
        )

    page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>DQ report {dq_info['checked_at']}</title>
<style>
body {{ font-family: sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #999; padding: 6px 10px; text-align: left; }}
</style>
</head>
<body>
<h1>Data Quality: labeled_transactions</h1>
<p>Checked at (UTC): {dq_info['checked_at']}<br>
Rows: {dq_info['total_rows']}<br>
Passed: {passed} of {len(results)}</p>
<table>
<tr><th>Rule</th><th>Description</th><th>Violations</th><th>Status</th></tr>
{''.join(rows)}
</table>
</body>
</html>
"""

    report_path = DQ_REPORTS_DIR / f"dq_report_{dq_info['checked_at']}.html"
    tmp_path = DQ_REPORTS_DIR / f".{report_path.name}.tmp"
    tmp_path.write_text(page, encoding="utf-8")
    os.replace(tmp_path, report_path)
    logger.info("DQ report saved: %s (%s of %s passed)", report_path, passed, len(results))
    return str(report_path)