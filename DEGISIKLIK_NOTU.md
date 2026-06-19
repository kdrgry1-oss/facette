# Paket 2 (KÜMÜLATİF) — Meta Feed + Kupon + SEO duplicate fix + Taksit

> Bu paket önceki paketi de içerir. Tek başına deploy edilebilir.

## backend/routes/products.py  (önceki pakettekiyle aynı)
- Google feed'e item_group_id + color + size (flag arkasında, ?group=off / settings.feed_variant_grouping=false ile geri al). g:id sabit.

## frontend/src/pages/Checkout.jsx  (önceki pakettekiyle aynı)
- "En avantajlı indirim otomatik uygulandı" onayı + katlanır promosyon alanı (Mango usulü).

## frontend/src/pages/ProductDetail.jsx  (YENİ)
- JSON-LD duplicate fix: edge middleware (functions/_middleware.js) zaten JSON-LD bastıysa
  client tarafında tekrar EKLEMEZ → Google'da çift Product/Breadcrumb riski kalktı.
- Taksit bilgisi: fiyatın altına "💳 9 taksite kadar · ₺X/ay'dan başlayan taksitlerle" (TR pazarı dönüşüm, P1-8).

## frontend/src/pages/Cart.jsx  (YENİ)
- Sepet özeti Toplam satırının altına taksit bilgisi satırı (P1-8).

## Doğrulama
- products.py: ast.parse OK + feed simülasyonu (g:id sabit, gruplama doğru, well-formed).
- Checkout/ProductDetail/Cart: esbuild (jsx=automatic) exit 0, hata yok.

## Not — zaten mevcut (dokümanın istediği, halihazırda yapılmış)
- index.html: OG/Twitter/canonical + Organization & WebSite JSON-LD ✅
- functions/_middleware.js: ürün/kategori edge OG + Product/Offer/BreadcrumbList JSON-LD ✅
- PDP: beden seçimi, beden tablosu modalı, sticky bar, "Eklendi ✓", "Gelince Haber Ver" ✅
- Sepet: ücretsiz kargo eşiği progress bar ✅
