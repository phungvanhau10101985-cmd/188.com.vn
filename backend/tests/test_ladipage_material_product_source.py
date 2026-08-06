# backend/tests/test_ladipage_material_product_source.py
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import ladipage_ai_service as svc


def _product(*, pid: int = 42, main_image: str = "https://cdn.example/main.jpg") -> SimpleNamespace:
    return SimpleNamespace(
        id=pid,
        name="Giày test",
        main_image=main_image,
        images=["https://cdn.example/gallery.jpg"],
        gallery=[],
        colors=[],
        material="Da bò",
        is_active=True,
    )


def test_material_section_product_source_skips_ai_image():
    ladipage = SimpleNamespace(
        id=1,
        source_type="products",
        product_ids=[42],
        category_id=None,
        admin_brief="",
        title="Test",
        include_material=True,
        include_faq=True,
        products_limit=12,
    )
    section = SimpleNamespace(
        section_type="material",
        data={"image_source": "product"},
    )
    db = MagicMock()

    with patch.object(svc, "resolve_products_for_ladipage", return_value=[_product()]):
        with patch.object(svc, "build_context", return_value={"dominant_material": "Da bò", "is_single_product": True}):
            with patch.object(
                svc,
                "generate_material_text",
                return_value={"body": "Mô tả", "callouts": ["A", "B", "C"]},
            ):
                with patch.object(svc, "generate_material_image") as gen_img:
                    out = svc.generate_or_regenerate_section(db, ladipage, section, target="all")

    gen_img.assert_not_called()
    assert out["image_source"] == "product"
    assert out["image_url"] == "https://cdn.example/main.jpg"
    assert out["body"] == "Mô tả"


def test_material_section_ai_source_still_generates_image():
    ladipage = SimpleNamespace(
        id=1,
        source_type="products",
        product_ids=[42],
        category_id=None,
        admin_brief="",
        title="Test",
        include_material=True,
        include_faq=True,
        products_limit=12,
    )
    section = SimpleNamespace(section_type="material", data={"image_source": "ai"})
    db = MagicMock()

    with patch.object(svc, "build_context", return_value={"dominant_material": "Da bò"}):
        with patch.object(
            svc,
            "generate_material_text",
            return_value={"body": "Mô tả", "callouts": ["A"]},
        ):
            with patch.object(
                svc,
                "generate_material_image",
                return_value={"image_url": "https://cdn.188.com.vn/site/ladipage/1/x.png"},
            ) as gen_img:
                out = svc.generate_or_regenerate_section(db, ladipage, section, target="all")

    gen_img.assert_called_once()
    assert out["image_source"] == "ai"
    assert "ladipage" in out["image_url"]


def test_material_section_defaults_to_product_without_image_source():
    ladipage = SimpleNamespace(
        id=1,
        source_type="products",
        product_ids=[42],
        category_id=None,
        admin_brief="",
        title="Test",
        include_material=True,
        include_faq=True,
        products_limit=12,
    )
    section = SimpleNamespace(section_type="material", data={})
    db = MagicMock()

    with patch.object(svc, "resolve_products_for_ladipage", return_value=[_product()]):
        with patch.object(svc, "build_context", return_value={"dominant_material": "Da bò"}):
            with patch.object(
                svc,
                "generate_material_text",
                return_value={"body": "Mô tả", "callouts": ["A"]},
            ):
                with patch.object(svc, "generate_material_image") as gen_img:
                    out = svc.generate_or_regenerate_section(db, ladipage, section, target="all")

    gen_img.assert_not_called()
    assert out["image_source"] == "product"
    assert out["image_url"] == "https://cdn.example/main.jpg"
