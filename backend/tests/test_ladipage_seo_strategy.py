"""Phân vai SEO ladipage vs danh mục."""
from app.services.ladipage_seo_strategy import (
    apply_ladipage_seo_guardrails,
    ensure_meta_has_material_usp,
    seo_texts_collide,
    suggest_category_ladipage_title,
)


def test_suggest_title_includes_material():
    assert "da bò" in suggest_category_ladipage_title("Oxford nam", "Da bò").lower()


def test_seo_texts_collide_exact_and_near():
    assert seo_texts_collide("Oxford nam buộc dây", "Oxford nam buộc dây | 188.com.vn")
    assert not seo_texts_collide("Oxford nam buộc dây da bò", "Oxford nam buộc dây")


def test_ensure_meta_has_material_usp():
    out = ensure_meta_has_material_usp("Oxford nam buộc dây | 188.com.vn", "Da bò", "Oxford nam")
    assert "da bò" in out.lower()
    assert "188.com.vn" in out.lower()


def test_apply_guardrails_differentiates_from_head():
    seo, warning = apply_ladipage_seo_guardrails(
        {"meta_title": "Oxford nam buộc dây", "meta_description": "Mua oxford nam giá tốt."},
        competitor={
            "head_title": "Oxford nam buộc dây",
            "category_name": "Oxford nam buộc dây",
            "seo_description": "Mua oxford nam giá tốt tại 188.",
        },
        material_filter="Da bò",
        category_name="Oxford nam buộc dây",
    )
    assert "da bò" in seo["meta_title"].lower()
    assert not seo_texts_collide(seo["meta_title"], "Oxford nam buộc dây")
    # Sau guardrail vẫn có thể còn warning mềm hoặc hết — title phải khác head.
    assert seo["meta_title"]
    _ = warning
