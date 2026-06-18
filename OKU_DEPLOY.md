# FACETTE — Çoğalt (Duplicate) Paketi

## Değişen dosyalar
- `backend/routes/products.py`  → 2 yeni endpoint
- `frontend/src/pages/admin/Products.jsx`  → "Kopyala" butonu artık yeni endpoint'i çağırıyor

## Ne düzeltildi
Eski `handleDuplicate` ürünü TÜM varyantlarıyla (eski barkodlar) ve AYNI kart id ile
kopyalıyordu → barkod çakışması + aynı kart id ("çoğaltamadın" sebebi buydu).

Artık çoğaltma backend'de yapılıyor:
- Her kopyaya **YENİ ve benzersiz Ürün Kart ID** atanır (her seferinde farklı; paylaşılmaz).
- Tüm varyantlara **aralıktan yeni benzersiz barkod** üretilir (orijinalle çakışmaz).
- Varyant id'leri yenilenir, Ticimax varyant id'si (urun_id) temizlenir.
- `stock_code` aynı bırakılır (aynı modelin başka rengini açmak pratik olsun diye;
  kopyada elle değiştirebilirsin).
- Kopya orijinalin renk-kardeşi DEĞİLDİR (csv_card_id = yeni kart id).

## Deploy
```
cd ~/Downloads/facette_deploy && unzip -o ~/Downloads/facette_cogalt_paket.zip -d . \
  && git add -A && git commit -m "feat(products): duplicate endpoint (yeni kart id + yeni barkod) + assign-variant-ids" && git push
```

## Deploy sonrası — Siyah bermuda şort beden id'leri (tek seferlik)
Beden → urun_id eşlemesi: S=8618, XS=8620, XL=8619, M=8617, L=8616
Sadece urun_id'si BOŞ olan varyantlara yazar (doluyu ezmez).

İsimle (en kolay):
```
curl -X POST https://api.facette.com.tr/api/products/assign-variant-ids \
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" \
  -d '{"name":"bermuda","color":"siyah","map":{"S":"8618","XS":"8620","XL":"8619","M":"8617","L":"8616"}}'
```
Veya kesin olsun istersen ürün id'siyle:
```
  -d '{"product_id":"<URUN_ID>","map":{"S":"8618","XS":"8620","XL":"8619","M":"8617","L":"8616"}}'
```
Dönen `updated_variants` sayısını kontrol et (5 olmalı).

## Henüz YAPILMADI (senin onayını bekliyor)
- **FCSS0600012 — Ticimax'ten çekme:** Ticimax çıkış planı gereği yeni Ticimax
  bağlantısı/coupling eklemiyorum ve canlı çekimi ben tetikleyemem (senin Ticimax
  anahtarın + sunucu tarafı). Mevcut `ticimax_product_pull` aracını bu stok koduna
  yönlendirmemi istersen söyle, stok-kodu filtresi var mı bakıp tek çağrıyı vereyim.
