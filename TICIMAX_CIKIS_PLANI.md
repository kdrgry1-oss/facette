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
- **Aşama 3: TAMAM** (UI temizliği — Entegrasyonlar sayfasındaki "Ticimax" kartı (API key + "Canlı Mod") ve Entegrasyon Logları filtresindeki `ticimax` seçeneği kaldırıldı. Sipariş kaynak etiketi zaten "Web" gösteriyordu (Orders rozeti `Web`; kaynak filtresinde ticimax yok) → DB `source` değerlerine ve sorgu mantığına **dokunulmadı**. `TicimaxReturns` bileşeni "Web Sitesi" iade akışını çalıştıran **aktif** bileşendir → DOKUNULMADI. Yalnız frontend, esbuild geçti.)
- **Aşama 4 (kısmi): TAMAM** (ilk backend dokunuşu — `server.py`'de `ticimax_category_sync` / `ticimax_member_sync` / `ticimax_product_pull` router'larının **import + include** satırları `# [A4-ticimax-off]` ile yorumlandı. Bu 3 değişken yalnız server.py'de kullanılıyor + uçlarının aktif frontend çağıranı yok → boot patlamaz. **stock_sync KORUNDU** (AutomationStatus'taki "Ticimax Stok Senkronla" butonu hâlâ `/admin/ticimax/sync-stock` çağırıyor). **returns KORUNDU** (aktif "Web Sitesi" iade akışı `/admin/ticimax/return-orders`, `/orders/refresh-dates`, `/returns/{id}/open`, `/return-orders/export` kullanıyor). Boot gate: Railway logunda `[scheduler] Background scheduler started`.)
- **Aşama 4b: TAMAM** (AutomationStatus'tan `ManualSyncButtons` ("Ticimax Stok Senkronla") render+fonksiyonu kaldırıldı **+** `ticimax_stock_sync` router'ı (import+include) `# [A4b-ticimax-off]` ile kapatıldı. Frontend+backend aynı paket, **kümülatif** (server.py Aşama 4 değişikliklerini de içerir). Artık **yalnız `ticimax_returns_router` aktif** (site iade akışı). esbuild + ast.parse geçti. Boot gate: Railway `[scheduler] Background scheduler started`.)
- **Aşama 4c:** `integrations.py` içindeki ~15 `/ticimax/*` ucu — **AMA** returns akışının kullandığı `/integrations/ticimax/orders/import` HARİÇ. Dikkatli, ayrı adım.
- **Aşama 5a: TAMAM (kısmi silme)** — referanssız 3 route dosyası silindi: `routes/ticimax_category_sync.py`, `routes/ticimax_member_sync.py`, `routes/ticimax_product_pull.py`. (server.py importları Aşama 4'te yorumlu olduğu için boot'a etkisi yok. `git rm` ile; önce `grep ^[^#]*ticimax_(category_sync|member_sync|product_pull) server.py` boş çıktığı doğrulandı.)

---

## 5. READ-ONLY ANALİZ — TAM ÇIKIŞ NEDEN TEK HAMLE DEĞİL

Ticimax çekirdek modülleri **aktif koda bağlı**, hemen silinemez:
- `ticimax_schema.py` → `routes/products.py` **boot'ta top-level** `from ticimax_schema import BOOL_COLS` yapıyor. Silersen ImportError → site açılmaz. (önce products.py'den koparılmalı)
- `ticimax_client.py`, `ticimax_order_parser.py` → aktif sipariş import + iade akışı (lazy import) kullanıyor.

`integrations.py`'deki 15 `/ticimax/*` ucundan bazıları **hâlâ aktif sayfalardan çağrılıyor:**
- `Categories.jsx` → `/ticimax/categories/sync-missing-from-products`
- `Products.jsx` → `/ticimax/teknik-detay/sync`
- `TicimaxReturns` (site iade) → `/ticimax/orders/import`, `/admin/ticimax/return-orders`
- `Integrations.jsx` → `/ticimax/status` (sayfa açılışında hâlâ GET; kart kaldırıldı ama handler/effect kaldı — kozmetik)

**Kalan silinemez:** `ticimax_stock_sync.py` (scheduler.py:619 lazy ref — önce o satır temizlenmeli), çekirdek 3 modül, integrations.py uçları, `models.py: ticimax_fields` (ÜRÜN VERİSİ — DOKUNMA).

### TAM ÇIKIŞ İÇİN GÜVENLİ SIRA (büyük iş, ayrı ayrı paketler)
1. **Aktif uçları yeniden adlandır — Aşama 5b: TAMAM (doğrulandı + sed).** İki uç INCELENDI, ikisi de **YEREL** (Ticimax API'sine gitmiyor):
   - `/ticimax/categories/sync-missing-from-products` → ürünlerin `category_name`'inden eksik kategorileri yerel DB'ye ekler (docstring: "Ticimax API'sini tekrar çağırmadan"). **→ `/site/categories/sync-missing-from-products`**
   - `/ticimax/teknik-detay/sync?use_cache=true` → yerel `ticimax_attribute_master` cache'inden ürün özelliklerini metin eşleştirir (buton hep use_cache=true; SOAP yalnız use_cache=false'ta, kullanılmıyor). **→ `/site/teknik-detay/sync`**
   - Yeniden adlandırma sed ile (backend decorator + tek frontend çağıran birlikte). Her uç tek çağıranlı (doğrulandı), çakışma yok, ast.parse+esbuild geçti. **NOT:** `db.ticimax_attribute_master` koleksiyonu ve `scripts/enrich_attrs_from_ticimax_master.py` adı hâlâ "ticimax" — bunlar VERİ/script, sonraki kozmetik pas.
2. **Returns akışını yeniden adlandır:** `/admin/ticimax/*` → `/admin/site-iade/*` + `/ticimax/orders/import` bağımlılığını çöz (tek atomik backend+frontend paket).
3. **Integrations.jsx ölü handler/effect temizliği** (frontend, güvenli).
4. **scheduler.py** ölü `_ticimax_sync_orders` / `_ticimax_sync_stock` fonksiyonlarını kaldır → `ticimax_stock_sync.py` silinebilir hale gelir.
5. **Çekirdek koparma:** products.py'den `ticimax_schema` importunu çöz → schema/client/parser silinebilir.
6. **EN SON:** `models.py: ticimax_fields` yalnız veri taşıma teyitliyse ve yedekle.

> Her adım: ast.parse + (frontend) esbuild + push sonrası Railway `[scheduler] Background scheduler started` + ilgili sayfa açılış testi.

---

## 6. REBRAND İZİ — "ticimax" → "Rooftr" (de-branding)

[KARAR] Sahip: *"adı ticimax olan herşeyi rooftr yap."* "rooftr" yazımı teyitli.
Bu iz, ÇIKIŞ izinden ayrı: çıkış = işlevi söker; rebrand = kalan "ticimax" adlarını **Rooftr** yapar. Aşamalı + çökme-güvenli.

### A/B AYRIMI (zorunlu — körlemesine global rename YASAK)
**🟢 Grup A — KOD (Rooftr yapılır, aşamalı):** dosya adları (`ticimax_*.py`, `Ticimax*.jsx`), fonksiyon/değişken adları, route yolları, yorumlar, **UI metinleri**, log mesajları.
**🔴 Grup B — VERİ (kodda DOKUNULMAZ; rename = veri uyumsuzluğu → "veriyi koruma" kuralını bozar):**
- `ticimax_fields` → ürün dökümanı alanı, AKTİF (URUNKARTIID, filtre `tf_/tfmin_`, arama; products.py 403-1379).
- `db.ticimax_attribute_master` → koleksiyon adı (category_mapping.py 1162/1817, integrations.py 5148).
- `source:"ticimax"`, `imported_from:"ticimax_cron"`, `ticimax_order_id` → mevcut siparişlerde kayıtlı (integrations.py 4871/5173/5561/5833/5901+).
> Grup B yalnız ileride **yedekli, ayrı, riskli DB migration** ile çevrilir. Kodda asla.

### R-AŞAMALARI (güvenliden riskliye)
- **R1 — Görünür UI metinleri → Rooftr: TAMAM (esbuild geçti).**
  - `TicimaxReturns.jsx` (Returns "Web Sitesi" sekmesinde aktif): 5 toast/tooltip/empty-state metni `Ticimax'tan…` → `Rooftr'dan…`; empty-state buton referansı gerçek etiketle eşitlendi ("Siparişleri Çek").
  - `TicimaxExcelUpload.jsx`: başlık "Ticimax Excel Ürün Aktarımı" → "Rooftr Excel Ürün Aktarımı"; "TicimaxExport" → "RooftrExport".
  - Kapsam DIŞI (bilerek): Integrations.jsx 344-445 toast'ları = ölü handler (kart Aşama 3'te kaldırıldı, tetiklenmez) → R3'te komple silinecek. Identifier/yorum/route → sonraki R-aşamaları.
- **R2 — route yolları `/ticimax/*` → `/rooftr/*` (returns alt-sistemi): TAMAM (ast.parse+esbuild geçti).**
  - `ticimax_returns.py` prefix `/admin/ticimax` → `/admin/rooftr` (stock_sync 4b'de kapalı → çakışma yok).
  - `integrations.py` `/ticimax/orders/import` → `/rooftr/orders/import` (path-classifier `/orders/import` substring'iyle korunur).
  - Çağıranlar: `TicimaxReturns.jsx` 6 yol (return-orders, orders/import, refresh-dates, export, returns/open ×2) + `Integrations.jsx:410` (ölü, tutarlılık).
  - **Kalan `/integrations/ticimax/*` route'ları (status, categories/import, products/import, test-connection, members/import vb.) DOKUNULMADI** → hepsi ölü Integrations handler'larından çağrılıyor, R3'te handler'larıyla silinecek.
- **R3 — Ölü kod temizliği: TAMAM (ast.parse + esbuild geçti).**
  - Backend: `integrations.py`'den 10 ölü `/ticimax` route silindi (status, settings, categories/import, variants/sync, test-connection, products/import, members/import, link-orders-to-users, members/import-excel, members) — ast tabanlı, hepsinin iç çağrısı yok doğrulandı (9087→7990 satır).
  - Frontend: `Integrations.jsx` tamamen ticimax'tan arındı (0 referans) — 5 ölü handler (Categories/Products/TestConnection/Orders/Members) + state (`ticimaxImporting*`, `ticimaxStatus`) + status-effect'teki `/ticimax/status` fetch + `statuses.ticimax` anahtarı kaldırıldı. Promise.all 7→6, destructuring hizalı, Trendyol/HB/Temu/iyzico/xml/doğan'a dokunulmadı.
  - Korunanlar: `/rooftr/orders/import` (returns), `/ticimax/products/upload-excel` (Excel sayfası — R-sonra), `/ticimax/orders/backfill` (caller belirsiz — R-sonra).
- **R4 — fonksiyon/değişken + dosya adları (alt-aşamalara bölündü, güvenliden riskliye):**
  - **R4a — frontend dosya adları: TAMAM (esbuild geçti, boot riski YOK).**
    - `git mv`: `TicimaxReturns.jsx`→`RooftrReturns.jsx`, `TicimaxExcelUpload.jsx`→`RooftrExcelUpload.jsx` (frontend/src/pages/admin/).
    - Internal `export default function` adları + import'lar: `Returns.jsx:7,108,450` (import+yorum+JSX) + `AdminApp.jsx:84,101` (import+JSX+route `path="ticimax-excel"`→`"rooftr-excel"`).
    - Repo'da `TicimaxReturns`/`TicimaxExcelUpload` referansı **0**. Kalan ticimax (boot/import DEĞİL → sonraki): `pullFromTicimax` fonksiyon adı + yorumlar + `/ticimax/products/upload-excel` API çağrısı + `data-testid="ticimax-excel-*"`.
  - **R4b — `/ticimax/products/upload-excel` → `/rooftr`: TAMAM (ast.parse + esbuild geçti, boot-safe).** Decorator + fonksiyon adı `upload_ticimax_products_excel`→`upload_rooftr_products_excel` + `RooftrExcelUpload.jsx:29` caller. Classifier güvenli (`server.py:453` `/products/` substring → product_push korunur). **`/ticimax/orders/backfill` DOKUNULMADI:** frontend/scheduler caller YOK (scheduler'daki backfill'ler hep Trendyol), işlevsel olarak Ticimax-SOAP çıkış-izi endpoint'i → rename = churn; ÇIKIŞ izinde silinecek.
  - **R4c (BOOT-KRİTİK, en son, AYRI) — backend dosya adları** `ticimax_returns.py`/`ticimax_schema.py`/`ticimax_client.py`/`ticimax_order_parser.py` → rename. **DİKKAT:** `products.py:10` top-level `from ticimax_schema import BOOL_COLS` + `server.py:86` `from routes.ticimax_returns import` → dosya adı AYNI commit'te import zinciriyle düzelmezse **BOOT PATLAR**. NOT: schema/client/parser çıkış izinde silinecek adaylar → rename yerine çıkışta silmek daha mantıklı olabilir (churn'den kaçın).
  - **R4d — sahibi-biz olan dosyaların kozmetik temizliği: TAMAM (esbuild geçti, boot riski yok).** `RooftrReturns.jsx` (`pullFromTicimax`→`pullFromRooftr` + 3 yorum) + `RooftrExcelUpload.jsx` (`data-testid="ticimax-excel-*"`→`rooftr-excel-*`). Bu 2 dosya artık **%100 ticimax-free**.
  - **R4d-KALAN — KASITLI BIRAKILDI (körlemesine rename YASAK kuralı / A-B ayrımı):**
    - `lib/img.js: static.ticimax.cloud` = Ticimax'ın **gerçek görsel CDN host'u** → değiştirmek Ticimax-barındırılan TÜM ürün görsellerini kırar. **DOKUNULMAZ.** *(Exit notu: görseller hâlâ kısmen Ticimax altyapısında; R2 `cdn.facette.com.tr` taşıması AYRI iş — Ticimax hesabı kapanırsa o görseller ölür.)*
    - `Products.jsx: ticimax_fields / ticimaxSchema / /products/meta/ticimax-schema` + `Categories.jsx: ticimax_id` = **Grup B veri/şema** (ürün formu buna bağlı). **DOKUNULMAZ.**
    - "Ticimax tarzı/aynası/benzeri" yorumları (ProductFilters/BrandMapping/FailedTransfers/MarketplaceHub/Orders vb.) = UI'ların Ticimax panellerinden örneklendiğini anlatan **tarihsel-doğru** yorumlar → "Rooftr" yapmak yanlış olur. Bırakıldı.
> Grup B (veri) tüm R-aşamalarında ELLENMEZ.

---

## 7. PERFORMANS (PageSpeed) İYİLEŞTİRME — EN SON (rebrand + stabilite bitince)

[KARAR] Sahip: *"page speed'i 100 yap ya da plana al, en son yapalım."* → **Plana alındı, en son.**

### Gerçekçi hedef (dürüst beyan)
**Mobil 100 bu mimaride GERÇEKÇİ DEĞİL.** Site CRA **client-render SPA** (`<div id="root">` boş geliyor) — mobil önce JS indirip parse edip render ediyor, içerik ondan sonra. Mobil 100 ancak SSR/prerender ile olur (mimari değişim).
- Gerçekçi: **mobil 43 → 75-85**; **masaüstü 95-100**.
- 90+ mobil: homepage prerender/SSR (büyük iş, ayrı proje).

### Mevcut ölçüm (22 Haz 2026, curl)
- `<div id="root">` boş → client-render SPA (asıl darboğaz).
- `main.js` = **412 KB ham / 128 KB gzip, tek parça** (homepage'de ayrı chunk yok) → mobil CPU parse'ı ana iş parçacığını bloke eder (yüksek TBT).
- `main.css` = 23 KB gzip (render-blocking, normal).
- 3rd-party: **GTM** (`GTM-THJQQDL`, head) + **PostHog `session_recording` AÇIK** (pahalı) + muhtemelen Meta Pixel (GTM üzerinden).
- **İyi olanlar — DOKUNMA:** Inter fontu async (preload+onload+noscript), preconnect/dns-prefetch (cdn/fonts/gtm/posthog), JS `defer`, lazy route'lar, SEO 100 / Best Practices 96.

### Öncelikli düzeltmeler (etki/risk — sırayla, tek tek test)
1. **3rd-party hafiflet (en kolay, en yüksek getiri, düşük risk):** PostHog `session_recording` kapat veya örnekle (örn %10); GTM+PostHog'u ilk etkileşim/idle sonrası geç-yükle → TBT düşer.
2. **JS bundle küçült/böl (412 KB):** içindeki ağır lib'leri tespit + route/komponent lazy → parse süresi.
3. **Homepage prerender (react-snap):** boş `#root` yerine anında içerik → LCP/FCP en büyük kazanım (en çok iş).
4. **Hero/ilk ürün görselleri:** WebP/AVIF + LCP görseline `fetchpriority="high"` + `srcset` + alt-fold `loading="lazy"`.
> Storefront değişiklikleri boot riski taşımaz; ama her deploy sonrası **hard-refresh + gerekirse Cloudflare cache purge** (CSS/cache yarışı = "görünüm bozuldu" belirtisinin kök nedeni, kod değil).

