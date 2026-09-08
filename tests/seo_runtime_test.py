from seo_runtime import render_template, resolve_category, resolve_product


def _config(**seo_patch):
    return {
        "brand": {"store_name": "Örnek Mağaza"},
        "company": {"legal_name": "Örnek A.Ş.", "city": "İstanbul", "country": "Türkiye"},
        "contact": {},
        "domains": {"storefront_url": "https://shop.example.test/"},
        "commerce": {"currency_code": "TRY"},
        "catalog_defaults": {"product_brand": "Örnek"},
        "seo_geo": {
            "auto_generate_products": True,
            "auto_generate_categories": True,
            "default_robots": "index,follow",
            "product_title_template": "{product_name} | {store_name}",
            "product_description_template": "{product_name} - {brand}",
            "category_title_template": "{category_name} | {store_name}",
            "category_description_template": "{category_name}",
            **seo_patch,
        },
    }


def _by_type(result, schema_type):
    return next(item for item in result["jsonld"] if item["@type"] == schema_type)


def test_product_manual_fields_win_and_path_override_wins_last():
    product = {
        "id": "p1", "slug": "keten-ceket", "name": "Keten Ceket",
        "meta_title": "Manuel ürün başlığı", "meta_description": "Manuel ürün açıklaması",
    }
    result = resolve_product(product, _config(), override={"title": "URL başlığı", "noindex": True})
    assert result["title"] == result["og_title"] == "URL başlığı"
    assert result["description"] == "Manuel ürün açıklaması"
    assert result["robots"] == "noindex,nofollow"
    assert result["sources"] == {
        "title": "path_override", "description": "entity_manual", "og_image": "missing"
    }


def test_product_schema_uses_only_present_facts():
    result = resolve_product({
        "id": "p2", "slug": "urun", "name": "Ürün", "images": ["/relative.jpg"],
    }, _config())
    product = _by_type(result, "Product")
    assert result["canonical"] == "https://shop.example.test/urun/urun"
    assert "offers" not in product
    assert "image" not in product
    assert "sku" not in product
    assert result["og_image"] == ""


def test_offer_and_stock_are_emitted_only_from_actual_values():
    cfg = _config()
    unknown_stock = resolve_product({"slug": "a", "name": "A", "price": 125}, cfg)
    offer = _by_type(unknown_stock, "Product")["offers"]
    assert offer["price"] == "125" and offer["priceCurrency"] == "TRY"
    assert "availability" not in offer

    known_stock = resolve_product({
        "slug": "b", "name": "B", "sale_price": 99.5,
        "variants": [{"stock": 0}, {"stock": 2}],
    }, cfg)
    assert _by_type(known_stock, "Product")["offers"]["availability"].endswith("/InStock")


def test_category_has_collection_and_breadcrumb_schema():
    result = resolve_category({"slug": "ceket", "name": "Ceket"}, _config())
    assert result["title"] == "Ceket | Örnek Mağaza"
    assert result["description"] == "Ceket"
    assert result["canonical"] == "https://shop.example.test/kategori/ceket"
    assert _by_type(result, "CollectionPage")["name"] == "Ceket"
    assert len(_by_type(result, "BreadcrumbList")["itemListElement"]) == 2


def test_unknown_template_tokens_and_missing_values_are_not_invented():
    rendered = render_template(
        "{product_name} {unknown_claim} {price} {city}",
        {"product_name": "Çanta", "price": None, "city": ""},
        160,
    )
    assert rendered == "Çanta"
