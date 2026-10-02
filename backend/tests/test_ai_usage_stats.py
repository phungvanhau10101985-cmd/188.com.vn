"""Chi phí token và parser log API — cùng công thức nanoai."""

from types import SimpleNamespace

from app.services.ai_token_cost import calc_cost_vnd_split, is_listed_api_cost_model
from app.services.ai_usage_report import build_api_usage_report
from app.services.ai_usage_tracker import parse_tracked_call


def test_flash_cost_matches_nanoai_table():
    split = calc_cost_vnd_split(1_000_000, 0, "gemini-2.5-flash", usd_to_vnd=25_000)
    assert split["inputVnd"] == 7500
    assert split["totalVnd"] == 7500


def test_pro_image_4k_uses_fixed_image_tokens():
    split = calc_cost_vnd_split(0, 999_999, "gemini-3-pro-image-preview", "4K", usd_to_vnd=25_000)
    # 2000 token ảnh * $120 / 1M * 25000₫
    assert split["outputVnd"] == 6000
    assert is_listed_api_cost_model("gemini-3-pro-image-preview")
    assert is_listed_api_cost_model("model-khong-co") is False


def test_parse_gemini_usage_and_image_size():
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"
    payload = {"generationConfig": {"imageConfig": {"imageSize": "2K"}}}
    body = {"usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40, "totalTokenCount": 160}}
    parsed = parse_tracked_call(url, {"json": payload}, SimpleNamespace(status_code=200, content=b"{}", json=lambda: body))
    assert parsed is not None
    assert parsed["model"] == "gemini-3-pro-image-preview"
    assert parsed["image_size"] == "2K"
    assert parsed["prompt_token_count"] == 120
    assert parsed["total_token_count"] == 160


def test_report_aggregates_without_touching_database():
    class Row:
        def __init__(self):
            self.id = 1
            self.model = "gemini-2.5-flash"
            self.feature = "category-seo"
            self.prompt_token_count = 1_000_000
            self.candidates_token_count = 0
            self.total_token_count = 1_000_000
            self.image_size = None
            from datetime import datetime, timezone

            self.created_at = datetime(2026, 10, 2, 3, 0, tzinfo=timezone.utc)

    class Query:
        def __init__(self, rows=None, scalar_value=0):
            self.rows = rows or []
            self.scalar_value = scalar_value

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self.rows

        def scalar(self):
            return self.scalar_value

    class Db:
        def query(self, model):
            name = getattr(model, "__name__", "")
            if name == "ApiUsageLog":
                return Query([Row()])
            return Query(scalar_value=100_000)

    report = build_api_usage_report(Db(), "2026-10-01", "2026-10-02", ensure_table=False)
    assert report["callCount"] == 1
    assert report["apiCostVnd"] == 7500
    assert report["revenueVnd"] == 100_000
    assert report["profitVnd"] == 92_500
    assert report["byFeature"][0]["label"] == "SEO danh mục"
    assert report["byModel"][0]["listedPrice"] is True
