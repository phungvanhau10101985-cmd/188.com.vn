"""Tổng hợp thống kê chi phí API AI theo khoảng ngày giờ Việt Nam."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.api_usage_log import ApiUsageLog
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


def _money_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def commerce_costs_for_range(db: Session, date_from: str, date_to: str) -> Dict[str, Any]:
    """Doanh thu đã cọc, giá vốn, ship và quảng cáo — cùng nguồn với bảng lợi nhuận chi phí quảng cáo."""
    from app.services.ad_spend_profit import load_profit_sheet
    from app.services.ad_spend_service import load_report

    sheet = load_profit_sheet(db, date_from, date_to)
    cost_ready = sheet.get("cost_vnd") is not None
    missing = int(sheet.get("missing_goods_count") or 0)
    goods = _money_int(sheet.get("goods_cost_vnd")) if cost_ready else None
    ship = _money_int(sheet.get("ship_cost_vnd")) if cost_ready else None
    if cost_ready:
        cost_note = "Giá nhập và ship của đơn đã cọc, cùng công thức bảng chi phí quảng cáo"
    elif missing:
        cost_note = f"{missing} đơn còn thiếu giá nhập"
    else:
        cost_note = "Chưa đủ giá vốn và ship"

    ad_spend = None
    ad_ready = False
    ad_note = "Chưa đọc được chi phí quảng cáo"
    try:
        ads = load_report(db, date_from, date_to)
    except Exception as exc:
        ads = None
        ad_note = str(exc)
    if ads is not None:
        status = ads.get("total_status")
        currency = str(ads.get("total_currency") or "").upper()
        spend = ads.get("total_spend")
        google = ads.get("google") or {}
        facebook = ads.get("facebook") or {}
        if status == "ok" and spend is not None and currency == "VND":
            ad_spend = _money_int(spend)
            ad_ready = ad_spend is not None
            ad_note = "Google + Facebook"
        elif status == "mixed_currency":
            ad_note = "Google và Facebook không cùng đơn vị tiền"
        elif currency and currency != "VND":
            ad_note = f"Quảng cáo đang tính bằng {currency}, chưa quy đổi VND"
        elif not google.get("configured") and not facebook.get("configured"):
            ad_note = "Chưa cấu hình quảng cáo"
        else:
            errors = []
            for name, block in (("Google Ads", google), ("Facebook Ads", facebook)):
                if block.get("configured") and not block.get("ok") and block.get("error"):
                    errors.append(f"{name}: {block['error']}")
            ad_note = errors[0] if errors else "Chưa đọc đủ chi phí quảng cáo"
    return {
        "revenueVnd": _money_int(sheet.get("revenue_vnd")) or 0,
        "orderCount": int(sheet.get("order_count") or 0),
        "goodsCostVnd": goods,
        "shipCostVnd": ship,
        "costReady": bool(cost_ready and goods is not None and ship is not None),
        "missingGoodsCount": missing,
        "costNote": cost_note,
        "adSpendVnd": ad_spend,
        "adSpendReady": ad_ready,
        "adSpendNote": ad_note,
    }


def period_profit_vnd(commerce: Dict[str, Any], api_cost: int) -> Optional[int]:
    """Thu đã cọc − giá vốn − ship − quảng cáo − chi API. Thiếu một khoản thì chưa chốt lãi."""
    if not commerce.get("costReady") or not commerce.get("adSpendReady"):
        return None
    goods = commerce.get("goodsCostVnd")
    ship = commerce.get("shipCostVnd")
    ads = commerce.get("adSpendVnd")
    if goods is None or ship is None or ads is None:
        return None
    return int(commerce.get("revenueVnd") or 0) - int(goods) - int(ship) - int(ads) - int(api_cost)


def build_api_usage_report(
    db: Session,
    from_ymd: str,
    to_ymd: str,
    *,
    ensure_table: bool = True,
    commerce: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
    commerce_row = commerce if commerce is not None else commerce_costs_for_range(db, from_date, to_date)
    profit = period_profit_vnd(commerce_row, api_cost)
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
        "revenueVnd": int(commerce_row.get("revenueVnd") or 0),
        "orderCount": int(commerce_row.get("orderCount") or 0),
        "goodsCostVnd": commerce_row.get("goodsCostVnd"),
        "shipCostVnd": commerce_row.get("shipCostVnd"),
        "costReady": bool(commerce_row.get("costReady")),
        "missingGoodsCount": int(commerce_row.get("missingGoodsCount") or 0),
        "costNote": commerce_row.get("costNote") or "",
        "adSpendVnd": commerce_row.get("adSpendVnd"),
        "adSpendReady": bool(commerce_row.get("adSpendReady")),
        "adSpendNote": commerce_row.get("adSpendNote") or "",
        "apiCostVnd": api_cost,
        "apiCostUsd": round(api_cost / usd_to_vnd, 4) if usd_to_vnd else 0,
        "profitVnd": profit,
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
