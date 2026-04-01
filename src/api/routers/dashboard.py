"""Local dev dashboard — lightweight status page for LocalStack resources and DB state.

Serves an HTML page at /dashboard with auto-refresh showing:
- Kinesis streams and shard status
- SQS queues with message counts
- DB table row counts
- Latest weather readings
- Alert rules and rule groups count
"""

import base64
import json

import boto3
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.alert_rule import AlertRule
from src.models.latest_reading import LatestReading
from src.models.rule_group import RuleGroup
from src.models.user import User
from src.models.weather_data import WeatherData
from src.shared.config import settings
from src.shared.db import get_primary_session

router = APIRouter(tags=["dashboard"])


def _boto_kwargs():
    kw = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        kw["endpoint_url"] = settings.aws_endpoint_url
    return kw


def _get_kinesis_info() -> list[dict]:
    try:
        client = boto3.client("kinesis", **_boto_kwargs())
        streams = client.list_streams().get("StreamNames", [])
        result = []
        for name in streams:
            desc = client.describe_stream(StreamName=name)["StreamDescription"]
            result.append({
                "name": name,
                "status": desc["StreamStatus"],
                "shards": len(desc["Shards"]),
                "retention_hours": desc["RetentionPeriodHours"],
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


def _get_sqs_info() -> list[dict]:
    try:
        client = boto3.client("sqs", **_boto_kwargs())
        queues = client.list_queues().get("QueueUrls", [])
        result = []
        for url in queues:
            attrs = client.get_queue_attributes(
                QueueUrl=url, AttributeNames=["All"]
            )["Attributes"]
            name = url.split("/")[-1]
            result.append({
                "name": name,
                "url": url,
                "messages_visible": int(attrs.get("ApproximateNumberOfMessages", 0)),
                "messages_in_flight": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
                "messages_delayed": int(attrs.get("ApproximateNumberOfMessagesDelayed", 0)),
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


async def _get_db_stats(db: AsyncSession) -> dict:
    try:
        users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        rules = (await db.execute(select(func.count(AlertRule.id)))).scalar() or 0
        groups = (await db.execute(select(func.count(RuleGroup.id)))).scalar() or 0
        weather = (await db.execute(select(func.count(WeatherData.id)))).scalar() or 0
        readings = (await db.execute(select(func.count()).select_from(LatestReading))).scalar() or 0
        return {
            "users": users,
            "alert_rules": rules,
            "rule_groups": groups,
            "weather_data_rows": weather,
            "latest_readings": readings,
        }
    except Exception as e:
        return {"error": str(e)}


async def _get_recent_readings(db: AsyncSession) -> list[dict]:
    try:
        result = await db.execute(
            select(LatestReading)
            .order_by(LatestReading.recorded_at.desc())
            .limit(20)
        )
        return [
            {"h3": r.h3_index, "metric": r.metric_type, "value": float(r.value),
             "at": r.recorded_at.isoformat() if r.recorded_at else ""}
            for r in result.scalars().all()
        ]
    except Exception:
        return []


def _render_table(headers: list[str], rows: list[list]) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = ""
    for row in rows:
        tds = "".join(f"<td>{cell}</td>" for cell in row)
        trs += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(db: AsyncSession = Depends(get_primary_session)):
    kinesis = _get_kinesis_info()
    sqs = _get_sqs_info()
    db_stats = await _get_db_stats(db)
    readings = await _get_recent_readings(db)

    # Kinesis table
    if kinesis and "error" not in kinesis[0]:
        kinesis_html = _render_table(
            ["Stream", "Status", "Shards", "Retention (hrs)"],
            [[s["name"], s["status"], s["shards"], s["retention_hours"]] for s in kinesis],
        )
    else:
        kinesis_html = f"<p class='error'>Error: {kinesis[0].get('error', 'unknown')}</p>"

    # SQS table
    if sqs and "error" not in sqs[0]:
        sqs_html = _render_table(
            ["Queue", "Visible", "In Flight", "Delayed"],
            [[s["name"], s["messages_visible"], s["messages_in_flight"], s["messages_delayed"]] for s in sqs],
        )
    else:
        sqs_html = f"<p class='error'>Error: {sqs[0].get('error', 'unknown') if sqs else 'no queues'}</p>"

    # DB stats
    if "error" not in db_stats:
        db_html = _render_table(
            ["Table", "Count"],
            [[k.replace("_", " ").title(), v] for k, v in db_stats.items()],
        )
    else:
        db_html = f"<p class='error'>Error: {db_stats['error']}</p>"

    # Latest readings
    if readings:
        readings_html = _render_table(
            ["H3 Index", "Metric", "Value", "Recorded At"],
            [[r["h3"], r["metric"], f"{r['value']:.2f}", r["at"][:19]] for r in readings],
        )
    else:
        readings_html = "<p>No readings yet. Run the simulator to generate data.</p>"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Agrobot Dashboard</title>
    <meta http-equiv="refresh" content="5">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f1117; color: #e1e4e8; padding: 24px; }}
        h1 {{ font-size: 24px; margin-bottom: 24px; color: #58a6ff; }}
        h2 {{ font-size: 16px; margin: 20px 0 8px; color: #8b949e; text-transform: uppercase;
              letter-spacing: 1px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px;
                background: #161b22; border-radius: 8px; overflow: hidden; }}
        th {{ background: #21262d; padding: 10px 14px; text-align: left; font-size: 13px;
             color: #8b949e; font-weight: 600; }}
        td {{ padding: 10px 14px; border-top: 1px solid #21262d; font-size: 14px;
             font-family: 'SF Mono', monospace; }}
        tr:hover td {{ background: #1c2128; }}
        .error {{ color: #f85149; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        .refresh {{ color: #484f58; font-size: 12px; float: right; }}
    </style>
</head>
<body>
    <h1>Agrobot Dashboard <span class="refresh">auto-refresh 5s</span></h1>

    <div class="grid">
        <div>
            <h2>Kinesis Streams</h2>
            {kinesis_html}
        </div>
        <div>
            <h2>SQS Queues</h2>
            {sqs_html}
        </div>
    </div>

    <div class="grid">
        <div>
            <h2>Database</h2>
            {db_html}
        </div>
        <div>
            <h2>Latest Readings (most recent 20)</h2>
            {readings_html}
        </div>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html)
