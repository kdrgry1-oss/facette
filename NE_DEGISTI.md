# FACETTE — düzeltme paketi (kümülatif)

## YENİ: Ürün görsellerini SÜRÜKLE-BIRAK ile yükleme
- frontend/src/pages/admin/Products.jsx — "Ürün Galerisi" kartının her yerine OS'tan dosya
  sürükleyip bırakarak yükleme eklendi. Sürüklerken turuncu kesikli "Görselleri buraya bırakın"
  vurgusu çıkar; boş galeride büyük bir bırakma alanı (tıklayınca da dosya seçici açılır) gösterilir.
  Yükleme çekirdeği `uploadImageFiles()` olarak ayrıldı (buton + bırakma aynı kodu kullanır;
  sadece image/* kabul, diğer dosyalar atlanır). Mevcut "sürükleyerek SIRALAMA" özelliği korunur;
  dosya-sürüklemesi ile sıralama-sürüklemesi birbirine karışmaz.

## (Önceki) 5 maddelik düzeltmeler
1. Görsel yüklenmiyor — `API.replace('/api','')` bozuk URL üretiyordu; `BACKEND_ORIGIN` + `fixImg()`
   ile düzeltildi + ayrı `imageInputRef` + R2 sertleştirme (r2_storage/upload).
2. Renk başına BENZERSİZ Ürün Kart ID (products.py + Products.jsx). Mevcut çiftler için tek seferlik:
   `cd backend && python -m scripts.dedupe_card_ids`  (DRY-RUN) → `... --apply` (uygula).
3. Yeni üründe Teknik Detay paneli gizli + resetForm temizliği.
4. AI açıklama önizlemesi düzenlenebilir (contentEditable) + index.css placeholder.
5. Kargo barkodu → durum "Hazırlanıyor"; "Kargoya Verildi" scheduler'da gerçek DHL takip kodu gelince.

Deploy sonrası yeşil sinyal: `[scheduler] Background scheduler started`
