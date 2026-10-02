"""Đọc chi phí quảng cáo Google Ads và Meta (Facebook) — không ghi log khóa bí mật."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ad_spend import AdSpendSettings

logger = logging.getLogger(__name__)

MAX_RANGE_DAYS = 366
_CACHE_TTL_SECONDS = 180
_METRICS_VERSION = "conv1"
_cache: Dict[str, Tuple[float, dict]] = {}

# Một sự kiện mua có thể xuất hiện ở nhiều action_type. Chỉ lấy loại đầu tiên có số,
# ưu tiên omni_purchase vì Meta đã gộp và khử trùng kênh.
_META_PURCHASE_TYPES = (
    "omni_purchase",
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "onsite_web_purchase",
    "web_in_store_purchase",
    "onsite_conversion.purchase",
)

class AdSpendApiError(Exception):
    pass


def normalize_customer_id(raw: Optional[str]) -> str:
    return re.sub(r"\D", "", raw or "")


def normalize_ad_account_id(raw: Optional[str]) -> str:
    text = re.sub(r"^act_", "", (raw or "").strip(), flags=re.IGNORECASE)
    return re.sub(r"\D", "", text)


def micros_to_amount(micros: Any) -> float:
    try:
        return int(micros or 0) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


def parse_date_range(date_from: str, date_to: str) -> Tuple[date, date]:
    try:
        start = datetime.strptime((date_from or "").strip(), "%Y-%m-%d").date()
        end = datetime.strptime((date_to or "").strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Ngày phải theo dạng YYYY-MM-DD.") from exc
    if end < start:
        raise ValueError("Ngày kết thúc phải sau hoặc trùng ngày bắt đầu.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Khoảng thời gian tối đa {MAX_RANGE_DAYS} ngày.")
    return start, end


def pick_secret(db_value: Optional[str], env_value: Optional[str]) -> Tuple[str, str]:
    stored = (db_value or "").strip()
    if stored:
        return stored, "database"
    env = (env_value or "").strip()
    if env:
        return env, "environment"
    return "", ""


def summarize_sources(sources: List[str]) -> str:
    if not sources or any(not item for item in sources):
        return "incomplete"
    kinds = set(sources)
    if kinds == {"database"}:
        return "database"
    if kinds == {"environment"}:
        return "environment"
    return "mixed"


def _google_api_version() -> str:
    raw = (getattr(settings, "GOOGLE_ADS_API_VERSION", None) or "v25").strip() or "v25"
    return raw if raw.startswith("v") else f"v{raw}"


def _meta_graph_version() -> str:
    raw = (getattr(settings, "META_ADS_GRAPH_API_VERSION", None) or "v25.0").strip() or "v25.0"
    return raw if raw.startswith("v") else f"v{raw}"


def get_or_create_settings(db: Session) -> AdSpendSettings:
    row = db.query(AdSpendSettings).filter(AdSpendSettings.id == 1).first()
    if row:
        return row
    row = AdSpendSettings(id=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _env_map() -> Dict[str, str]:
    return {
        "google_developer_token": getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", "") or "",
        "google_client_id": getattr(settings, "GOOGLE_ADS_CLIENT_ID", "") or "",
        "google_client_secret": getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", "") or "",
        "google_refresh_token": getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", "") or "",
        "google_customer_id": getattr(settings, "GOOGLE_ADS_CUSTOMER_ID", "") or "",
        "google_login_customer_id": getattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "") or "",
        "google_service_account_file": getattr(settings, "GOOGLE_ADS_SERVICE_ACCOUNT_FILE", "") or "",
        "meta_access_token": getattr(settings, "META_ADS_ACCESS_TOKEN", "") or "",
        "meta_ad_account_id": getattr(settings, "META_ADS_ACCOUNT_ID", "") or "",
    }


def resolve_credentials(row: AdSpendSettings) -> Dict[str, Any]:
    env = _env_map()
    google_parts = {
        "developer_token": pick_secret(row.google_developer_token, env["google_developer_token"]),
        "client_id": pick_secret(row.google_client_id, env["google_client_id"]),
        "client_secret": pick_secret(row.google_client_secret, env["google_client_secret"]),
        "refresh_token": pick_secret(row.google_refresh_token, env["google_refresh_token"]),
        "customer_id": pick_secret(
            normalize_customer_id(row.google_customer_id) or None,
            normalize_customer_id(env["google_customer_id"]),
        ),
    }
    login_value, _login_source = pick_secret(
        normalize_customer_id(row.google_login_customer_id) or None,
        normalize_customer_id(env["google_login_customer_id"]),
    )
    meta_token = pick_secret(row.meta_access_token, env["meta_access_token"])
    meta_account = pick_secret(
        normalize_ad_account_id(row.meta_ad_account_id) or None,
        normalize_ad_account_id(env["meta_ad_account_id"]),
    )
    service_account, service_source = load_service_account(env.get("google_service_account_file") or "")
    google = {key: value for key, (value, _source) in google_parts.items()}
    oauth_ok = bool(google["client_id"] and google["client_secret"] and google["refresh_token"])
    auth_sources = [service_source] if service_account else [
        google_parts["client_id"][1],
        google_parts["client_secret"][1],
        google_parts["refresh_token"][1],
    ]
    google_sources = auth_sources + [google_parts["customer_id"][1]]
    return {
        "google": google,
        "google_login_customer_id": login_value,
        "service_account": service_account,
        "google_service_account_email": (service_account or {}).get("client_email") or "",
        "google_source": summarize_sources(google_sources),
        "google_configured": bool(google["customer_id"]) and (bool(service_account) or oauth_ok),
        "meta_access_token": meta_token[0],
        "meta_ad_account_id": meta_account[0],
        "meta_source": summarize_sources([meta_token[1], meta_account[1]]),
        "facebook_configured": bool(meta_token[0] and meta_account[0]),
    }


def settings_to_view(row: AdSpendSettings) -> dict:
    creds = resolve_credentials(row)
    google = creds["google"]
    return {
        "google_customer_id": google["customer_id"],
        "google_login_customer_id": creds["google_login_customer_id"],
        "google_developer_token_set": bool(google["developer_token"]),
        "google_client_id_set": bool(google["client_id"]),
        "google_client_secret_set": bool(google["client_secret"]),
        "google_refresh_token_set": bool(google["refresh_token"]),
        "google_service_account_email": creds.get("google_service_account_email") or "",
        "google_configured": creds["google_configured"],
        "google_credential_source": creds["google_source"],
        "meta_ad_account_id": creds["meta_ad_account_id"],
        "meta_access_token_set": bool(creds["meta_access_token"]),
        "facebook_configured": creds["facebook_configured"],
        "meta_credential_source": creds["meta_source"],
        "google_ads_api_version": _google_api_version(),
        "meta_graph_api_version": _meta_graph_version(),
    }


def apply_settings_update(row: AdSpendSettings, payload: dict) -> None:
    if payload.get("clear_google_secrets"):
        row.google_developer_token = None
        row.google_client_id = None
        row.google_client_secret = None
        row.google_refresh_token = None
    if payload.get("clear_meta_secrets"):
        row.meta_access_token = None

    if "google_customer_id" in payload and payload["google_customer_id"] is not None:
        row.google_customer_id = normalize_customer_id(payload["google_customer_id"]) or None
    if "google_login_customer_id" in payload and payload["google_login_customer_id"] is not None:
        row.google_login_customer_id = normalize_customer_id(payload["google_login_customer_id"]) or None
    if "meta_ad_account_id" in payload and payload["meta_ad_account_id"] is not None:
        row.meta_ad_account_id = normalize_ad_account_id(payload["meta_ad_account_id"]) or None

    for field in (
        "google_developer_token",
        "google_client_id",
        "google_client_secret",
        "google_refresh_token",
        "meta_access_token",
    ):
        raw = payload.get(field)
        if isinstance(raw, str) and raw.strip():
            setattr(row, field, raw.strip())


def google_error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "Google Ads từ chối yêu cầu."
    err = payload.get("error")
    if isinstance(err, str):
        desc = str(payload.get("error_description") or err).strip()
        return f"Không lấy được token Google: {desc}"
    if isinstance(err, dict):
        msg = str(err.get("message") or "Google Ads từ chối yêu cầu.").strip()
        extras: List[str] = []
        for detail in err.get("details") or []:
            if not isinstance(detail, dict):
                continue
            for item in detail.get("errors") or []:
                if isinstance(item, dict):
                    text = str(item.get("message") or "").strip()
                    if text:
                        extras.append(text)
        if extras:
            return f"{msg} {' '.join(extras[:2])}"
        return msg
    return "Google Ads từ chối yêu cầu."


def meta_error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "Facebook từ chối yêu cầu."
    err = payload.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message") or "").strip()
        if msg:
            return msg
    return "Facebook từ chối yêu cầu."


def _metric_bucket() -> Dict[str, float]:
    return {
        "spend": 0.0,
        "impressions": 0.0,
        "clicks": 0.0,
        "conversions": 0.0,
        "conversion_value": 0.0,
    }


def _add_metrics(bucket: Dict[str, float], spend: float, impressions: int, clicks: int, conversions: float, conversion_value: float) -> None:
    bucket["spend"] += spend
    bucket["impressions"] += impressions
    bucket["clicks"] += clicks
    bucket["conversions"] += conversions
    bucket["conversion_value"] += conversion_value


def aggregate_metric_rows(
    rows: List[dict],
    *,
    date_key: str,
    spend_key: str,
    impressions_key: str,
    clicks_key: str,
    campaign_id_key: str,
    campaign_name_key: str,
    currency_key: str,
    spend_is_micros: bool,
    conversions_key: str = "conversions",
    conversion_value_key: str = "conversion_value",
) -> dict:
    daily: Dict[str, Dict[str, float]] = {}
    campaigns: Dict[str, Dict[str, Any]] = {}
    currency: Optional[str] = None
    for row in rows:
        day = str(row.get(date_key) or "").strip()
        raw_spend = row.get(spend_key)
        spend = micros_to_amount(raw_spend) if spend_is_micros else _as_float(raw_spend)
        impressions = _as_int(row.get(impressions_key))
        clicks = _as_int(row.get(clicks_key))
        conversions = _as_float(row.get(conversions_key))
        conversion_value = _as_float(row.get(conversion_value_key))
        code = str(row.get(currency_key) or "").strip()
        if code and not currency:
            currency = code
        if day:
            bucket = daily.setdefault(day, _metric_bucket())
            _add_metrics(bucket, spend, impressions, clicks, conversions, conversion_value)
        cid = str(row.get(campaign_id_key) or "").strip() or str(row.get(campaign_name_key) or "").strip()
        if not cid:
            continue
        camp = campaigns.setdefault(
            cid,
            {
                "id": cid,
                "name": str(row.get(campaign_name_key) or cid),
                **_metric_bucket(),
            },
        )
        _add_metrics(camp, spend, impressions, clicks, conversions, conversion_value)

    daily_rows = [
        {
            "date": day,
            "spend": round(values["spend"], 2),
            "impressions": int(values["impressions"]),
            "clicks": int(values["clicks"]),
            "conversions": round(values["conversions"], 2),
            "conversion_value": round(values["conversion_value"], 2),
        }
        for day, values in sorted(daily.items(), reverse=True)
    ]
    campaign_rows = sorted(campaigns.values(), key=lambda item: item["spend"], reverse=True)
    for item in campaign_rows:
        item["spend"] = round(float(item["spend"]), 2)
        item["impressions"] = int(item["impressions"])
        item["clicks"] = int(item["clicks"])
        item["conversions"] = round(float(item["conversions"]), 2)
        item["conversion_value"] = round(float(item["conversion_value"]), 2)
    spend_total = round(sum(item["spend"] for item in daily_rows), 2)
    return {
        "currency": currency,
        "spend": spend_total,
        "impressions": sum(item["impressions"] for item in daily_rows),
        "clicks": sum(item["clicks"] for item in daily_rows),
        "conversions": round(sum(item["conversions"] for item in daily_rows), 2),
        "conversion_value": round(sum(item["conversion_value"] for item in daily_rows), 2),
        "daily": daily_rows,
        "campaigns": campaign_rows,
    }


def flatten_google_results(results: List[dict]) -> List[dict]:
    out: List[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") or {}
        campaign = item.get("campaign") or {}
        segments = item.get("segments") or {}
        customer = item.get("customer") or {}
        out.append(
            {
                "date": segments.get("date"),
                "spend_micros": metrics.get("costMicros", metrics.get("cost_micros")),
                "impressions": metrics.get("impressions"),
                "clicks": metrics.get("clicks"),
                "conversions": metrics.get("conversions"),
                "conversion_value": metrics.get("conversionsValue", metrics.get("conversions_value")),
                "campaign_id": campaign.get("id"),
                "campaign_name": campaign.get("name"),
                "currency": customer.get("currencyCode") or customer.get("currency_code"),
            }
        )
    return out


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def meta_action_amount(actions: Any, preferred: Tuple[str, ...]) -> float:
    """Lấy một action_type, không cộng các loại trùng cùng một lượt mua."""
    if not isinstance(actions, list):
        return 0.0
    found: Dict[str, float] = {}
    for item in actions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("action_type") or "").strip()
        if not name:
            continue
        found[name] = _as_float(item.get("value"))
    for name in preferred:
        amount = found.get(name) or 0.0
        if amount:
            return amount
    return 0.0


def _empty_platform(*, configured: bool, error: Optional[str] = None) -> dict:
    return {
        "configured": configured,
        "ok": error is None,
        "error": error,
        "currency": None,
        "spend": 0,
        "impressions": 0,
        "clicks": 0,
        "conversions": 0,
        "conversion_value": 0,
        "daily": [],
        "campaigns": [],
        "partial": False,
    }


def _platform_from_aggregate(configured: bool, aggregated: dict, *, partial: bool = False) -> dict:
    return {
        "configured": configured,
        "ok": True,
        "error": None,
        "partial": partial,
        **aggregated,
    }


def load_service_account(path: str) -> Tuple[Optional[dict], str]:
    file_path = (path or "").strip()
    if not file_path:
        return None, ""
    target = Path(file_path)
    if not target.is_file():
        return None, ""
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, ""
    if not isinstance(data, dict) or data.get("type") != "service_account":
        return None, ""
    if not data.get("client_email") or not data.get("private_key"):
        return None, ""
    return data, "environment"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def service_account_access_token(info: dict) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64url(
        json.dumps(
            {
                "iss": info["client_email"],
                "scope": "https://www.googleapis.com/auth/adwords",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now,
                "exp": now + 3600,
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode()
    key = serialization.load_pem_private_key(str(info["private_key"]).encode(), password=None)
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{claims}.{_b64url(signature)}"
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=25,
        )
    except requests.RequestException as exc:
        raise AdSpendApiError("Không kết nối được máy chủ token Google.") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if response.status_code >= 400 or not token:
        raise AdSpendApiError(google_error_message(payload))
    return str(token)


def refresh_google_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=25,
        )
    except requests.RequestException as exc:
        raise AdSpendApiError("Không kết nối được máy chủ token Google.") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if response.status_code >= 400 or not token:
        raise AdSpendApiError(google_error_message(payload))
    return str(token)


def search_google_ads(
    *,
    customer_id: str,
    access_token: str,
    developer_token: str,
    login_customer_id: str,
    query: str,
) -> Tuple[List[dict], bool]:
    url = f"https://googleads.googleapis.com/{_google_api_version()}/customers/{customer_id}/googleAds:search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if developer_token:
        headers["developer-token"] = developer_token
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id
    rows: List[dict] = []
    page_token = ""
    partial = False
    for page in range(30):
        body: Dict[str, str] = {"query": query}
        if page_token:
            body["pageToken"] = page_token
        try:
            response = requests.post(url, headers=headers, json=body, timeout=45)
        except requests.RequestException as exc:
            raise AdSpendApiError("Không kết nối được Google Ads.") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            raise AdSpendApiError(google_error_message(payload))
        batch = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(batch, list):
            rows.extend(batch)
        page_token = str((payload or {}).get("nextPageToken") or "")
        if not page_token:
            break
        if page == 29:
            partial = True
    return rows, partial


def fetch_google_rows(creds: dict, start: date, end: date) -> Tuple[List[dict], bool]:
    google = creds["google"]
    service_account = creds.get("service_account")
    if isinstance(service_account, dict) and service_account.get("private_key"):
        token = service_account_access_token(service_account)
    else:
        token = refresh_google_access_token(
            google["client_id"],
            google["client_secret"],
            google["refresh_token"],
        )
    query = (
        "SELECT segments.date, campaign.id, campaign.name, "
        "metrics.cost_micros, metrics.impressions, metrics.clicks, "
        "metrics.conversions, metrics.conversions_value, customer.currency_code "
        "FROM campaign "
        f"WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}' "
        "AND metrics.cost_micros > 0"
    )
    raw, partial = search_google_ads(
        customer_id=google["customer_id"],
        access_token=token,
        developer_token=google["developer_token"],
        login_customer_id=creds.get("google_login_customer_id") or "",
        query=query,
    )
    return flatten_google_results(raw), partial


def fetch_meta_rows(access_token: str, ad_account_id: str, start: date, end: date) -> Tuple[List[dict], bool]:
    version = _meta_graph_version()
    url = f"https://graph.facebook.com/{version}/act_{ad_account_id}/insights"
    params = {
        "fields": (
            "campaign_id,campaign_name,spend,impressions,clicks,actions,action_values,"
            "date_start,account_currency"
        ),
        "level": "campaign",
        "time_increment": "1",
        "time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
        "limit": "500",
        "access_token": access_token,
    }
    rows: List[dict] = []
    next_url: Optional[str] = None
    partial = False
    for page in range(40):
        try:
            if next_url:
                response = requests.get(next_url, timeout=45)
            else:
                response = requests.get(url, params=params, timeout=45)
        except requests.RequestException as exc:
            raise AdSpendApiError("Không kết nối được Facebook Ads.") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400 or (isinstance(payload, dict) and payload.get("error")):
            raise AdSpendApiError(meta_error_message(payload))
        batch = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(batch, list):
            for item in batch:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    {
                        "date": item.get("date_start"),
                        "spend": item.get("spend"),
                        "impressions": item.get("impressions"),
                        "clicks": item.get("clicks"),
                        "conversions": meta_action_amount(item.get("actions"), _META_PURCHASE_TYPES),
                        "conversion_value": meta_action_amount(item.get("action_values"), _META_PURCHASE_TYPES),
                        "campaign_id": item.get("campaign_id"),
                        "campaign_name": item.get("campaign_name"),
                        "currency": item.get("account_currency"),
                    }
                )
        paging = payload.get("paging") if isinstance(payload, dict) else None
        next_url = paging.get("next") if isinstance(paging, dict) else None
        if not next_url:
            break
        if page == 39:
            partial = True
    return rows, partial


def _cache_key(kind: str, creds: dict, start: date, end: date) -> str:
    if kind == "google":
        google = creds["google"]
        material = "|".join(
            [
                kind,
                str(google.get("customer_id") or ""),
                str(google.get("developer_token") or ""),
                str(google.get("refresh_token") or ""),
                str(creds.get("google_service_account_email") or ""),
                creds.get("google_login_customer_id") or "",
                start.isoformat(),
                end.isoformat(),
                _google_api_version(),
                _METRICS_VERSION,
            ]
        )
    else:
        material = "|".join(
            [
                kind,
                creds["meta_ad_account_id"],
                creds["meta_access_token"],
                start.isoformat(),
                end.isoformat(),
                _meta_graph_version(),
                _METRICS_VERSION,
            ]
        )
    return hashlib.sha256(material.encode()).hexdigest()


def _cached_fetch(key: str) -> Optional[Tuple[List[dict], bool]]:
    hit = _cache.get(key)
    if not hit:
        return None
    stored_at, payload = hit
    if time.time() - stored_at > _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return list(payload.get("rows") or []), bool(payload.get("partial"))


def _store_fetch(key: str, rows: List[dict], partial: bool) -> None:
    _cache[key] = (time.time(), {"rows": rows, "partial": partial})


def build_report(creds: dict, start: date, end: date) -> dict:
    google_report = _empty_platform(configured=False)
    facebook_report = _empty_platform(configured=False)

    if creds["google_configured"]:
        try:
            key = _cache_key("google", creds, start, end)
            cached = _cached_fetch(key)
            if cached is None:
                rows, partial = fetch_google_rows(creds, start, end)
                _store_fetch(key, rows, partial)
            else:
                rows, partial = cached
            aggregated = aggregate_metric_rows(
                rows,
                date_key="date",
                spend_key="spend_micros",
                impressions_key="impressions",
                clicks_key="clicks",
                campaign_id_key="campaign_id",
                campaign_name_key="campaign_name",
                currency_key="currency",
                spend_is_micros=True,
            )
            google_report = _platform_from_aggregate(True, aggregated, partial=partial)
        except AdSpendApiError as exc:
            logger.warning("ad_spend google: %s", exc)
            google_report = _empty_platform(configured=True, error=str(exc))
        except Exception:
            logger.exception("ad_spend google unexpected")
            google_report = _empty_platform(configured=True, error="Không đọc được chi phí Google Ads.")

    if creds["facebook_configured"]:
        try:
            key = _cache_key("facebook", creds, start, end)
            cached = _cached_fetch(key)
            if cached is None:
                rows, partial = fetch_meta_rows(
                    creds["meta_access_token"], creds["meta_ad_account_id"], start, end
                )
                _store_fetch(key, rows, partial)
            else:
                rows, partial = cached
            aggregated = aggregate_metric_rows(
                rows,
                date_key="date",
                spend_key="spend",
                impressions_key="impressions",
                clicks_key="clicks",
                campaign_id_key="campaign_id",
                campaign_name_key="campaign_name",
                currency_key="currency",
                spend_is_micros=False,
            )
            facebook_report = _platform_from_aggregate(True, aggregated, partial=partial)
        except AdSpendApiError as exc:
            logger.warning("ad_spend facebook: %s", exc)
            facebook_report = _empty_platform(configured=True, error=str(exc))
        except Exception:
            logger.exception("ad_spend facebook unexpected")
            facebook_report = _empty_platform(configured=True, error="Không đọc được chi phí Facebook Ads.")

    total_spend = None
    total_currency = None
    total_status = "incomplete"
    google_ok = google_report["ok"] and google_report["configured"]
    facebook_ok = facebook_report["ok"] and facebook_report["configured"]
    if google_ok and facebook_ok:
        g_cur = google_report.get("currency")
        f_cur = facebook_report.get("currency")
        if g_cur and f_cur and g_cur != f_cur:
            total_status = "mixed_currency"
        else:
            total_currency = g_cur or f_cur
            total_spend = round(float(google_report["spend"]) + float(facebook_report["spend"]), 2)
            total_status = "ok"
    elif google_ok and not creds["facebook_configured"]:
        total_currency = google_report.get("currency")
        total_spend = google_report["spend"]
        total_status = "ok"
    elif facebook_ok and not creds["google_configured"]:
        total_currency = facebook_report.get("currency")
        total_spend = facebook_report["spend"]
        total_status = "ok"
    elif google_ok or facebook_ok:
        total_status = "incomplete"

    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "google": google_report,
        "facebook": facebook_report,
        "total_spend": total_spend,
        "total_currency": total_currency,
        "total_status": total_status,
    }


def load_report(db: Session, date_from: str, date_to: str) -> dict:
    start, end = parse_date_range(date_from, date_to)
    row = get_or_create_settings(db)
    return build_report(resolve_credentials(row), start, end)


def clear_report_cache() -> None:
    _cache.clear()
