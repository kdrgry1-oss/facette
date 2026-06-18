# FACETTE — Ürün ID + Çoğalt Paketi (cumulative)

Bu paket önceki "çoğalt" paketini de içerir → **sadece bunu deploy et**, yeter.

## Değişen dosyalar
- `backend/routes/deps.py`            → urun_id üreticisi (build_used_urun_id_set, next_urun_id)
- `backend/routes/products.py`        → duplicate + assign-variant-ids + create'te urun_id otomatik atama
- `frontend/src/pages/admin/Products.jsx` → "Kopyala" düzeltildi + modalda "Ürün ID" düzenlenebilir

## Yeni davranışlar
1. **Ürün ID (beden) düzenlenebilir** — "Beden Varyantları" modalında Ürün ID artık input.
   Değiştirip KAYDET'e basınca kaydolur.
2. **Yeni üründe otomatik Ürün ID** — ürün oluşturulurken (create) urun_id'si BOŞ olan her
   bedene, sistemdeki EN YÜKSEK urun_id + 1'den başlayıp +1 ilerleyerek (mevcut olanları
   atlayarak) değer atanır. Barkod mantığının aynısı.
3. **Çoğalt (Kopyala)** — backend'de düzgün çalışıyor: her kopyaya yeni benzersiz Ürün Kart ID,
   yeni benzersiz barkodlar ve yeni urun_id'ler atanır (orijinalle çakışmaz). stock_code aynı kalır.

## Deploy
```
cd ~/Downloads/facette_deploy && unzip -o ~/Downloads/facette_urunid_paket.zip -d . \
  && git add -A && git commit -m "feat(products): urun_id düzenlenebilir + create'te otomatik atama; duplicate düzeltme" && git push
```

## Tek seferlik — Siyah bermuda şort beden id'leri (istersen)
(assign-variant-ids endpoint'i bu pakette de var.)
```
curl -X POST https://api.facette.com.tr/api/products/assign-variant-ids \
  -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" \
  -d '{"name":"bermuda","color":"siyah","map":{"S":"8618","XS":"8620","XL":"8619","M":"8617","L":"8616"}}'
```
Not: Artık modalda elle de girebilirsin; bu endpoint sadece toplu/hızlı çözüm.
