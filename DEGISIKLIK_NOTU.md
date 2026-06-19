# Paket 4 (KÜMÜLATİF) — Meta Feed + Kupon + SEO + Taksit + Güven/Teslimat + Taksonomi

> Önceki tüm paketleri içerir. Tek başına deploy edilebilir.

## backend/routes/products.py
- Google feed: item_group_id + color + size (flag; ?group=off / settings.feed_variant_grouping=false). g:id sabit.

## backend/routes/categories.py  (YENİ — P3-18)
- get_categories'e geriye-uyumlu `visible_only` parametresi.
  - Varsayılan False = ADMIN davranışı korunur (tüm kategoriler).
  - True (storefront) = pasif (is_active=False) + test/placeholder kategorileri (HB_CAT_TEST_123 vb.) gizler.
- Test pattern doğrulandı: HB_CAT_TEST_123/CAT_TEST/_test_/test_N gizlenir; Giyim/kontes/fideltest korunur.

## frontend  (YENİ — P3-18)
- SlugRouter.jsx, MiuMiuTheme.jsx (anasayfa), Category.jsx (PLP): /categories çağrılarına ?visible_only=true eklendi.
  → Storefront artık test/pasif kategorileri çekmiyor. Admin paneli etkilenmez.

## frontend/src/pages/Checkout.jsx
- Kupon: otomatik en iyi indirim onayı + katlanır promosyon alanı.
- Güven şeridi (Güvenli ödeme · 3D Secure · 14 gün iade · Gizli ücret yok) + özet panelinde Tahmini teslimat.

## frontend/src/pages/ProductDetail.jsx
- JSON-LD duplicate fix + taksit bilgisi + Sepete Ekle altında görünür Tahmini teslimat.

## frontend/src/pages/Cart.jsx
- Sepet özetinde taksit bilgisi.

## Doğrulama
- products.py + categories.py: ast.parse OK; feed simülasyonu + test pattern doğrulandı.
- Checkout/ProductDetail/Cart/Category/SlugRouter/MiuMiuTheme: esbuild (jsx=automatic) exit 0.

## NOT — slug bug'ı (gi-yi-m) ZATEN düzeltilmiş ✅ (lib/slug.js Türkçe→ASCII map, backend generate_slug ile uyumlu).

## KAPSAM DIŞI (canlı DB, geri alınamaz — körlemesine yapılmadı):
- Duplike kategori (aksesuar + aksesuar-aksesuar) BİRLEŞTİRME + 301: kategori delete HARD-delete olduğu için
  geri alınamaz. İstenirse önce DRY-RUN (sadece raporlayan) bir temizlik scripti hazırlanmalı, onay sonrası uygulanmalı.
- Test kategorisi DB'den fiziksel silme: yukarıdaki filtre storefront'tan gizliyor; kalıcı silme admin panelinden
  veya dry-run script ile yapılabilir.
