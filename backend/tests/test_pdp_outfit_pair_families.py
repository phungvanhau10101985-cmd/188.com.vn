from unittest.mock import patch

from app.services.pdp_outfit_pair_families import (
    infer_pair_family,
    listing_queries_for_family,
    pair_family_compatible,
)
from app.services.pdp_outfit_suggestions import (
    filter_stored_outfit_payload,
    invalidate_outfit_cache_for_product,
    persisted_outfit_is_fresh,
    score_outfit_candidate,
)
from app.services.pdp_outfit_visual import (
    build_visual_context,
    color_harmony,
    cosine,
    nano_image_scores_for_anchor,
    vector_from_color_families,
)


def test_ao_khoac_and_vest_combo_is_not_formal_top():
    assert (
        infer_pair_family(
            "Thời trang Nam",
            "Áo khoác & vest Nam",
            "áo khoác bomber nam thể thao, năng động",
            "Áo khoác golf nam PGM",
        )
        != "formal_top"
    )


def test_infer_giay_tay_and_vest():
    assert infer_pair_family("Giày dép Nam", "Giày tây nam", "Giày oxford") == "formal_shoe"
    assert infer_pair_family("Thời trang Nam", "Áo vest nam", "Áo vest") == "formal_top"
    assert infer_pair_family("Thời trang Nam", "Áo sơ mi nam", "Áo sơ mi dài tay") == "formal_top"
    assert infer_pair_family("Giày dép Nam", "Sneaker nam", "Giày chạy") == "sport_shoe"
    assert infer_pair_family("Thời trang Nam", "Áo hoodie nam", "Hoodie") == "casual_top"


def test_sport_shoe_dress_allows_skirt():
    assert pair_family_compatible("sport_shoe", "skirt", "dress") is True
    assert pair_family_compatible("casual_shoe", "dress_casual", "dress") is True


def test_formal_shoe_allows_vest_rejects_hoodie():
    assert pair_family_compatible("formal_shoe", "formal_top", "top") is True
    assert pair_family_compatible("formal_shoe", "casual_top", "top") is False
    assert pair_family_compatible("formal_shoe", "formal_bottom", "bottom") is True
    assert pair_family_compatible("formal_shoe", "sport_bottom", "bottom") is False


def test_unknown_family_does_not_block():
    assert pair_family_compatible(None, "casual_top", "top") is True
    assert pair_family_compatible("formal_shoe", None, "top") is True


def test_listing_queries_include_vest_for_tay():
    qs = listing_queries_for_family("formal_shoe", "top")
    assert "áo vest" in qs
    assert "áo sơ mi" in qs
    assert "blazer" in qs


def test_brown_oxford_allows_white_shirt():
    class _P:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    shoe = _P(
        name="Giày oxford nam da nâu",
        category="Giày dép Nam",
        subcategory="Giày tây nam",
        sub_subcategory="Giày oxford",
        style="công sở",
        occasion="đi làm",
        color="nâu",
        colors=None,
        material="da",
        price=800000,
        purchases=10,
    )
    shirt = _P(
        name="Áo sơ mi nam trắng",
        category="Thời trang Nam",
        subcategory="Áo sơ mi nam",
        sub_subcategory="Áo sơ mi dài tay",
        style="công sở",
        occasion="đi làm",
        color="trắng",
        colors=None,
        material="vải",
        price=350000,
        purchases=4,
    )
    hoodie = _P(
        name="Áo hoodie nam thể thao",
        category="Thời trang Nam",
        subcategory="Áo hoodie nam",
        sub_subcategory="Hoodie",
        style="casual",
        occasion="dạo phố",
        color="đen",
        colors=None,
        material="nỉ",
        price=280000,
        purchases=900,
    )
    ss, _ps, rs = score_outfit_candidate(shoe, shirt, slot="top")
    sh, _ph, _rh = score_outfit_candidate(shoe, hoodie, slot="top")
    assert ss >= 3
    assert any("vest" in x.lower() or "sơ mi" in x.lower() or "giày tây" in x.lower() for x in rs)
    assert sh == 0


def test_visual_context_skips_network_without_cache():
    class _P:
        id = 99
        name = "Giày tây nam da đen"
        color = "đen"
        colors = None
        main_image = "https://example.com/shoe.jpg"
        images = None
        gallery = None

    with patch("app.services.pdp_outfit_visual.post_image_search", create=True), patch(
        "app.services.nanoai_partner_search.post_image_search"
    ) as post, patch("app.services.pdp_outfit_visual.fetch_image_bytes") as fetch:
        ctx = build_visual_context(None, _P(), allow_network=False)
        scores = nano_image_scores_for_anchor(None, _P(), allow_network=False)
        assert ctx.anchor_vector
        assert scores == {}
        post.assert_not_called()
        fetch.assert_not_called()


def test_invalidate_outfit_cache_prefix():
    from app.services import pdp_outfit_suggestions as svc

    svc._CACHE[f"{svc._CACHE_VER}:12"] = (9e12, {"applicable": True, "slots": []})
    svc._CACHE[f"{svc._CACHE_VER}:13"] = (9e12, {"applicable": True, "slots": []})
    invalidate_outfit_cache_for_product(12)
    assert f"{svc._CACHE_VER}:12" not in svc._CACHE
    assert f"{svc._CACHE_VER}:13" in svc._CACHE
    svc._CACHE.pop(f"{svc._CACHE_VER}:13", None)


def test_persisted_outfit_freshness_and_filter():
    from datetime import datetime, timedelta, timezone

    from app.services import pdp_outfit_suggestions as svc

    now = datetime.now(timezone.utc)
    assert persisted_outfit_is_fresh(svc._CACHE_VER, now)
    assert not persisted_outfit_is_fresh("old", now)
    assert not persisted_outfit_is_fresh(svc._CACHE_VER, now - timedelta(days=8))

    payload = {
        "applicable": True,
        "reason": None,
        "anchor": {"id": 1, "role": "shoes"},
        "slots": [
            {"id": "top", "label": "Áo", "items": [{"id": 11}, {"id": 12}, {"id": 13}]},
            {"id": "dress", "label": "Váy", "items": [{"id": 21}]},
        ],
    }
    only_top = filter_stored_outfit_payload(payload, only_slot="top", limit=2)
    assert [s["id"] for s in only_top["slots"]] == ["top"]
    assert [i["id"] for i in only_top["slots"][0]["items"]] == [11, 12]


def test_build_reads_persisted_picks_without_compute():
    from app.services.pdp_outfit_suggestions import build_outfit_slot_picks

    stored = {
        "applicable": True,
        "reason": None,
        "anchor": {"id": 88, "role": "shoes", "role_label": "Giày", "gender": "Nam", "title": "Phối"},
        "slots": [{"id": "top", "label": "Áo", "listing_params": {}, "items": [{"id": 501, "match_score": 4, "reasons": []}]}],
    }

    class _P:
        id = 88
        category = "Giày dép Nam"
        subcategory = None
        sub_subcategory = None
        name = "Giày tây nam"

    with patch("app.services.pdp_outfit_suggestions.load_persisted_outfit_picks", return_value=stored), patch(
        "app.services.pdp_outfit_suggestions._compute_outfit_slot_picks"
    ) as compute, patch("app.services.pdp_outfit_suggestions.save_persisted_outfit_picks") as save, patch(
        "app.services.pdp_outfit_suggestions.schedule_outfit_visual_warm"
    ):
        out = build_outfit_slot_picks(None, _P(), limit=6)
        compute.assert_not_called()
        save.assert_not_called()
        assert out["applicable"] is True
        assert out["slots"][0]["items"][0]["id"] == 501


def test_color_harmony_neutral_and_contrast():
    assert color_harmony({"brown"}, {"white"}) >= 0.7
    assert color_harmony({"blue"}, {"brown"}) >= 0.8
    assert cosine(vector_from_color_families({"black"}), vector_from_color_families({"black"})) > 0.99
    assert cosine(vector_from_color_families({"black"}), vector_from_color_families({"white"})) < 0.55
