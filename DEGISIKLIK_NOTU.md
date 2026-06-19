# Paket: Meta Feed item_group_id + Checkout Kupon Görünüm Sadeleştirme

## 1. backend/routes/products.py — Meta varyasyon gruplaması
- `_build_merchant_xml(..., group_variants=False)` parametresi eklendi.
- Google/generic ürün-seviyesi feed'e her item için EKLENEN alanlar:
  `<g:item_group_id>` (parent = mpn, fallback csv_card_id/urun_karti_id) + `<g:color>` + (tek bedenliyse) `<g:size>`.
- `<g:id>` ve tüm mevcut alanlar AYNEN korunur — sadece ekleme.
- Feature-flag / rollback:
  - settings.main.feed_variant_grouping = false  → kapat (DB)
  - Acil: `?group=off` query param  (ör. .../google-merchant.xml?group=off)
  - Varsayılan: AÇIK
- Kanıtlanan davranış (simülasyon): aynı parent renkler aynı item_group_id'de gruplanıyor,
  çok-bedenli üründe yanlış size basılmıyor, XML well-formed, g:id'ler birebir sabit.

## 2. frontend/src/pages/Checkout.jsx — Kupon görünüm
- "En avantajlı indirim otomatik uygulandı" ✓ yeşil onay başlığı (uygulanan kampanya listesinin üstünde).
- Manuel promosyon alanı KATLANIR yapıldı (Mango usulü): "Promosyon kodun var mı?" linki → tıklayınca açılır.
  Kod zaten uygulanmışsa açık gelir. Kullanıcıyı "kod avına" itmez.
- Kupon motoru (recalcPromotions / removePromotion / handleApplyCoupon) mantığına DOKUNULMADI — sadece görünüm.

## Doğrulama
- products.py: ast.parse OK + feed çıktısı gerçek veriyle simüle edildi (g:id sabit, gruplama doğru, XML geçerli).
- Checkout.jsx: esbuild (jsx=automatic) exit 0, hata yok.
