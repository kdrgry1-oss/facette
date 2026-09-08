import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "amazon_helpers", Path(__file__).parents[1] / "routes" / "amazon_helpers.py"
)
amazon_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(amazon_helpers)


def test_canonical_color_prefers_variant_then_product_and_attributes():
    product = {"color": "Bej", "attributes": [{"name": "Renk", "value": "Siyah"}]}
    assert amazon_helpers.canonical_amazon_color(product, {"color": "Mürdüm"}) == "Mürdüm"
    assert amazon_helpers.canonical_amazon_color(product, {}) == "Bej"
    assert amazon_helpers.canonical_amazon_color(
        {"attributes": [{"name": "Renk", "value": "Acı Kahve"}]}, {}
    ) == "Acı Kahve"
    assert amazon_helpers.canonical_amazon_color({}, {}, "Siyah") == "Siyah"


def test_variant_images_are_first_deduplicated_and_limited_to_amazon_slots():
    product = {
        "main_image": "https://cdn.facette.com.tr/product-main.webp",
        "images": [f"https://cdn.facette.com.tr/p-{i}.webp" for i in range(12)],
    }
    variant = {
        "main_image": "https://cdn.facette.com.tr/color-main.webp",
        "images": ["https://cdn.facette.com.tr/color-main.webp",
                   "https://cdn.facette.com.tr/color-side.webp"],
    }
    images = amazon_helpers.amazon_image_candidates(product, variant)
    assert images[:3] == [
        "https://cdn.facette.com.tr/color-main.webp",
        "https://cdn.facette.com.tr/color-side.webp",
        "https://cdn.facette.com.tr/product-main.webp",
    ]
    assert len(images) == 9


def test_seller_sku_uses_canonical_color_to_prevent_color_collision():
    variant = {"stock_code": "FC100", "size": "M", "barcode": "8691"}
    assert amazon_helpers.build_amazon_seller_sku(variant, {}, "Siyah") == "FC100-Siyah-M"
    assert amazon_helpers.build_amazon_seller_sku(variant, {}, "Acı Kahve") == "FC100-AcıKahve-M"


def test_sibling_query_covers_variant_and_numeric_card_stock_codes():
    query = amazon_helpers.amazon_sibling_query(["FC100", "12345"])
    clauses = query["$or"]
    assert {"variants.stock_code": {"$in": ["FC100", "12345"]}} in clauses
    assert {"variants.sku": {"$in": ["FC100", "12345"]}} in clauses
    assert {"urun_karti_id": {"$in": ["FC100", "12345", 12345]}} in clauses


def test_failure_detail_is_bounded_and_redacts_credentials():
    detail = amazon_helpers.safe_amazon_failure({
        "status": 400,
        "data": {"issues": [{"code": "90220", "message": "access_token=abc123 missing size"}]},
    })
    assert detail == {"code": "90220", "message": "access_token=[REDACTED] missing size", "http": 400}
    assert len(amazon_helpers.safe_amazon_failure(error="x" * 1000)["message"]) == 300


def test_retry_policy_escalates_then_quarantines():
    assert amazon_helpers.amazon_retry_policy(1) == (60, False)
    assert amazon_helpers.amazon_retry_policy(4) == (480, False)
    assert amazon_helpers.amazon_retry_policy(8) == (86400, True)
    assert amazon_helpers.amazon_retry_policy(50) == (86400, True)
