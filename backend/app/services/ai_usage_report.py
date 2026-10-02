"""Tổng hợp thống kê chi phí API AI theo khoảng ngày giờ Việt Nam."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.api_usage_log import ApiUsageLog
from app.models.order import Order, OrderStatus, PaymentStatus
from app.services.ai_token_cost import (
    calc_cost_vnd_split,
    feature_label,
    get_partner_ai_token_cost_usd_to_vnd,
    is_listed_api_cost_model,
    model_display_label,
)
from app.services.ai_usage_tracker import _ensure_table

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
CHART_OTHER_KEY = "__other__"


def ict_ymd(moment: Optional[datetime] = None) -> str:
    current = moment or datetime.now(ICT)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(ICT).strftime("%Y-%m-%d")


def ict_shift_days(days: int, moment: Optional[datetime] = None) -> str:
    y, m, d = [int(part) for part in ict_ymd(moment).split("-")]
    shifted = datetime(y, m, d, tzinfo=timezone.utc) + timedelta(days=days)
    return shifted.strftime("%Y-%m-%d")


def _parse_ymd(value: str) -> datetime:
    y, m, d = [int(part) for part in value.split("-")]
    return datetime(y, m, d, tzinfo=ICT)


def range_bounds(from_ymd: str, to_ymd: str) -> tuple[datetime, datetime, str, str]:
    start_raw = (from_ymd or "").strip() or ict_shift_days(-30)
    end_raw = (to_ymd or "").strip() or ict_ymd()
    start = _parse_ymd(start_raw)
    end_day = _parse_ymd(end_raw)
    if end_day < start:
        start, end_day = end_day, start
        start_raw, end_raw = end_raw, start_raw
    end = end_day.replace(hour=23, minute=59, second=59, microsecond=999000)
    return start, end, start.strftime("%Y-%m-%d"), end_day.strftime("%Y-%m-%d")


def _enumerate_days(from_ymd: str, to_ymd: str) -> List[str]:
    start = _parse_ymd(from_ymd)
    end = _parse_ymd(to_ymd)
    days: List[str] = []
    cursor = start
    while cursor <= end:
        days.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
        if len(days) > 800:
            break
    return days


def _day_label(ymd: str) -> str:
    parsed = _parse_ymd(ymd)
    return parsed.strftime("%d/%m")


def _empty_bucket() -> Dict[str, int]:
    return {
        "calls": 0,
        "promptTokens": 0,
        "outputTokens": 0,
        "totalTokens": 0,
        "costVnd": 0,
        "inputCostVnd": 0,
        "outputCostVnd": 0,
        "calls1K": 0,
        "calls2K": 0,
        "calls4K": 0,
        "callsNoImage": 0,
    }


def _apply_log(bucket: Dict[str, int], prompt: int, output: int, total: int, split: Dict[str, int], image_size: Optional[str], with_sizes: bool) -> None:
    bucket["calls"] += 1
    bucket["promptTokens"] += prompt
    bucket["outputTokens"] += output
    bucket["totalTokens"] += total
    bucket["costVnd"] += split["totalVnd"]
    bucket["inputCostVnd"] += split["inputVnd"]
    bucket["outputCostVnd"] += split["outputVnd"]
    if not with_sizes:
        return
    if image_size == "1K":
        bucket["calls1K"] += 1
    elif image_size == "2K":
        bucket["calls2K"] += 1
    elif image_size == "4K":
        bucket["calls4K"] += 1
    else:
        bucket["callsNoImage"] += 1


def _bucket_row(key: str, label: str, bucket: Dict[str, int], *, listed: Optional[bool] = None) -> Dict[str, Any]:
    row = {"key": key, "label": label, **bucket}
    if listed is not None:
        row["listedPrice"] = listed
    return row


def _revenue_vnd(db: Session, start: datetime, end: datetime) -> int:
    paid = (PaymentStatus.PAID, PaymentStatus.DEPOSIT_PAID, PaymentStatus.PARTIALLY_PAID)
    amount = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(
            Order.created_at >= start,
            Order.created_at <= end,
            Order.payment_status.in_(paid),
            Order.status != OrderStatus.CANCELLED,
        )
        .scalar()
    )
    try:
        return int(round(float(amount or 0)))
    except (TypeError, ValueError):
        return 0


def build_api_usage_report(db: Session, from_ymd: str, to_ymd: str, *, ensure_table: bool = True) -> Dict[str, Any]:
    if ensure_table:
        from app.db.session import engine

        _ensure_table(engine)
    start, end, from_date, to_date = range_bounds(from_ymd, to_ymd)
    usd_to_vnd = get_partner_ai_token_cost_usd_to_vnd()
    logs = (
        db.query(ApiUsageLog)
        .filter(ApiUsageLog.created_at >= start, ApiUsageLog.created_at <= end)
        .order_by(ApiUsageLog.created_at.desc())
        .all()
    )

    by_model: Dict[str, Dict[str, int]] = {}
    by_feature: Dict[str, Dict[str, int]] = {}
    by_image: Dict[str, Dict[str, int]] = {}
    totals = _empty_bucket()
    prepared: List[Dict[str, Any]] = []

    for log in logs:
        prompt = int(log.prompt_token_count or 0)
        output = int(log.candidates_token_count or 0)
        total = int(log.total_token_count or 0)
        image_size = log.image_size if log.image_size in ("1K", "2K", "4K") else None
        split = calc_cost_vnd_split(prompt, output, log.model, image_size, usd_to_vnd=usd_to_vnd)
        created = log.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        day = created.astimezone(ICT).strftime("%Y-%m-%d") if created else from_date
        prepared.append(
            {
                "id": log.id,
                "model": log.model,
                "feature": log.feature,
                "prompt": prompt,
                "output": output,
                "total": total,
                "image_size": image_size,
                "split": split,
                "day": day,
                "created_at": created.isoformat() if created else None,
            }
        )
        _apply_log(totals, prompt, output, total, split, image_size, True)
        by_model.setdefault(log.model, _empty_bucket())
        _apply_log(by_model[log.model], prompt, output, total, split, image_size, True)
        by_feature.setdefault(log.feature, _empty_bucket())
        _apply_log(by_feature[log.feature], prompt, output, total, split, image_size, True)
        size_key = image_size or "no-image"
        by_image.setdefault(size_key, _empty_bucket())
        _apply_log(by_image[size_key], prompt, output, total, split, image_size, False)

    def sort_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(rows, key=lambda item: item["costVnd"], reverse=True)

    model_rows = sort_rows(
        [
            _bucket_row(model, model_display_label(model), bucket, listed=is_listed_api_cost_model(model))
            for model, bucket in by_model.items()
        ]
    )
    feature_rows = sort_rows(
        [_bucket_row(feature, feature_label(feature), bucket) for feature, bucket in by_feature.items()]
    )
    image_order = ("1K", "2K", "4K", "no-image")
    image_rows = []
    for key in image_order:
        bucket = by_image.get(key)
        if not bucket or bucket["calls"] <= 0:
            continue
        label = "Không trả ảnh" if key == "no-image" else key
        image_rows.append(_bucket_row(key, label, bucket))

    days = _enumerate_days(from_date, to_date)
    model_totals = {row["key"]: row["costVnd"] for row in model_rows}
    top_keys = [row["key"] for row in model_rows[:8]]
    top_set = set(top_keys)
    daily = {
        day: {"requests": 0, "inputTokens": 0, "outputTokens": 0, "inputCostVnd": 0, "outputCostVnd": 0, "totalCostVnd": 0}
        for day in days
    }
    per_model = {day: {key: {"requests": 0, "inputTokens": 0, "costVnd": 0} for key in [*top_keys, CHART_OTHER_KEY]} for day in days}
    other_any = False
    for item in prepared:
        bucket = daily.get(item["day"])
        if bucket is None:
            continue
        split = item["split"]
        bucket["requests"] += 1
        bucket["inputTokens"] += item["prompt"]
        bucket["outputTokens"] += item["output"]
        bucket["inputCostVnd"] += split["inputVnd"]
        bucket["outputCostVnd"] += split["outputVnd"]
        bucket["totalCostVnd"] += split["totalVnd"]
        series_key = item["model"] if item["model"] in top_set else CHART_OTHER_KEY
        if series_key == CHART_OTHER_KEY:
            other_any = True
        cell = per_model[item["day"]][series_key]
        cell["requests"] += 1
        cell["inputTokens"] += item["prompt"]
        cell["costVnd"] += split["totalVnd"]

    def series_rows(field: str) -> List[Dict[str, Any]]:
        rows = []
        for day in days:
            row: Dict[str, Any] = {"dateKey": day, "dateLabel": _day_label(day)}
            for key in top_keys:
                row[key] = per_model[day][key][field]
            row[CHART_OTHER_KEY] = per_model[day][CHART_OTHER_KEY][field]
            rows.append(row)
        return rows

    tokens_by_model = series_rows("inputTokens")
    show_other = other_any and any(int(row.get(CHART_OTHER_KEY) or 0) > 0 for row in tokens_by_model)
    api_cost = totals["costVnd"]
    revenue = _revenue_vnd(db, start, end)
    recent = []
    for item in prepared[:100]:
        recent.append(
            {
                "id": item["id"],
                "model": item["model"],
                "modelLabel": model_display_label(item["model"]),
                "feature": item["feature"],
                "featureLabel": feature_label(item["feature"]),
                "promptTokens": item["prompt"],
                "outputTokens": item["output"],
                "totalTokens": item["total"],
                "imageSize": item["image_size"],
                "inputCostVnd": item["split"]["inputVnd"],
                "outputCostVnd": item["split"]["outputVnd"],
                "costVnd": item["split"]["totalVnd"],
                "listedPrice": is_listed_api_cost_model(item["model"]),
                "createdAt": item["created_at"],
            }
        )

    return {
        "from": from_date,
        "to": to_date,
        "usdToVnd": usd_to_vnd,
        "revenueVnd": revenue,
        "apiCostVnd": api_cost,
        "apiCostUsd": round(api_cost / usd_to_vnd, 4) if usd_to_vnd else 0,
        "profitVnd": revenue - api_cost,
        "callCount": totals["calls"],
        "totals": {
            "calls": totals["calls"],
            "promptTokens": totals["promptTokens"],
            "outputTokens": totals["outputTokens"],
            "totalTokens": totals["totalTokens"],
            "inputCostVnd": totals["inputCostVnd"],
            "outputCostVnd": totals["outputCostVnd"],
            "totalCostVnd": totals["costVnd"],
        },
        "byModel": model_rows,
        "byFeature": feature_rows,
        "byImageSize": image_rows,
        "recentLogs": recent,
        "charts": {
            "daily": [
                {
                    "dateKey": day,
                    "dateLabel": _day_label(day),
                    **daily[day],
                }
                for day in days
            ],
            "modelKeys": top_keys,
            "modelLabels": {key: model_display_label(key) for key in top_keys},
            "tokensByModelRows": tokens_by_model,
            "requestsByModelRows": series_rows("requests"),
            "costByModelRows": series_rows("costVnd"),
            "showOtherSeries": show_other,
            "otherKey": CHART_OTHER_KEY,
        },
        "modelCostTotals": model_totals,
    }
