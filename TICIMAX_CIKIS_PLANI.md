# FACETTE — Ticimax Çıkış Planı (çökme-güvenli)

> Hedef: sıfır senkron, sıfır veri çekme, kod/UI/config/DB'de Ticimax kalmaması.
> **Kural: hiçbir aşamada `server.py` boot'u bozulmaz.** Silme her zaman EN SON, referanslar sıfırlanınca.

---

## 0. NEDEN GEÇEN SEFER ÇÖKTÜ (kök neden)

`server.py` başlangıçta 5 Ticimax router'ını **import ediyor** (satır ~82-86) ve kaydediyor (~611-620):
```
from routes.ticimax_stock_sync import router as ticimax_stock_sync_router
... (category_sync, member_sync, product_pull, returns)
api_router.include_router(ticimax_stock_sync_router)
...
```
Bir Ticimax dosyasını **silersen**, bu import satırı `ImportError` verir → FastAPI app boot edemez → **Railway'de site komple düşer.**
Çözüm: önce import + include'ları temizle, SONRA dosyayı sil. Sıra bozulursa çöker.

---

## 1. YÜZEY HARİTASI (silmeden önce bilinmesi gerekenler)

**Backend — startup-kritik (server.py):** 5 router import + include (stock_sync, category_sync, member_sync, product_pull, returns).
**Backend — dosyalar:** `ticimax_client.py`, `ticimax_order_parser.py`, `ticimax_schema.py`, `ticimax_member_sync.py` + 5 route dosyası. `integrations.py` içinde **15** adet `/ticimax/*` ucu.
**Scheduler:** `_ticimax_sync_orders` (sipariş çekme — **Aşama 1'de KAPATILDI**), `_ticimax_sync_stock` (zaten kapalı). Fonksiyonlar lazy-import; duruyorlar, zararsız.
**Frontend:** ~23 dosya `ticimax` içeriyor. Özel sayfalar: `TicimaxExcelUpload.jsx`, `TicimaxReturns.jsx`; nav: adminNav "Ticimax Excel Yükle"; `AutomationStatus` Ticimax kartı; `Integrations/MarketplaceHub/Orders/Returns` vb.
**DB alanları (DOKUNMA — veri):** `source: "ticimax"`, `imported_from: "ticimax"/"ticimax_cron"`, `ticimax_order_id` (~39 referans). Bunlar geçmiş sipariş verisi; silme/yeniden adlandırma yalnız veri taşıma teyitliyse.

---

## 2. AŞAMALAR (her biri geri alınabilir)

### Aşama 1 — Otomatik veri çekmeyi durdur ✅ (BU PAKET)
- Scheduler'da `ticimax_orders_sync` job kaydı **yorumlandı** (fonksiyon duruyor).
- Stok senkronu zaten kapalıydı.
- **Import bozulmadı, dosya silinmedi → site boot eder.**
- Sonuç: Ticimax'tan otomatik sipariş/stok çekme YOK. Manuel admin uçları hâlâ var ama tetiklenmedikçe çalışmaz.
- **Geri alma:** scheduler'daki bloğu yorumdan çıkar.

### Aşama 2 — UI'dan gizle (kod silmeden)
- adminNav'dan "Ticimax Excel Yükle" girişini kaldır; `AutomationStatus` Ticimax kartını gizle.
- `TicimaxExcelUpload.jsx` / `TicimaxReturns.jsx` route'larını menüden çıkar (dosya dursun).
- Backend route'lara dokunma (çağrılmazsa zararsız).
- **Test:** frontend build (esbuild) geçmeli; menüde Ticimax görünmemeli.

### Aşama 3 — Kaynak etiketi: "Ticimax/TicimaxWeb" → "Site" / "Web"
- Yalnız **gösterim** katmanında (UI label) yap. **DB'deki `source` değerlerini DEĞİŞTİRME** (sipariş kaynağı zaten prefix ile belirleniyor: `TY…`/`HB…`/prefix yok=Site).
- Filtre/sorgularda `source:"ticimax"` kullanan yerleri tek tek gözden geçir; gösterim "Site" olsun, sorgu mantığı bozulmasın.
- **Test:** sipariş listesi kaynak kolonu doğru; mevcut Ticimax kaynaklı siparişler "Site" görünür.

### Aşama 4 — Route'ları devre dışı bırak (dosya silmeden)
- `server.py`'de **önce** `include_router(ticimax_*)` satırlarını yorumla; **sonra** ilgili `import` satırlarını yorumla. İkisi birlikte → `/ticimax/*` uçları 404, ama import yok = hata yok.
- `integrations.py` içindeki 15 `/ticimax/*` ucu: erişilse de kullanılmıyor; istenirse bunlar da kaldırılır (ayrı, dikkatli adım).
- **Test (zorunlu):** `python -c "import server"` benzeri boot denemesi VEYA push sonrası Railway logunda `[scheduler] Background scheduler started` satırını gör. Görünmüyorsa boot patlamıştır → geri al.

### Aşama 5 — Dosyaları sil (EN SON, referans sıfırsa)
- Silmeden önce **şu komutla referans kontrolü** yap:
  ```bash
  grep -rniE "ticimax" backend/server.py backend/scheduler.py
  ```
  Çıktı boşsa (yalnız yorum kalmışsa) silmek güvenli.
- Sırayla sil: önce 5 route dosyası, sonra `ticimax_member_sync.py`, en son `ticimax_client.py / _order_parser / _schema`.
- Her silmeden sonra boot testi.
- DB temizliği (Ticimax kaynaklı kayıtlar / `ticimax_order_id` alanı) **yalnız veri taşıma teyitliyse** ve yedek alındıktan sonra.

---

## 3. HER PUSH ÖNCESİ ÇÖKME-ÖNLEME CHECKLIST
1. `cd backend && python -c "import ast,glob;[ast.parse(open(f).read()) for f in glob.glob('**/*.py',recursive=True)];print('syntax ok')"` → syntax temiz mi.
2. `grep -rniE "ticimax" backend/server.py` → sildiğin dosyaya import kalmış mı (kalmışsa SİLME).
3. Push sonrası Railway logu: `[scheduler] Background scheduler started` göründü mü (boot OK işareti).
4. Site health + bir sipariş sayfası açılıyor mu.
5. Patlarsa: son commit'i revert et (`git revert HEAD`), geri al.

---

## 4. DURUM
- **Aşama 1: TAMAM** (otomatik çekme kapalı, site güvende).
- **Aşama 2: TAMAM** (UI'dan gizlendi — adminNav "Ticimax Excel Yükle" girişi + AutomationStatus "Ticimax" kartı kaldırıldı. **Yalnız frontend**, backend boot'una dokunulmadı, esbuild geçti. Dosyalar ve `/admin/ticimax-excel` route'u duruyor; menüde görünmüyor.)
- Aşama 3-5: onayınla sırayla, her biri ayrı küçük paket + boot testi.
