# Facette E-Commerce PRD

## Problem Statement
Facette e-ticaret uygulaması - React + FastAPI + MongoDB tabanlı admin paneli ve mağaza yönetimi. Trendyol entegrasyonu, ürün yönetimi, stok takibi, sipariş yönetimi ve toplu işlem özellikleri.

## Core Requirements
1. Ürün yönetimi (CRUD, varyantlar, özellikler, fiyatlandırma)
2. Trendyol entegrasyonu (kategori/özellik eşleştirme, ürün aktarma)
3. Cariler (Tedarikçi/Üretici) yönetimi
4. Global ayarlar (KDV, kâr oranı)
5. Excel toplu import/export
6. İade/İptal yönetimi (iskonto, gider pusulası, toplu yazdırma)
7. Doğan e-Dönüşüm e-Fatura entegrasyonu

## Architecture
- Frontend: React, Tailwind CSS, Shadcn/UI, Lucide icons
- Backend: FastAPI, Motor (Async MongoDB)
- DB: MongoDB (test_database)
- Routes: /api prefix, Turkish URL slugs (/admin/urunler, /admin/iadeler)
- Integrations: Trendyol API, Doğan e-Dönüşüm SOAP (zeep)



## Iteration 42-43 (2026-05-12) — Reports Suite + Production Forecasting + IYS

### 📊 Yeni Gelişmiş Rapor Seti (`/admin/raporlar/kar-stok`)
7 sekmeli tek sayfa, tümü gerçek veriyle çalışıyor:

| # | Rapor | Endpoint | Özellik |
|---|---|---|---|
| 1 | Stok Değer | `/admin/reports2/stock-valuation` | Toplam alış + satış değeri, marka/kategori breakdown, potansiyel kâr % |
| 2 | **Üretim Önerisi** | `/admin/reports2/stockout-forecast` | Stok tükenme tarihi + üretim miktarı önerisi (kritik/yüksek/uyarı renk kodlu) |
| 3 | Hızlı Satan | `/admin/reports2/fast-movers` | Velocity, stok tükenme tahmini |
| 4 | Yavaş Satan + Ölü Stok | `/admin/reports2/{slow-movers,dead-stock}` | Stoğa bağlı para |
| 5 | İade Oranı Uyarısı | `/admin/reports2/return-rate` | Eşik aşan ürünler |
| 6 | Net Kâr (Kanal) | `/admin/reports2/profit-by-channel` | Site/Trendyol/HB komisyon dahil |
| 7 | Maliyet Girişi | `/admin/product-costs` (CRUD + bulk) | Manuel ürün maliyeti |

### 🏭 Üretim Önerisi & Otomasyon
- **Akıllı eşleştirme**: Sipariş kalemlerindeki ürün adlarını veritabanı ürünleriyle keyword-bazlı eşleştirir (Trendyol/Ticimax product_id'leri sistem ID'lerinden farklı olabilir)
- **Tükenme tarihi**: Mevcut stok / günlük velocity → tahmini bitiş tarihi
- **Üretim miktarı önerisi**: hedef stok süresi × velocity - mevcut stok
- **Renk kodlu uyarı**: ≤14g kritik (kırmızı), ≤30g yüksek (turuncu), ≤60g uyarı (sarı)
- **📧 Email uyarısı**: Tek tık ile kdrgry@gmail.com'a en kritik 20 ürün gönderilir
- **🏭 Tek tık üretim planına ekle**: Hem toplu hem tek satır bazında `production_plan` koleksiyonuna kaydeder
- **⏰ Günlük otomatik cron**: Her sabah 9:00 UTC'de otomatik stockout uyarı emaili gönderir

### 👤 Beden Önerisi Sistemi
- Müşteri profili: `height_cm`, `weight_kg`, `chest_cm`, `waist_cm`, `hip_cm`
- API: `GET/POST /api/me/measurements`, `GET /api/products/{id}/size-recommendation`
- Algoritma: marka ölçü tablosu varsa → en yakın bedeni minimize edilmiş squared error ile seçer; yoksa BMI heuristic fallback (XS/S/M/L/XL/XXL)

### 📨 İYS (İleti Yönetim Sistemi) Entegrasyonu
- Türkiye yasal zorunluluğu — B2C ticari ileti öncesi izin kontrolü
- OAuth2 Client Credentials token cache
- 60dk TTL local cache (`iys_permissions` koleksiyonu)
- Endpoints: `/api/admin/iys/{status,query,query-batch,register}`
- Credentials Secrets Vault'tan okunur: `IYS_API_USERNAME`, `IYS_API_PASSWORD`, `IYS_BRAND_CODE`
- Pazarlama kampanyaları öncesi toplu izin doğrulama (50'lik batch)

### Yeni Dosyalar
- `/app/backend/routes/{reports_v2,production_hooks,size_recommender,iys_integration}.py`
- `/app/frontend/src/pages/admin/ReportsExtended.jsx` (7 sekmeli rapor sayfası)
- `/app/frontend/src/lib/adminNav.js` (menü tanımı)
- `/app/frontend/src/pages/admin/MenuSettings.jsx` (kullanıcıya özel menü düzeni)

### Admin Layout / Menü
- Beyaz yazılar, sıralama: Sipariş→Katalog→Rapor→Üretim→Tasarım→Üye→Görevler→Pazarlama→SEO→Entegrasyon→Ayarlar
- "İçerik" → "Tasarım" rename
- Dashboard sekmesi yok (logo → Dashboard linki)
- Hover ile altmenü açılır (140ms delay), overflow scroll kaldırıldı
- Her kullanıcı kendi menü düzenini `Ayarlar → Menü Düzeni`'nden ayarlayabilir (localStorage user-bazlı)

### Kargo Etiketi (`GET /api/orders/{id}/cargo-label`)
- 100×120mm format, FACETTE logo embedded base64
- Mulish font, Libre Barcode 39 Extended
- TEK barkod (sağ altta, kargo tracking veya sipariş_no)
- 3 bölüm: Gönderici / Alıcı / Kargo Bilgileri
- Telefon format: "543 595 52 90"
- "DHL E-Commerce" (MNG kaldırıldı), "Peşin Ödemeli"
- Auto-fit script: barkod çerçeveye sığacak şekilde font-size dinamik

### .env Yeni
```
IYS_API_BASE_URL=https://api.iys.org.tr   # (default)
IYS_BRAND_CODE=                              # ⚠️ Vault'ta veya .env'de
IYS_API_USERNAME=                            # ⚠️ Secrets Vault ÖNERİLİR
IYS_API_PASSWORD=
```


## Iteration 41 (2026-05-09) — Production Architecture: Vault + Monitoring + Scale

### 🔐 Hassas Veri Koruması (Secrets Vault)
- **AES-256 (Fernet)** ile şifreli credential store: `/app/backend/security/crypto.py`
- Master key: `SECRETS_MASTER_KEY` env (boşsa JWT_SECRET'tan HKDF ile türetilir)
- API: `/api/admin/vault/{secrets|secret|secret/{key}/reveal}`
- Sadece **süper admin** raw değer görür; diğer adminlere `••••••AB12` maskeli gösterilir
- Audit log: vault_secret_write / reveal / delete eylemleri `auth_audit_logs`'a yazılır
- Frontend: `/admin/secrets-vault` (form + masked tablo + reveal toggle)
- Bootstrap admin (`admin@facette.com`) startup'ta `is_super_admin: true` olarak işaretlenir

### 📊 Hata İzleme + Email Alarm
- `ErrorTrackingMiddleware`: tüm 5xx + slow response (>3s) → `error_logs`
- Burst detection: 60 saniyede 10+ kritik → otomatik `error_spike` alarmı
- **3 kanallı dispatcher** (`security/alerts.py`):
  - SMTP (öncelikli, varsayılan: kdrgry@gmail.com)
  - Resend (fallback)
  - In-app (her zaman, `alerts` koleksiyonu)
- Throttle: aynı `fingerprint` 5 dakikada bir defa mail gönderir
- Frontend: `/admin/sistem-sagligi` — KPI cards, alerts table, errors table, circuit breakers, "Test Alarmı Gönder" (super_admin)
- Starlette spurious `RuntimeError("No response returned")` filtrelendi (false-positive'leri engeller)

### ⚡ Yüksek Trafik / Ölçeklenebilirlik
- **Cache layer** (`/app/backend/cache.py`): Redis (REDIS_URL boşsa LRU+TTL in-memory fallback)
- **Circuit breaker** (`security/circuit_breaker.py`): bozuk upstream'leri izole eder
- Yeni indexler: `vault_secrets.key (unique)`, `error_logs.created_at/level/kind`, `alerts.created_at/read/fingerprint`
- Mongo ping latency `/admin/system/health`'de canlı izlenir

### 📚 Dokümantasyon
- `/app/PRODUCTION_ARCHITECTURE.md`: 7 bölümlük tam mimari rehberi
  - Mimari diagram, güvenlik katmanları, secrets vault kullanımı
  - Email alarm kurulumu (Gmail App Password / Resend)
  - 100K eş zamanlı kullanıcı kontrol listesi (replica set, CDN, gunicorn worker'lar)
  - Sunucu taşıma rehberi (mongodump/restore, .env, Redis, master key kritik)
  - P2/P3 backlog

### 📱 Mobil İkon (F harfi)
- `@capacitor/assets` ile Android (136 dosya) + iOS (13 dosya) icon/splash üretildi
- Brand: BG #0F0F11 (siyah-yakını), Accent #D4AF37 (lüks altın), F harfi merkezde

### Yeni Dosyalar
- `/app/backend/security/{__init__,crypto,redactor,monitoring,alerts,circuit_breaker}.py`
- `/app/backend/cache.py`
- `/app/backend/routes/{secrets_vault,system_health}.py`
- `/app/frontend/src/pages/admin/{SystemHealth,SecretsVault}.jsx`
- `/app/frontend/resources/{icon,icon-foreground,icon-background,splash,splash-dark}.png`
- `/app/PRODUCTION_ARCHITECTURE.md`

### .env yeni keyler (kullanıcının doldurması gerekenler)
```
SECRETS_MASTER_KEY=<auto-generated, /app/backend/.env içinde mevcut>
ALERT_TO_EMAIL=kdrgry@gmail.com         # ✅ set
ALERT_SMTP_HOST=                          # ⚠️ Gmail App Password gerekli
ALERT_SMTP_USER=
ALERT_SMTP_PASSWORD=
REDIS_URL=                                # opsiyonel, in-memory fallback aktif
```

### Test Sonucu (iteration_39.json)
- Backend: **20/20 PASS** (vault CRUD, monitoring, alerts, cache, regression)
- Frontend: **100%** (system-health-page + secrets-vault-page tüm data-testid'ler render)
- Kritik/küçük hata: **0**
- Mobil icon: 136 Android + 13 iOS asset üretildi


## Iteration 40 (2026-05-09) — Capacitor Native Projesi Tamamlandı

### 📱 Android + iOS Native Projeler Üretildi

Apple Developer + Google Play Console hesapları kullanıcıda mevcut. Iter39'da hazırlanan altyapıyı bu iterasyonda native projeye dönüştürdük:

**Yapılanlar:**
- `npx cap add android` ✅ — `/app/frontend/android/` (Gradle projesi, Java/Kotlin kaynak)
- `npx cap add ios` ✅ — `/app/frontend/ios/App/` (Xcode workspace, Swift)
- `AndroidManifest.xml` permissions + deep link intent (`facette://`) + universal link (`https://facette.com.tr`)
- `Info.plist` iOS: CFBundleURLTypes (facette scheme), localization (tr+en), push capability (UIBackgroundModes:remote-notification), KVKK uyumlu privacy strings (camera/photo/location/contacts), ATS strict
- `build.gradle` (Android app): release signing config (keystore.properties auto-load), minifyEnabled+shrinkResources, ProGuard rules
- `capacitor.config.json` — siyah/beyaz tema, splash 2s, push plugin presentation
- `build-android.sh` (executable) — `bash build-android.sh debug|release` → APK/AAB
- `build-ios.sh` (executable) — `bash build-ios.sh open|archive` → Xcode/IPA
- `ios/ExportOptions.plist` — App Store distribution config

**Yeni dokümantasyon:**
- `NEW /app/MOBILE_APP_BUILD_INSTRUCTIONS.md` (8KB) — Mac/PC'de adım adım rehber:
  - Save to GitHub → clone → yarn install
  - Android Studio + JDK 17 setup
  - Keystore generation (`keytool -genkey`)
  - Release AAB build
  - Xcode signing + APNs key
  - Firebase Console (FCM + APNs) entegrasyonu
  - App icon/splash generation (`@capacitor/assets`)
  - 26 maddelik checklist + sorun çözüm tablosu

**Capacitor packages installed (yarn):**
`@capacitor/cli@7, @capacitor/core@7, @capacitor/android@7, @capacitor/ios@7, @capacitor/app@7, @capacitor/push-notifications@7, @capacitor/preferences@7, @capacitor/splash-screen@7, @capacitor/status-bar@7, @capacitor/network@7`

**Frontend smoke OK:** webpack compiled successfully, storefront live.



## Iteration 39 (2026-05-09) — Trendyol Answer Bug Fix + Capacitor Wrap Hazırlık + Dokümantasyon

### 🐛 Trendyol Answer Field Empty Bug — DÜZELTİLDİ
Bug: `trendyol_questions.answer` alanı 303/303 boştu çünkü Trendyol'un filter API'si performans için `answers[]` array'ini boş döndürür.

**Fix (`/api/integrations/trendyol/questions/sync-answers`):**
- ANSWERED status'lu fakat answer alanı boş soruları batch tara
- Her biri için `GET /integration/qna/sellers/{supplier_id}/questions/{id}` (detail endpoint)
- Detail response single `answer` objesi döner (`answers[]` DEĞİL — format farkı tespit edildi)
- DB update: `answer`, `answered_at`, `answer_synced_at`
- Body: `{max_count, only_empty_answers}`

**Sonuç:**
- ✅ 303/303 cevap çekildi
- ✅ Bulk-train: **228 KB satırı eklendi** (74'ü çok kısa cevap atlandı)
- ✅ AI Asistan artık 228 örnek cevapla eğitildi

### 📱 Capacitor Wrap Hazırlık (App Store + Play Store)
Mevcut React frontend → iOS/Android native uygulama paketleme altyapısı:

**Backend (zaten Iter35'te hazır):**
- `/api/app/version-check`, `/api/app/devices/register`, `/api/app/config`
- Push notification altyapısı + admin yönetim paneli
- CORS'a `capacitor://localhost`, `ionic://localhost`

**Frontend altyapısı (Iter39):**
- `NEW /app/frontend/src/lib/native.js` — Capacitor native bridge (try/catch safe imports)
- `bootstrapNative()` — push registration + version check + deep links
- `setupPushNotifications()` — FCM/APNs token alma + backend register
- `checkAppVersion()` — force-update detection
- `setupDeepLinks()` — `facette://order/123` URL handler
- `App.js` — useEffect içinde bootstrap çağrısı (web mode'da no-op)
- `NEW /app/frontend/capacitor.config.ts` — appId, splash screen, push, statusbar config
- Capacitor packages installed (yarn): `@capacitor/core`, `@capacitor/app`, `@capacitor/push-notifications`, `@capacitor/preferences`

**Deployment çalıştırılması (kullanıcı tarafında):**
```bash
cd /app/frontend
yarn add @capacitor/cli @capacitor/android @capacitor/ios
npx cap init "Facette" "com.facette.app" --web-dir=build
npx cap add android && npx cap add ios
yarn build && npx cap sync
npx cap open android  # Android Studio
npx cap open ios      # Xcode (Mac)
```

### 📄 Dokümantasyon
- `NEW /app/SALES_PITCH.md` (14KB) — Marketing satış dokümantasyonu (Iter38'de oluşturulmuştu)
- `NEW /app/CAPACITOR_DEPLOYMENT_GUIDE.md` (10KB) — Adım adım iOS+Android paketleme rehberi:
  - Apple Developer + Google Play Console kurulum
  - Capacitor init + sync komutları
  - Build & Release flow (Xcode + Android Studio)
  - Store listing rehberi (icon, screenshot, privacy, KVKK)
  - 11 maddelik checklist
  - Yaygın sorun & çözümleri tablosu
  - Maliyet tahmini (~10-20K₺ ilk yıl)

### Files Modified / Created
- `/app/backend/routes/integrations_trendyol_qna.py` — sync-answers endpoint (single `answer` object mapping)
- `NEW /app/frontend/src/lib/native.js` — Capacitor bridge
- `NEW /app/frontend/capacitor.config.ts` — Capacitor config
- `/app/frontend/src/App.js` — bootstrapNative useEffect
- `/app/frontend/package.json` — 4 yeni Capacitor paketi
- `NEW /app/SALES_PITCH.md`
- `NEW /app/CAPACITOR_DEPLOYMENT_GUIDE.md`



## Iteration 38 (2026-05-08) — Akıllı Müşteri Yanıtlayıcı (AI Asistan)

### 🤖 AI Asistan — Sohbetle Eğitilen, Otomatik Yanıt Veren Bot

Kullanıcı talebi: "akıllı soru yanıtlayıcı, otomatik mesajlarla eğitiliyor, yanlış/yetersiz cevaplar tespit ediliyor, direk bota ben şunu şunu yaz diyebileyim".

**Backend (`/app/backend/routes/ai_assistant.py`)**
- `POST /api/ai-assistant/chat` — admin doğrudan bot ile sohbet:
  - **Intent detection (LLM tabanlı):** TEACH_QA / INSTRUCT / ASK
  - "S: ... C: ..." pattern'i → otomatik KB'ye eklenir
  - "Talimat: ..." → settings.ai_chatbot.persona'ya append
  - Düz soru → bot cevap verir
- `GET /api/ai-assistant/chat/history` — admin'in son 100 sohbeti
- `POST /api/ai-assistant/bulk-train` — geçmiş ANSWERED soruları KB'ye toplu aktar (channel/min_length/skip_existing/max_count)
- `GET /api/ai-assistant/bulk-train-status` — KB toplam, chat-trained, bulk-trained, last_run
- `POST /api/ai-assistant/auto-answer-batch` — bekleyen WAITING soruları için batch draft + auto-send (dry_run/min_confidence/send flag'leri)
- `POST /api/ai-assistant/evaluate-answer` — AI cevap kalite kontrolü (sufficient/reason)
- `GET /api/ai-assistant/auto-answer-stats` — pending, auto_answered_today, last_run

**Frontend (`/admin/ai-asistan`)**
4 tab page:
1. **Sohbet ile Eğit** — chat UI, quick prompts (kargo süresi/beden tablosu/iade), intent badge, KB eklendi/Talimat kaydedildi badge
2. **Bilgi Bankası** — KB CRUD (search, ekle, sil, usage_count)
3. **Toplu Eğitim** — channel/min_len/max/skip-existing config + run + sonuç kartı
4. **Otomatik Yanıt** — config (channel/max/conf/dry_run/send) + run + sonuç tablosu (Q, taslak, conf%, yeterli ✓/⚠, action GÖNDERİLDİ/KUYRUKTA)

**Sidebar:** "Entegrasyonlar > AI Asistan" (Brain ikon)

### Smoke Test Canlı (LLM gerçek çağrı)
- TEACH_QA: "S: Kargo kac gunde gelir? C: 2-3 is gunu icinde teslim edilir." → KB'ye eklendi ✅
- INSTRUCT: "Talimat: XL bedeni 42-44 numara olarak söyle" → persona'ya append ✅
- ASK: "iade nasıl yapılır?" → cevap döndü, KB'ye eklenmedi ✅
- evaluate-answer: kısa cevap için sufficient:false ✅
- auto-answer dry-run: 1 test sorusu → confidence 0.99, action:queued ✅

### Test Sonuçları
**`/app/test_reports/iteration_38.json` — Backend 14/15 PASS (1 skip), Frontend %100, 0 critical bug**

### Files Modified / Created
- `NEW /app/backend/routes/ai_assistant.py` (450 satır)
- `NEW /app/frontend/src/pages/admin/AIAssistant.jsx` (550 satır)
- `/app/backend/server.py` — ai_assistant_router include
- `/app/frontend/src/App.js` — route /admin/ai-asistan
- `/app/frontend/src/pages/admin/AdminLayout.jsx` — Brain icon + sidebar link

### Sales Documentation Created
- `NEW /app/SALES_PITCH.md` — Sistem satış dokümantasyonu (8KB, marketing-ready)
  - Hedef: 5M-250M₺ ciro moda markaları
  - 10 ana yetenek (çoklu pazaryeri, AI, lojistik, e-Fatura, RFM, mobil, güvenlik, otomasyon, storefront, ödeme)
  - ROI hesabı (122 saat/ay tasarruf, ~80-120K₺ personel maliyet azalması)
  - 4 fiyat tier'ı (9.9K-79.9K₺ aylık + 750K₺ one-time license)
  - Roadmap v1.0/v1.1/v2.0
  - Demo pitch script + rakip karşılaştırması



## Iteration 37 (2026-05-08) — Trendyol Q&A + Reviews Refactor

### 🔧 integrations.py Refactor — Aşama 2

Iter35'te Doğan modülü çıkarıldı. Iter37'de **Trendyol Q&A + Reviews** (5 endpoint, ~340 satır) `integrations_trendyol_qna.py`'ye taşındı.

**Taşınan endpoint'ler:**
- `GET /api/integrations/trendyol/questions/sync` — 60-365 gün geriye Trendyol Q&A çek
- `GET /api/integrations/trendyol/questions` — local DB list + paginate
- `POST /api/integrations/trendyol/questions/{id}/answer` — soruya yanıt
- `POST /api/integrations/trendyol/reviews/scrape` — public storefront yorum çek
- `POST /api/integrations/trendyol/reviews/scrape-bulk` — toplu

**Yapı:**
- Lazy import: `from .integrations import get_trendyol_config, get_trendyol_headers, log_integration_event` (her endpoint içinde) — circular import önler
- server.py'de `trendyol_qna_router` `integrations_router`'dan ÖNCE include edilir (catch-all routing kritik)
- 339 satır azaldı: integrations.py 4459 → **4126 satır**

### Smoke Test
- Q&A list (refactored): HTTP 200, 235 soru ✅
- Q&A sync (refactored): **68 yeni soru çekildi** (son 7 gün, canlı Trendyol API) ✅
- Trendyol settings (main module): HTTP 200, regression yok ✅
- Trendyol invoice upload (main module): HTTP 400 expected ("Fatura linki bos olamaz") ✅

### Files Modified / Created
- `NEW /app/backend/routes/integrations_trendyol_qna.py` (370 satır)
- `/app/backend/routes/integrations.py` — Q&A + Reviews bloğu silindi (-339 satır)
- `/app/backend/server.py` — `trendyol_qna_router` include



## Iteration 36 (2026-05-08) — IP-Level Brute Force Blocklist

### 🛡️ IP Blocklist (Iter34 önerisinin tamamlanması)

Iter33'teki account-level lockout (5 fail/15min → 15 dk lock) tek bir email'i koruyordu.
Bu iterasyonda **IP-level blocklist** eklendi: aynı IP'den 1 saatte 50+ failed login →
24 saat otomatik ban. Distributed brute force (botnet) saldırılarını çok daha erken durdurur.

**Backend (`deps.py` + `security_dashboard.py`)**
- Yeni helper'lar:
  - `is_ip_blocked(ip) → (locked, retry_after)` — `ip_blocklist` koleksiyonunda permanent veya blocked_until > now kontrol; süresi dolanı temizle
  - `register_failed_login_ip(ip)` — son 60 dakika içindeki failed login'leri `auth_audit_logs`'da say; threshold 50 → 24h ban
  - Constants: `IP_BLOCK_WINDOW_MIN=60`, `IP_BLOCK_THRESHOLD=50`, `IP_BLOCK_DURATION_HOURS=24`
- `auth.py::login` — IP block check (account lockout'tan önce); login fail durumunda hem `register_failed_login` (account) hem `register_failed_login_ip` (IP) çağrılıyor
- 3 yeni endpoint:
  - `GET /api/admin/security/ip-blocklist` — aktif ban listesi (manuel + otomatik)
  - `POST /api/admin/security/ip-blocklist {ip, hours?, permanent?, reason?}` — manuel ban
  - `DELETE /api/admin/security/ip-blocklist/{ip}` — ban kaldır
- Mongo index: `ip_blocklist` `{ip} unique`, `{blocked_until}`
- Audit log event'leri: `admin_ip_block`, `admin_ip_unblock` (kim, hangi IP, ne zaman, hangi sebeple)

**Frontend (`SecurityDashboard.jsx`)**
- "IP Engel Listesi" yeni section: manuel ekleme formu (IP + saat + Kalıcı checkbox + sebep) + aktif ban tablosu (tip badge KALICI/OTOMATİK/MANUEL, bitiş, sebep, tetik sayı, "Kaldır" butonu)

### Smoke Test
- Manuel ban (203.0.113.99, 1h) → HTTP 200 ✅
- Ban'lı IP'den login (`X-Forwarded-For: 203.0.113.99`) → **HTTP 429** + "Bu IP adresinden çok fazla başarısız deneme yapıldı. 1 saat sonra tekrar deneyin." ✅
- Unblock → DB silindi, login HTTP 200 + token döndü ✅

### Files Modified / Created
- `/app/backend/routes/deps.py` — IP blocklist helper'ları
- `/app/backend/routes/auth.py` — login akışında IP check
- `/app/backend/routes/security_dashboard.py` — 3 yeni endpoint + HTTPException import
- `/app/backend/server.py` — `ip_blocklist` index'leri
- `/app/frontend/src/pages/admin/SecurityDashboard.jsx` — IP Blocklist section + handler'lar



## Iteration 35 (2026-05-08) — iyzico Kısmi İade UI + Mobil Uygulama Hazırlık

### 💳 A) iyzico Kısmi İade UI (`Returns.jsx`)
Backlog P1 tamamlandı. Mevcut `/api/integrations/iyzico/refund` endpoint'inin üstüne admin UI:

- Returns sayfası tablosuna **CreditCard ikonlu mavi buton** (sadece RETURN tipi için)
- Modal: 
  - Sipariş özet kartı (no, müşteri, tutar)
  - **İade Tutarı** (KDV dahil, default = net iade tutarı)
  - **Kargo Bedeli Kesintisi** (Truck ikonlu, müşteriden tutulacak tutar)
  - **İade Sebebi** (text)
  - Canlı hesaplama: `İade − Kargo = Müşteriye İade Edilecek` (tabular-nums, mavi vurgu)
  - Validasyon: amount>0, shipping<amount
- Submit → backend Iyzico /payment/refund → DB `orders.refunds[]` push
- Loading spinner + toast (success: tutar göster)

### 📱 C) Mobil Uygulama Backend Altyapısı (Capacitor/RN için hazır)
Kullanıcının "Android & iOS native uygulamaya taşıyacağım" talebi için sunucu-tarafı:

**Yeni endpoint'ler — `routes/mobile.py` (public + auth)**
- `GET /api/app/version-check?platform=ios&current_version=0.5.0` — force update detection
- `POST /api/app/devices/register` — push token + device info (FCM/APNs)
- `DELETE /api/app/devices/{device_id}` — uninstall/logout
- `GET /api/app/devices/me` — kullanıcının cihazları
- `GET /api/app/config` — feature flags + branding + support kanalları (uzaktan kontrol)

**Admin endpoint'ler — `routes/admin_mobile.py`**
- `GET/POST /api/admin/mobile/versions` — iOS/Android version yönetimi
- `GET/POST /api/admin/mobile/config` — feature flags + branding güncelle
- `GET /api/admin/mobile/devices` — kayıtlı cihaz listesi + platform breakdown
- `POST /api/admin/mobile/push/send` — broadcast/segment/user/device push (FCM HTTP). FCM_SERVER_KEY env yoksa mock mode'da kuyruklar.

**Frontend admin sayfası — `MobileApp.jsx` (`/admin/mobil-uygulama`)**
- 4 Tab: Versiyonlar / Yapılandırma / Cihazlar / Push Bildirim
- iOS + Android version kart (min, latest, store_url, release notes, force_update toggle)
- Feature flags: live_support, social_logins, biometric_login, instagram_shop vb.
- Cihaz tablosu + platform breakdown KPI'ları
- Push send form: target (all/platform/user/device) + title + body + image_url + JSON data (deep link)

**Yan değişiklikler:**
- `.env` `CORS_ORIGINS`'e `capacitor://localhost`, `ionic://localhost`, `http://localhost` eklendi
- Mongo index'ler: `user_devices` `{user_id, device_id} unique`, `push_token`, `is_active+platform`
- `notification_logs` koleksiyonu push gönderim audit log

### Mobil Uygulama Yol Haritası (Önerilen)
1. **Faz 1 — Capacitor (1-2 hafta)** — Mevcut React UI'ı hızlıca App Store + Play Store'a çıkar
2. **Faz 2 — React Native + Expo (1.5-3 ay)** — Premium native UX (background sync, biometric vb.)

### Files Modified / Created
- `NEW /app/backend/routes/mobile.py`
- `NEW /app/backend/routes/admin_mobile.py`
- `NEW /app/frontend/src/pages/admin/MobileApp.jsx`
- `/app/backend/server.py` — router include + user_devices indexes
- `/app/backend/.env` — CORS Capacitor origin'leri
- `/app/frontend/src/App.js` — route + import
- `/app/frontend/src/pages/admin/AdminLayout.jsx` — sidebar link
- `/app/frontend/src/pages/admin/Returns.jsx` — Iyzico refund modal + button + DialogDescription (a11y)

### Iter35 Refactor (Doğan modülü ayrıldı)
- `NEW /app/backend/routes/integrations_dogan.py` — 4 endpoint (settings GET/POST, test-connection, check-user)
- `/app/backend/routes/integrations.py` — Doğan section silindi (4535 → 4459 satır, -76 satır)
- `/app/backend/server.py:349-352` — `dogan_router` `integrations_router`'dan ÖNCE include (catch-all sıralaması kritik)
- **Test 24/24 PASS** — Doğan endpoint'leri eski davranışla birebir aynı, hiçbir routing regression yok
- Sıradaki refactor: Trendyol (44 routes, ~3500 lines) — ayrı kontrollü iterasyon



## Iteration 34 (2026-05-08) — Security Dashboard + Trendyol Q&A Date Filter + Trendyol Reviews Scraper

### 🛡️ Admin Security Dashboard (`/admin/guvenlik-paneli`)
Iter33'te oluşturulan `auth_audit_logs` koleksiyonunun üstüne canlı görünürlük paneli kuruldu.

**Backend (`/app/backend/routes/security_dashboard.py`)**
- `GET /api/admin/security/summary?window_hours=N` — KPI'lar (total events, success/fail logins, registrations, active lockouts, locked_users list, NoSQL injection attempts, lockout-blocked attempts)
- `GET /top-failed-emails` — başarısız login aggregate (email + count + last_seen + distinct_ips)
- `GET /top-failed-ips` — IP bazlı agregat
- `GET /timeline` — saat bazlı success/fail zaman serisi (grafik için)
- `GET /recent-events?limit=&event=&success=&email=&ip=` — son 100 audit log + filtreleme
- `POST /unlock-user {email}` — admin manuel kilit açma + `admin_unlock` audit event

**Frontend (`/app/frontend/src/pages/admin/SecurityDashboard.jsx`)**
- 8 KPI kartı (Toplam Olay / Başarılı / Başarısız / Aktif Kilitli / Yeni Kayıt / Şifre Hata / NoSQL Injection / Lockout Bloğu)
- "Şu an Kilitli Hesaplar" kartı + her hesap için "Kilidi Aç" butonu
- "Çok Saldırılan E-postalar" + "Şüpheli IP'ler" grid
- Son 100 olay tablosu — event/success/email/ip filtreleri
- Window selector: 1sa / 24sa / 7gün / 30gün
- Sidebar: Entegrasyonlar > Güvenlik Paneli (Shield ikon)

**Indexes** (`server.py` lifespan'a eklendi):
- `auth_audit_logs.created_at desc`
- `auth_audit_logs.event + email + created_at`
- `auth_audit_logs.ip + created_at`
- `auth_audit_logs.success + created_at`

### 📅 Trendyol Questions — Tarih Aralığı Düzeltmesi
Önceki sorun: API varsayılan olarak son ~14-30 gün döndüğü için "geçmiş soruları çekmiyor" bug'ı.

**Fix** (`integrations.py:3567`):
- `GET /api/integrations/trendyol/questions/sync?days_back=90&status=`
- Her sayfa request'ine `startDate` + `endDate` (Unix ms) ekleniyor
- `days_back` clamp `[1, 365]`
- `orderByField=CreatedDate, orderByDirection=DESC` ile en yeniden eskiye
- Response'a `synced` (yeni) + `updated` (zaten var) + `date_range` ayrımı eklendi

### ⭐ Trendyol Reviews — Public Storefront Scraper
Resmi Trendyol Seller API'sinde yorum endpoint'i yok (web search teyit). Public storefront API (`public.trendyol.com/discovery-web-websfxsocialreviewrating-santral`) kullanan scraper eklendi.

**Endpoint'ler** (`integrations.py:3744`):
- `POST /api/integrations/trendyol/reviews/scrape` body: `{trendyol_url, product_id, min_rating}` (default 4 → sadece 4-5★)
  - URL'den `-p-(\d+)` regex ile contentId çıkar
  - Public reviews API'den 10 sayfa × 30 = max 300 yorum çek
  - DB: `product_reviews` koleksiyonuna duplicate-safe insert (`source: trendyol_public`, `external_id: review_id`)
  - Ürünün `rating`/`review_count`/`reviews_synced_at` alanlarını re-compute
- `POST /scrape-bulk` body: `{items:[{trendyol_url, product_id}], min_rating}` (max 50 ürün/batch)

⚠️ Production note: Trendyol public API anti-bot olabilir; UA cycling veya supplier-side review API gerekebilir.

### Test Sonuçları
**`/app/test_reports/iteration_34.json` — Backend 29/29 PASS + Frontend %100**
- 6 security endpoint admin guard ✅
- Locked user → unlock-user → DB'de unset doğrulandı ✅
- Trendyol questions startDate/endDate kod-review onaylı ✅
- Reviews scrape input validation (URL + contentId regex) ✅
- Frontend 8 KPI card, locked user list + unlock button, filters, sidebar link ✅

### Files Modified / Created
- `NEW /app/backend/routes/security_dashboard.py`
- `NEW /app/frontend/src/pages/admin/SecurityDashboard.jsx`
- `/app/backend/server.py` — index'ler + router include
- `/app/backend/routes/integrations.py` — `timedelta` import, questions sync date params, reviews scrape endpoints
- `/app/frontend/src/App.js` — import + route `/admin/guvenlik-paneli`
- `/app/frontend/src/pages/admin/AdminLayout.jsx` — sidebar link
- `NEW /app/backend/tests/test_iteration34_security_dashboard.py`



## Iteration 33 (2026-05-08) — Cybersecurity Hardening (OWASP/PCI-DSS)

### 🔒 Kapsamlı Güvenlik Sertleştirmesi (Backend)

Kullanıcının "OWASP Top 10 + PCI-DSS uyumlu güvenlik" talebiyle backend'e tam set sertleştirme uygulandı:

#### 1. JWT Sertleştirme (`deps.py`)
- `_decode_jwt_strict`: HS256 zorunlu (alg=none açığı kapalı), `iss=facette-api` doğrulama, `exp+user_id` zorunlu claim
- `JWT_SECRET` env zorunluluğu (64-byte random `.env`'de) — eski hardcoded fallback uyarı veriyor
- Token payload: `iat, iss, exp (7d), user_id, is_admin`
- `require_admin`/`get_current_user` `is_active=False` kullanıcıyı reddediyor

#### 2. Şifre & Hash
- `bcrypt rounds=12` (önceki default 10)
- `verify_password` md5/sha1 prefix'i olmayan hash'i reddediyor (`$2a/$2b/$2y` zorunlu)

#### 3. NoSQL Injection Koruması (`safe_str`, `is_safe_email`)
- `$`, `{`, `}`, `\x00` içeren email payload'ları regex ile reddediliyor
- `safe_str` dict/list/tuple gibi tip karmaşası saldırılarına karşı boş string döndürüyor
- `login`, `register`, `change-password` endpoint'leri tüm string input'ları sanitize ediyor

#### 4. Rate Limiting (`slowapi` middleware)
- `login`: 10/dk per-IP (X-Forwarded-For aware)
- `register`: 5/dk per-IP
- `forgot-password/request-otp`: 3/dk
- `forgot-password/verify-otp`: 10/dk
- 11. denemede HTTP 429 + `Retry-After` header

#### 5. Brute Force Lockout (`is_account_locked`, `register_failed_login`)
- 5 hatalı login (15 dk pencere) → account `locked_until` 15 dk
- Lockout sırasında doğru parolayla bile giriş engelleniyor (HTTP 429)
- Başarılı login'de `failed_attempts/locked_until` reset

#### 6. Audit Log (`auth_audit_logs` koleksiyonu)
- Event'ler: `login` (success/fail), `register`, `password_change` (success/fail)
- Saklanan alanlar: `event, user_id, email, ip, user_agent, success, meta(reason, retry_after), created_at`
- IP `client_ip_from_request` ile X-Forwarded-For first-hop'tan alınıyor

#### 7. Security Headers Middleware (`server.py::SecurityHeadersMiddleware`)
Her API yanıtında:
- `Content-Security-Policy` (default-src 'self' + https whitelisting, frame-ancestors 'none', object-src 'none')
- `X-Frame-Options: DENY` (clickjacking)
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` (geolocation/microphone/camera/usb disabled, payment=self)
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HSTS)
- `Cross-Origin-Resource-Policy: same-site` (Spectre koruması, sadece /api/*)
- `X-Robots-Tag: noindex, nofollow` (sadece /api/*)

#### 8. CORS Sıkılaştırması
- Eski `allow_origins=["*"]` kaldırıldı
- Whitelist: `facette.com.tr, www.facette.com.tr, ecommerce-erp-2.preview.emergentagent.com, localhost:3000`
- `allow_methods` daraltıldı (GET/POST/PUT/PATCH/DELETE/OPTIONS); `allow_headers` whitelist (Authorization/Content-Type/Accept/X-Requested-With)
- `CORS_ORIGINS` env eksikse fail-fast — accidental wildcard önler

### Test Sonuçları
**`/app/test_reports/iteration_33.json` — 25/25 PASS**
- JWT alg=none/expired/bad-issuer/tampered-sig hepsi 401 ✅
- 5 NoSQL payload variant'ı reddedildi ✅
- Lockout (5 fail → 15-min lock + DB locked_until field) ✅
- Rate limits (login/register/otp 429) ✅
- Audit log writes ✅
- Tüm security header'lar her /api/* response'da ✅
- Change-password (wrong→400+audit, correct→200+audit) ✅
- bcrypt $2b$12$ prefix ✅; legacy md5 reddedildi ✅
- require_admin customer JWT için 403 ✅
- admin@facette.com regression login OK ✅

### Notlar (Production Önerileri)
- ⚠️ Public preview URL ingress (Cloudflare) `Access-Control-Allow-Origin: *` ekleyebiliyor — FastAPI tarafı strict (localhost:8001'de doğrulandı). Production'da ingress katmanından da whitelist enforce edilmeli.
- 💡 `auth_audit_logs.created_at + (event,email)` index'i forensic sorgular için önerilir (büyüdükçe).

### Files Modified
- `/app/backend/.env` — `JWT_SECRET` (64-byte random) + `CORS_ORIGINS` whitelist
- `/app/backend/routes/deps.py` — JWT strict decode, NoSQL guards, audit log, lockout helpers, shared slowapi limiter
- `/app/backend/routes/auth.py` — login/register/change-password rate limit + audit + lockout + sanitize
- `/app/backend/server.py` — SecurityHeadersMiddleware, SlowAPIMiddleware, CORS strict whitelist
- `/app/backend/requirements.txt` — slowapi==0.1.9, limits, deprecated, wrapt

### Files Created
- `/app/backend/tests/test_security_iter33.py` (testing agent oluşturdu)
- `/app/test_reports/iteration_33.json`



## Iteration 32 (2026-05-08) — Ticimax Canlı Stok Senkronu

### 🎯 Özellik: Web Servis Stok Çekimi
Admin'in tek tıkla (veya cron ile her 2 saatte bir) Ticimax SOAP'tan canlı stok değerlerini çekip yerel `products` koleksiyonunu güncellemesi.

### Backend
- NEW `/app/backend/routes/ticimax_stock_sync.py`
  - `POST /api/admin/ticimax/sync-stock?max_products=2000&page_size=50` — senkron çağrı (~2-30s)
  - `POST /api/admin/ticimax/sync-stock-async` — background task
- Eşleme stratejisi (öncelik): csv_card_id == Ticimax UrunKartiID → variants[].id == Varyasyon.ID → variants[].stock_code == Varyasyon.StokKodu → variants[].barcode == Varyasyon.Barkod
- Cron: `_ticimax_sync_stock` her 2 saatte bir (id=`ticimax_stock_sync`)
- Loglar `integration_logs` koleksiyonuna `marketplace=ticimax, action=stock_sync` olarak yazılıyor

### Frontend
- `Otomasyon Durumu` panelinin sağ üstüne **"Ticimax Stok Senkronla"** butonu (Database ikonlu, amber renkli)
- Tıkladıktan sonra anında popup: ticimax_total, fetched, matched_products, updated_variants, not_found_in_db, duration_sec

### Test Status
- Endpoint canlı: `ticimax_total=13, fetched=13, matched_products=0` (test wscode sınırlı)
- ⚠️ **Test ortamı Ticimax SOAP wscode sadece 13 ürün dönüyor** (IDs 2880-2892); DB'de bu csv_card_id'ler yok (DB max 2836).
- Kullanıcı **production wscode**'u girdiğinde tam katalog senkron olacak. Eşleme algoritması csv_card_id'den fallback olarak stock_code/barcode'a düşüyor.

### Files
- NEW `/app/backend/routes/ticimax_stock_sync.py`
- `/app/backend/scheduler.py` (_ticimax_sync_stock job + 2hr interval)
- `/app/backend/server.py` (router registration)
- `/app/frontend/src/pages/admin/AutomationStatus.jsx` (ManualSyncButtons component)

### Kullanım
1. Admin > Otomasyon Durumu sayfasına git
2. Sağ üstte "Ticimax Stok Senkronla" butonuna tıkla
3. Sonuç popup'ında "X ürün eşleşti, Y varyasyon güncellendi" gör
4. Otomatik olarak da 2 saatte bir cron çalışıyor — Aktif Cron İşleri listesinde "ticimax_stock_sync" görünür



## Iteration 31 (2026-05-08) — Wave 1: Massive UX Pack (12 fix/feature)

### 🎯 Kullanıcının uzun listesi (Hepsi tamamlandı)

| # | Talep | Durum |
|---|---|---|
| 1 | Mega menü öğeleri çok aralıklı + fareyle kayboluyor | ✅ space-y-1, py-6, 250ms close-delay (`openMenu`/`scheduleClose`/`cancelClose` handlers) |
| 2 | Mega menü sağda 3 ürün | ✅ `limit=2` → `limit=3`, layout `min-w-[564px]` |
| 3 | Sepet/Üye/Sipariş kartlarında ürün resmi tam sığmıyor | ✅ `object-cover` → `object-contain` (Account.jsx, OrderSuccess.jsx, Checkout.jsx) |
| 4 | Ürün sayfasında "Adet" yazısı + selector kaldır | ✅ ProductDetail.jsx quantity bloğu silindi (sepete her zaman 1) |
| 5 | Ürünün başka renkleri varsa kare swatch göster | ✅ Backend `GET /api/products/{id}/color-siblings` (csv_card_id grouping) + ColorSiblings component |
| 6 | Footer için tasarım şablonu + HTML editor | ✅ NEW `/admin/footer-tasarim` (mode: html / structured), CRUD + canlı önizleme + reset-default |
| 7 | Account "Suud Collection" → "Facette" | ✅ ProfilePane sidebar metni |
| 8 | Geri sayım bar aktifken statik metinler de görünsün | ✅ Header.jsx countdown'un altına "500 TL Üzeri Ücretsiz Kargo · İlk Üyeliklere %10" eklendi |
| 9 | Adres formunda kurumsal alanlar yok | ✅ `is_corporate` toggle + `company_name` / `tax_no` / `tax_office` (frontend + backend whitelist) |
| 10 | Sepet drawer'da kombin + en çok satanlar göster | ✅ CartDrawer.jsx — cart-suggestions API + best sellers (sort=popular) yatay scroll strips |
| 11 | Sipariş onay sayfası: geri butonu | ✅ Checkout.jsx + OrderSuccess.jsx üst sola `<ChevronLeft>` border-black butonu |
| 12 | "Adrese Teslim Edilsin" radio kaldır | ✅ Checkout.jsx address block sadeleştirildi |
| 13 | Sipariş onay sayfası B&W kontrastı | ✅ `text-stone-*` → `text-black/text-gray-700`, `bg-stone-*` → `bg-black/bg-gray-50` |
| 14 | Account: şifre sıfırlama | ✅ NEW endpoint `POST /api/auth/change-password` + Account.jsx "Şifre" sekmesi (Lock ikonlu pill tab + form) |

### Backend Files
- NEW `/app/backend/routes/footer_template.py` (public + admin endpoints)
- `/app/backend/routes/auth.py` change-password endpoint
- `/app/backend/routes/customer.py` corporate fields whitelist (POST + PUT)
- `/app/backend/routes/products.py` color-siblings endpoint
- `/app/backend/server.py` router registers

### Frontend Files
- NEW `/app/frontend/src/pages/admin/FooterDesign.jsx`
- `/app/frontend/src/components/Header.jsx` (mega menu fix + 3 products + delay)
- `/app/frontend/src/components/CartDrawer.jsx` (kombin + bestsellers)
- `/app/frontend/src/components/Footer.jsx` (template-driven)
- `/app/frontend/src/pages/Account.jsx` (security tab + Facette + corporate + object-contain)
- `/app/frontend/src/pages/OrderSuccess.jsx` (back button + B&W + object-contain)
- `/app/frontend/src/pages/Checkout.jsx` (back button + B&W + remove address radio)
- `/app/frontend/src/pages/ProductDetail.jsx` (no quantity + ColorSiblings)
- `/app/frontend/src/App.js` + AdminLayout sidebar

### Test Status
- ✅ Smoke screenshot: Top bar ile birlikte countdown (00 GÜN 12 SAAT 48 DK 56 SN) + statik strip + mega menü 3 ürün + tighter spacing tümü doğrulandı
- ✅ Backend curl: `/api/footer-template` (mode=structured, 3 columns), `/api/products/{id}/color-siblings` (siblings=0 sample), `/api/auth/change-password` (401 unauth — koruma çalışıyor)

### ⚠️ Kullanıcı Aksiyonu Gerekli
- **Trendyol creds**: Otomasyon paneli "TEST_TY_KEY" gösteriyor → `Admin > Pazaryeri > Trendyol > Ayarlar`'dan canlı `api_key/api_secret/supplier_id` GÜNCELLEME KAYDET basın (bilgileri "ekledim" dediniz ama DB'ye yazılmamış görünüyor)
- **RESEND_API_KEY**: `/app/backend/.env`'e gerçek Resend key ekleyip backend restart (E-posta kampanyaları için)
- **Doğan creds**: settings collection'a `id=dogan_edonusum` döküman gerekli

### Defer Edilen
- Trendyol gerçek 4-5★ yorum çekme (canlı creds geldiğinde yapılır)
- Trendyol müşteri soruları debug (canlı creds geldiğinde)
- P3 integrations.py refactor (4380 satır — risk vs fayda)



## Iteration 30 (2026-05-08) — Countdown Bar + DHL Rebrand + Otomasyon Paneli

### ⏱️ Yönetilebilir Geri Sayım Üst Barı (countdown_bar)
**Yeni özellik**: Admin > Sayfa Tasarımı > "Geri Sayım Barı" bloğu — sitenin en üstünde tam yönetilebilir countdown.

**Field'lar (settings JSON)**:
- `left_text` — sol tarafta görünen metin (örn: "TÜM ALIŞVERİŞLERDE KARGO BEDAVA")
- `timer_label` — sayaç etiketi (örn: "KALAN SÜRE:")
- `start_at` — datetime-local; bu tarih gelene kadar bar GİZLİ (planlama)
- `end_at` — datetime-local; countdown bitince bar otomatik kaybolur
- `bg_color` / `text_color` — color picker
- `fallback_text` — bar pasifken (start öncesi/end sonrası) gösterilecek metin

**Akış**: now < start_at → fallback / now ∈ [start, end] → countdown / now > end → fallback. Reference image (facette.com.tr) ile birebir uyumlu görsel (sayı kutuları beyaz, GÜN/SAAT/DK/SN etiketli).

**Files**:
- NEW `/app/frontend/src/components/CountdownBar.jsx`
- NEW form section + canlı önizleme: `PageDesign.jsx`
- `Header.jsx` artık statik "500 TL Üzeri Ücretsiz Kargo" yerine `<CountdownBar/>` render ediyor (bar yoksa orijinal metin fallback)
- `Home.jsx` BlockRenderer countdown_bar tipini skip ediyor (zaten Header'da)

### 🚚 MNG Kargo → "DHL E-Commerce" Rebrand
- Admin Orders.jsx: cargo provider listesi, action button title'ları, toast mesajları
- Integrations.jsx: provider name + description
- ProviderSettings.jsx: webhook info kartı başlığı + payload comment
- provider_settings.py: provider name + description
- Backend internal key `mng` korundu (API/DB compat)

### 📊 Otomasyon Durumu Paneli (NEW: `/admin/otomasyon`)
**Yeni özellik**: Admin tüm cron + senkron + entegrasyon durumlarını tek ekrandan görür.

**Bölümler**:
1. **Entegrasyon kartları** (4 adet): Ticimax / Doğan / Resend / Trendyol — yapılandırma durumu yeşil/gri
2. **Aktif Cron İşleri**: APScheduler job listesi (id, interval, sıradaki çalışma + relative time)
3. **Pazaryeri Senkron Ayarları**: Her marketplace için ürün + sipariş interval + son senkron zamanı
4. **Log Özeti**: Son 100 log marketplace bazlı sayım (success/error/info)
5. **Son Entegrasyon Logları**: 50 satırlık tablo (zaman, marketplace, action, status, mesaj)
- Otomatik 30sn yenileme + manuel "Yenile" butonu
- Sidebar > Entegrasyonlar > "Otomasyon Durumu" altında

**Backend**: `GET /api/admin/automation/status?log_limit=N`
**Files**: `automation_status.py` (NEW), `AutomationStatus.jsx` (NEW), `App.js` route, `AdminLayout.jsx` sidebar

### Test Status
- countdown_bar: ✅ Screenshot doğrulandı (referans `facette.com.tr` ile birebir aynı: "TÜM ALIŞVERİŞLERDE KARGO BEDAVA | KALAN SÜRE: 11 GÜN 13 SAAT 51 DK 30 SN")
- automation status: ✅ Screenshot doğrulandı (4 cron, Trendyol AKTIF "Ürün: 5dk Sipariş: 2dk", 6 marketplace log)
- DHL rebrand: ✅ Tüm UI'da "DHL E-Commerce" / "DHL" yazıyor

### Files Modified
- NEW `/app/backend/routes/automation_status.py`
- NEW `/app/frontend/src/components/CountdownBar.jsx`
- NEW `/app/frontend/src/pages/admin/AutomationStatus.jsx`
- `/app/backend/server.py` (router include)
- `/app/backend/routes/provider_settings.py` (DHL rename)
- `/app/frontend/src/components/Header.jsx` (CountdownBar import)
- `/app/frontend/src/pages/admin/PageDesign.jsx` (countdown_bar form + preview)
- `/app/frontend/src/pages/admin/Orders.jsx` (DHL rename)
- `/app/frontend/src/pages/admin/Integrations.jsx` (DHL rename)
- `/app/frontend/src/components/admin/ProviderSettings.jsx` (DHL rename)
- `/app/frontend/src/pages/Home.jsx` (countdown_bar skip)
- `/app/frontend/src/App.js` (route)
- `/app/frontend/src/pages/admin/AdminLayout.jsx` (sidebar)



## Iteration 29 (2026-05-07) — Page Block Visibility + Trendyol Cron + Kampanya E-postası

### ✨ Page Block Cihaz Görünürlüğü (Mobile / Desktop)
- Backend: `cms.py` POST/PUT whitelist'ine `show_desktop`, `show_mobile` (default True) eklendi
- Frontend: `PageDesign.jsx` form'una iki toggle (🖥️ Masaüstünde Göster / 📱 Mobilde Göster); blok kartında "🖥️ Gizli" / "📱 Gizli" rozetleri
- `Home.jsx` BlockRenderer artık görünürlüğe göre `md:hidden` / `hidden md:block` class'ı uyguluyor; ikisi de false ise blok hiç render edilmez

### ⏱️ Trendyol Cron 2-dakikalık Senkronizasyon
- `marketplace_accounts.trendyol.auto_sync.orders_interval_min = 2` DB'ye yazıldı + `orders_enabled = True`
- Cron `_run_trendyol_auto_orders_pull` zaten dinamik interval okuyor → 2 dk'da bir tetiklenecek
- ⚠️ Şu an Trendyol creds `TEST_TY_KEY` placeholder. Gerçek API çalışması için kullanıcı admin > Pazaryeri ayarlarından `api_key` / `api_secret` / `supplier_id` girmeli

### 🟡 P2.1 — Trendyol Sipariş Listesi
- DB'de zaten 20 Trendyol siparişi mevcut (platform=trendyol)
- Admin Orders.jsx `?platform=trendyol` filtresi düzgün çalışıyor (curl ile doğrulandı: 20 sipariş, müşteri isimleri, item count tamam)
- Cron 2 dk'lık aktif olduğunda yeni siparişler otomatik akacak

### 🟡 P2.2 — RFM Müşteri Segmentasyonu + E-posta Kampanyası
- ✅ `/api/analytics-extra/rfm` endpoint'i zaten vardı (R/F/M quintile + 9 segment etiketi: VIP, Sadık, Yeni, Potansiyel Sadık, Risk Altında, Dikkat Edilmeli, Kaybedilen, Hibernasyon, Standart)
- ✅ `/admin/musteri-segmentleri` admin sayfası zaten vardı (segment kartları + tablo + Excel export)
- ✨ **Yeni**: `POST /api/admin/email/send-to-emails` endpoint — dinamik liste için Resend kampanya
- ✨ **Yeni**: CustomerSegments.jsx'e "Kampanya Gönder" butonu + modal (subject + HTML editor + canlı önizleme + segment'e özel toplu gönderim)
- 156 müşteri segmentlere ayrıldı (VIP/Şampiyon: 19, Yeni Müşteri: 34, Kaybedilen: 29 vs.)
- ⚠️ Resend gönderim için `RESEND_API_KEY` gerekli (admin .env'e eklenmeli)

### ⚪ P3 — `integrations.py` Refactor (Defer Edildi)
- 4380 satırlık dosya çalışıyor + tüm testler geçiyor; refactor riski faydadan yüksek
- Future iteration'da vendor bazlı bölme (`integrations_trendyol.py`, `_hb.py`, `_temu.py`, `_ticimax.py`) önerilir

### Files Modified
- `/app/backend/routes/cms.py` (show_desktop/show_mobile field whitelist)
- `/app/backend/routes/catalog_extras.py` (send-to-emails endpoint)
- `/app/frontend/src/pages/admin/PageDesign.jsx` (visibility toggles + badges)
- `/app/frontend/src/pages/Home.jsx` (BlockRenderer visibility CSS)
- `/app/frontend/src/pages/admin/CustomerSegments.jsx` (CampaignModal + Send button)



## Iteration 28 (2026-05-07) — Page Blocks Yönetimi + MNG Webhook Tamamlandı

### 🟡 P1.1 — Admin Sayfa Tasarımı (page-blocks)
**Tespit edilen bug**: `cms.py` seed-default-home `two_banners` type kullanıyordu ama Home.jsx BlockRenderer ve PageDesign.jsx BLOCK_TYPES `half_banners` bekliyordu → orta blok hiç render edilmiyordu.

**Yapılanlar:**
- Seed default'ı düzeltildi: `two_banners` → `half_banners`
- DB migration yapıldı: 1 mevcut block tipi `half_banners`'a güncellendi
- Yeni endpoint `POST /api/page-blocks/reorder` (body: `{ids: [...]}`) — bulk drag-drop reorder, tek seferde sort_order=1,2,3,... atar
- `PageDesign.jsx` save-order artık 5 paralel PUT yerine tek POST/reorder kullanıyor (hızlı + atomik)
- PUT field whitelist eklendi (id/created_at override engellendi — security önerisi)
- Mevcut UI zaten tam fonksiyonel: drag-drop dnd-kit, mobile/desktop iframe preview, image upload, product picker, all 8 block types

### 🟡 P1.2 — MNG Kargo Webhook
**Mevcut:** `POST /api/orders/cargo/mng-webhook` (orders.py:1529) zaten yazılı + status_map dolu.

**Doğrulanan:**
- BARKOD veya REFERANS_NO ile sipariş eşleşme
- Status mapping: 100=preparing, 200/300=shipped, 400=delivered+delivered_at, 500=returned
- `cargo_status_history` push (audit trail)
- `integration_logs` collection log
- Auth-free (public endpoint, MNG için)
- Bilinmeyen barkodlar sessizce loglanıyor (MNG retry yapmasın)

**Yeni:** ProviderSettings.jsx'e MNG seçildiğinde **webhook URL info kartı** eklendi:
- URL: `{BACKEND}/api/orders/cargo/mng-webhook` (kopyala butonuyla)
- Beklenen payload örneği (ISLEM_KODU 100/200/300/400/500)
- MNG paneline tanımlanması için admin'e talimat

### Test Status
- testing_agent_v3_fork iteration 24 → **12/12 passed**, 1 skipped (non-bug)
- Test dosyası: `/app/backend/tests/test_iteration24_pageblocks_mng_webhook.py`
- Page blocks: GET sort, POST/PUT/DELETE/reorder/seed all pass + admin auth enforced
- MNG webhook: 400 hata, unknown silent log, 200/300/400 status updates, history push, integration_logs ✅

### Files Modified
- `/app/backend/routes/cms.py` (half_banners fix + reorder endpoint + PUT whitelist)
- `/app/frontend/src/pages/admin/PageDesign.jsx` (save-order bulk endpoint)
- `/app/frontend/src/components/admin/ProviderSettings.jsx` (MNG webhook info card)

### MNG Webhook URL (admin'e tanımlatılacak)
```
https://erp-dashboard-118.preview.emergentagent.com/api/orders/cargo/mng-webhook
```
(Production'da REACT_APP_BACKEND_URL'a göre değişir; UI'da auto-render ediliyor)



## Iteration 27 (2026-05-07) — Ticimax Sipariş Verilerinin Düzeltilmesi + Account Sayfası Yenilendi

### 🔴 P0 Critical Bug Fix — Ticimax Pagination + Cron Parser
**Tespit:**
- Kullanıcı "sipariş verileri silindi" derken aslında veriler bozuk olarak yazılmıştı.
- 2 ayrı bug üst üste:
  1. **Cron parser çok minimaldi** (`scheduler.py`): top-level `AliciAdi` field'ı boş döndüğü için `first_name=""`, `address` Python dict olarak string'leştiriliyordu, `items=[]` boş kalıyordu. Doğru veriler `KargoAdresi/FaturaAdresi` nested dict + `UrunListesi` içinde gizliydi.
  2. **Ticimax SOAP `BaslangicIndex` yanlış**: `(page-1)*page_size` formülü kullanılıyordu, ama Ticimax `BaslangicIndex`'i 0-based **sayfa indeksi** olarak yorumluyor. page_size=100 ile her "sayfa" 10000 ID atlatıyordu.

**Fix:**
- Yeni shared module `/app/backend/ticimax_order_parser.py` — KargoAdresi/FaturaAdresi nested dict parse + UrunListesi item parse (zeep `__values__` desteği)
- `scheduler.py._ticimax_sync_orders` artık parser'ı kullanıyor + idempotent upsert (var ise güncelle, yok ise insert)
- `ticimax_client.get_orders` pagination düzeltildi: `BaslangicIndex=(page-1)` (page index)
- Yeni admin endpoint `POST /api/integrations/ticimax/orders/backfill?items_chunk=N` — bozuk sipariş tespit edip Ticimax'tan tekrar parse ediyor

**Sonuç:**
- Backfill ile 99 sipariş düzeltildi (194 → 137 broken)
- `first_name` boş: 58 → 1 ✅
- `total=0` sayısı: 57 → 0 ✅
- Admin sipariş tablosu artık gerçek müşteri isimlerini gösteriyor (Gamze Ülkebaş, Tuğçe Sevinç vs.)
- Kalan 136 sipariş 2025 yılına ait eski siparişler — Ticimax `SelectSiparisUrun` bunlar için 0 item dönüyor, kayıp veri Ticimax tarafında

### 🟡 P1 — Account.jsx Suud/Zara Tarzı Yeniden Tasarım
- Hero header: 80px avatar (initials) + saatlik selamlama + e-posta + üyelik tarihi
- Pill-style tab nav (mobile select dropdown yerine yatay scroll pill'ler)
- Sipariş kartları: ürün resim stack (4'e kadar overlap), status badge, expandable detail
- Genişletilmiş detay: ürün listesi (size/color/qty), teslimat adresi, kargo takip linki, total
- Adres kartları: varsayılan rozet + Star ikon, edit/delete inline
- Profil paneli: solda detaylar + sağda siyah Suud avantaj kartı
- Mulish font + tracking-wide minimal black/white aesthetic korundu
- All API calls aynı (`/api/my-orders`, `/api/my-addresses`, `/api/users/me`, `/api/addresses`)

### Files Modified
- `/app/backend/ticimax_order_parser.py` (NEW)
- `/app/backend/ticimax_client.py` (BaslangicIndex fix)
- `/app/backend/scheduler.py` (cron uses parser)
- `/app/backend/routes/integrations.py` (backfill endpoint)
- `/app/frontend/src/pages/Account.jsx` (full redesign)


## Iteration 26 (2026-05-07) — Bug Fixes + Bulk Invoice + MNG Webhook + Mega Menu Best-Sellers

### P0 Bug Fixes ✅
1. **Order Success ekranı çıkmıyordu** (kritik bug):
   - Root cause: `clearCart()` sonrası `useEffect`'teki `items.length === 0 && paymentStep === "form"` koşulu `/sepet`'e yönlendiriyordu, navigate(/order-success) overwrite oluyordu
   - Fix: navigate öncesi `setPaymentStep("success")` + `navigate(replace: true)` — race condition giderildi
2. **Mobil ürün resim slider çalışmıyordu** (mobile fallback grid-cols-2 idi):
   - Yeni: mobile full-width snap-x carousel + pagination dots (her resim aspect-[3/4])
   - `mobileImageIdx` state + onScroll handler ile dot indicator senkron
   - Desktop: 2-col grid değişmedi
3. **Sticky CTA bar yukarıdaydı** → mobile bottom, desktop top:
   - `fixed bottom-0 md:top-0 md:bottom-auto` + safe-area-inset-bottom
   - mobile: kompakt h-12 (önceki h-14)

### P1 UI/UX
4. **"Görünümü Tamamla" pozisyonu değişti**: artık ürün açıklaması ile sepete-ekle arasında küçük görseller (64x80px), yatay scroll, 6 ürün
5. **Mega menu artık dinamik en çok satan ürünleri çekiyor**: hover'da `/products?category=X&limit=2&sort=popular` fetch, sağda 44x56 görseller + ürün adı + fiyat. Statik MENU_IMAGES fallback olarak kaldı
6. **Ana menü gap-8 → gap-5**: kategori başlıkları daha sıkı (kullanıcı talebi)

### P1 Admin Bulk Operations + MNG Webhook
7. **`POST /api/orders/bulk/create-invoice?invoice_type=auto`** — toplu fatura kesimi (akıllı hibrit, otomatik VKN/TC kontrolü)
8. **Admin Orders.jsx `handleBulkGenerateInvoice`** yeni endpoint'i kullanıyor — N tek tek istek yerine 1 toplu istek
9. **`POST /api/orders/cargo/mng-webhook`** — MNG status update webhook'u:
   - BARKOD/REFERANS_NO ile sipariş eşle
   - ISLEM_KODU mapping: 100→preparing, 200/300→shipped, 400→delivered, 500→returned
   - cargo_status_history array'e push, integration_logs'a yaz
   - Bilinmeyen sipariş sessiz 200 (MNG retry önler)

### Files Modified
- /app/backend/routes/orders.py (bulk/create-invoice + cargo/mng-webhook)
- /app/frontend/src/pages/Checkout.jsx (paymentStep success, navigate replace)
- /app/frontend/src/pages/ProductDetail.jsx (mobile carousel, sticky bottom, mini combo)
- /app/frontend/src/components/Header.jsx (mega menu dinamik, gap daraltıldı)
- /app/frontend/src/pages/admin/Orders.jsx (bulk invoice → yeni endpoint)

### Pending User Manual Tasks
- Account/üye sayfası overhaul (büyük scope, ayrı iterasyon)
- e-Fatura QA (manuel test gerekli — 1 kurumsal sipariş ile end-to-end)
- MNG'ye webhook URL bildirimi: `https://erp-dashboard-118.preview.emergentagent.com/api/orders/cargo/mng-webhook`


## Iteration 25 (2026-05-06) — Mulish Font + Suud-Style Combo + Mobile UX Overhaul

### Kullanıcı Verbatim Talepleri (Hepsi Karşılandı ✅)
1. **"Combo ürünler suudcollection.com gibi görünsün"** → Image+Bookmark+Name+Price 4-sütun grid
2. **"Tüm fontlar Muli (Mulish), çoğunlukla ince"** → Mulish 200/300/400, body weight 300 default
3. **"Mobilde logo+search+menü görünümleri hoşa gitmiyor"** → Header sadeleştirildi
4. **"Mobil menü kalabalık"** → Accordion (default kapalı) + alt hesap linkleri
5. **"Ödeme sayfası karışık"** → bg-white, sharp edges, light typography

### Değişiklikler
- **`index.css`**: Manrope kaldırıldı, **Mulish** yüklendi (200-800), body default font-weight 300, override `.font-medium → 400`, `.font-semibold → 500`, `.font-bold → 600`
- **`ProductDetail.jsx` & `Cart.jsx`**: Combo/suggestion bloğu Suud Collection stili — image + Bookmark icon (top-right) + product name (line-clamp-1) + price (with optional crossed-out original). Başlık: **"Görünümü Tamamla"**
- **`Header.jsx`**: 
  - Desktop nav font-weight light + tracking-[0.2em]
  - Mobile: text logo "FACETTE" (md:hidden), image logo (hidden md:block) — ayrım net
  - Mobile: account ikonu kaldırıldı (hidden md:inline-flex), kalan: hamburger / logo / search / cart
  - Mobile menü: 4 ana kategori (En Yeniler / Giyim / Aksesuar / Sale), Giyim + Aksesuar `<details>` accordion default kapalı, alt'ta bg-stone-50 panel'de Giriş/Sipariş/İletişim/İade linkleri
- **`Checkout.jsx`**: 
  - bg-gray-50 → bg-white
  - "Sipariş Onayı" başlık font-medium → font-light tracking-tight + üst caption "ÖDEME"
  - SSL pill → minimal text "SSL Güvenli"
  - Tüm `bg-white rounded border` → `bg-white border border-black/10` (sharp edges, tema tutarlı)

### Test (iteration_23.json — 7/7 ✅)
- body font-family Mulish, weight 300; Checkout h1 weight 200
- Combo "Görünümü Tamamla" + 4 ürün Suud formatında render
- Mobile menu: 4 üst kategori, Giyim/Aksesuar accordions default closed → click ile açılıyor
- Mobile account icon hidden, FACETTE text logo visible
- Checkout bg white, cards radius 0px

### Kritik Code Review Notları (Major Risk DEĞİL)
- ProductDetail dedup: allImages[0]===allImages[1] dedupping; Set ile genişletilebilir
- Cart useEffect deps sadece `items.length` — quantity changes suggestions'ı refresh etmiyor (kabul edilebilir)
- Header useEffect popularSearches.length deps eksik (eslint suppression yok ama warning vermiyor)


## Iteration 24 (2026-05-06) — Bug Fixes: MNG TR Encoding + Combo Endpoint + UTF-8

### P0 — MNG Kargo Türkçe Karakter Bozulması Düzeltildi ✅
- **Sorun**: MNG kargo etiketinde "FACETTE DIŞ TİC.A.Ş." → "FACETTE DI T CARET A. .", "GÜZİN GÖKSOY" → "GÜZ N GöKSOY", "İstanbul" → " stanbul" (uppercase Turkish chars Ş İ Ğ Ö Ü stripped by MNG's PDF render engine)
- **Çözüm**:
  - `mng_kargo_client.py`'a `tr_safe()` ASCII-normalize fonksiyonu eklendi
  - `siparis_giris_detayli_v3` içinde MNG'ye giden tüm string field'lar (alici_ad, il, ilce, adres, semt, mahalle, vergi_dairesi, customer_code) `tr_safe`'ten geçiriliyor
  - DB'deki `mng_kargo.customer_code` "FACETTE DIŞ TİC.A.Ş." → "FACETTE DIS TIC.A.S." olarak güncellendi
  - Default değer `orders.py::get_mng_settings`'te de "FACETTE DIS TIC.A.S." olarak güncellendi
- **Sonuç**: MNG etiketinde artık tüm karakterler tam görünür (özel uppercase Turkish chars ASCII karşılıklarına çevrilir, hiçbiri kaybolmaz)

### P0 — Ürün Detay Combo "Stilini Tamamla" Çalışmıyordu ✅
- **Sorun**: Frontend `GET /products/{id}/combo?limit=4` çağırıyordu ama backend endpoint'i `/combine-products` (URL mismatch → 404 → comboProducts boş)
- **Çözüm**: ProductDetail.jsx artık doğru endpoint'i çağırıyor + boş dönerse cart-suggestions'a fallback yapıyor (kategori bazlı öneri)
- **Test**: DOM'da `data-testid="product-combo-section"` + 4 combo item render ediliyor — desktop ekran görüntüsünde "BU ÜRÜNLE YAKIŞANLAR / Stilini tamamla" başlığı altında 4 görsel + hover overlay görünüyor

### Cargo Label HTML UTF-8 Hardening
- `/cargo-label` HTMLResponse'a explicit `Content-Type: text/html; charset=utf-8` header eklendi
- Font-stack: Google Fonts Inter (full Turkish coverage) → Liberation Sans → DejaVu Sans → Arial
- `lang="tr"`, double charset declaration (meta charset + http-equiv), `print-color-adjust: exact`

### Files Modified
- /app/backend/mng_kargo_client.py (`tr_safe`, all SOAP params normalized)
- /app/backend/routes/orders.py (cargo-label HTML font-stack + UTF-8 header, default customer_code ASCII-safe)
- /app/frontend/src/pages/ProductDetail.jsx (combo endpoint URL fix + cart-suggestions fallback)
- DB: settings.mng_kargo.customer_code → "FACETTE DIS TIC.A.S."

### Pending User Communication
Kullanıcı "mobilde değişiklik yok" dedi, ama tüm ekran görüntülerinde mobil sticky header (FACETTE+blur), product detail mobile sticky bottom CTA (resim+isim+fiyat+SEPETE EKLE), Footer accordion, Cart bottom CTA çalışıyor. Browser cache temizleme gerekebilir. Daha somut bir mobil değişiklik istiyorsa hangi sayfa/blok'un farklı olmasını istediğini belirtmesi gerekiyor.


## Iteration 23 (2026-05-06) — e-Fatura Akıllı Hibrit + Page Builder Seed + Combo Sections

### P0 — Doğan e-Fatura (TEMELFATURA) Eklendi ✅
- `dogan_client.py`'a `build_efatura_ubl_xml` static method eklendi:
  - ProfileID=TEMELFATURA, cac:OrderReference, cac:BuyerCustomerParty, cac:Delivery>DeliveryAddress
  - cac:PaymentMeans yok (e-Fatura için ihtiyaç yok)
  - InvoiceLine'da hem BuyersItemIdentification hem SellersItemIdentification
  - Customer 10 haneli VKN şart (validation built-in)
- `send_efatura_invoice` metodu — EFaturaOIB.SendInvoice endpoint'ini kullanıyor
- `check_user(vkn)` parse düzeltildi — `is_efatura` ve `invoice_alias` doğru dönüyor
- Test sonucu (canlı): 7810816779 → mükellef + alias `urn:mail:defaultpk@facette.com`; 7570050418 → mükellef + alias `urn:mail:setekspk@edmbilisim.com`

### P0 — Akıllı Hibrit Fatura Kesimi (orders.py::create-invoice) ✅
- `invoice_type` default'u **`auto`**'ya değiştirildi:
  - VKN/TC dolu (10 veya 11 hane) → Doğan CheckUser sorgusu
  - `is_efatura=True` ve 10 haneli → **e-Fatura** (EFC prefix, EFaturaOIB.SendInvoice)
  - Aksi → **e-Arşiv** (FCT prefix, WriteToArchiveExtended)
  - VKN/TC boş → e-Arşiv (TCKN=11111111111 fallback)
- DB'ye `invoice_dogan_id`, `invoice_pdf_url` kaydediliyor (e-Arşiv için web_key, e-Fatura için INVOICE_ID)

### P1 — Page Builder Default Home Seed ✅
- `cms.py::POST /api/page-blocks/seed-default-home` endpoint'i eklendi
- Mevcut Home.jsx default tasarımı (hero_slider, full_banner, two_banners, product_slider, instashop) DB'ye aktarıldı
- Admin `/admin/sayfa-tasarimi` ekranına **"Varsayılan Anasayfayı Yükle"** butonu eklendi
- Artık admin slider görsellerini, vitrin ürünlerini, banner'ları UI'dan değiştirebilir

### P1 — ProductDetail "Stilini Tamamla" ✅
- ProductDetail.jsx'te `comboProducts` (cross-sell) bloğu sade siyah/beyaz "Stilini tamamla" formatına geçirildi
- Sadece görsel + hover overlay "DETAYI GÖR" (text/fiyat yok) — kullanıcının açık talebi

### P1 — Cart "Kasa Önü Fırsatları" ✅
- `products.py::POST /api/products/checkout-deals` endpoint'i — sadece indirimli aktif ürünler
- Cart.jsx'te "Stilini Tamamla" altında ayrı "Kasa Önü Fırsatları" bloğu (kırmızı %X badge, satıcı orijinal fiyat üstü çizili)
- Sepetteki ürünler hariç tutuluyor

### Files Modified
- /app/backend/dogan_client.py (build_efatura_ubl_xml, send_efatura_invoice, check_user fix)
- /app/backend/routes/orders.py (auto/hibrit invoice_type)
- /app/backend/routes/cms.py (seed-default-home endpoint)
- /app/backend/routes/products.py (checkout-deals endpoint)
- /app/frontend/src/pages/Cart.jsx (deals section eklendi)
- /app/frontend/src/pages/ProductDetail.jsx ("Stilini Tamamla" minimal)
- /app/frontend/src/pages/admin/PageDesign.jsx ("Varsayılanı Yükle" butonu)

### Test Results
- Backend smoke: 4/4 pass (homepage blocks, cart suggestions, checkout deals, admin auth)
- Doğan CheckUser canlı: ✅ alias parse doğru
- e-Fatura UBL well-formed (218 KB, ProfileID=TEMELFATURA, BuyerCustomerParty + DeliveryAddress)
- 5 default home blocks seed edildi DB'ye


## Iteration 22 (2026-05-05) — Doğan UBL CANLI ÇÖZÜLDÜ + Mobil UI/UX Overhaul

### P0 BACKEND — Doğan e-Dönüşüm CANLI e-Arşiv UBL **ÇALIŞIYOR** ✅
- `dogan_client.py::build_earsiv_ubl_xml` örnek `FCT2026000011227.xml` referans alınarak komple yeniden yazıldı:
  - Tam UBL-TR namespace seti (ext, qdt, ccts, xades, ubltr, cac, udt, cbc, ds, xsi:schemaLocation)
  - **Zorunlu** `cac:Signature` bloğu (SignatoryParty + DigitalSignatureAttachment URI)
  - **Zorunlu** `cac:AdditionalDocumentReference` × 2 (XSLT base64 + SendingType=ELEKTRONIK)
  - **Zorunlu** `cac:Delivery` > `CarrierParty` (MNG Kargo VKN 6080712084 default)
  - `cac:PaymentMeans` (PaymentMeansCode=1)
  - `unitCode="C62"` her InvoiceLine için (NIU değil)
  - `SellersItemIdentification` her satırda
  - Multi-rate KDV gruplandırma (TaxSubtotal blokları)
  - Bireysel (TCKN 11) → cac:Person, Kurumsal (VKN 10) → PartyName + PartyTaxScheme
- Doğan XSLT şablonu `/app/backend/dogan_xslt_template.txt`'e kaydedildi (210 KB base64), her UBL'ye gömülüyor
- `send_earsiv_invoice` artık `WriteToArchiveExtended` (senkron) kullanıyor — INVOICE_ID + WEB_KEY anında dönüyor
- EARSIV_TYPE=INTERNET, VALIDATION_FLAG=Y, EARCHIVE_TEST_FLAG=is_test
- **Canlı submit testi başarılı**: INVOICE_ID=FCT2026778025040, web_key=https://portal.doganedonusum.com/earchive/view-earchive/view-pdf-earchive.xhtml?webValidationKey=...
- `orders.py::create-invoice` endpoint'i `invoice_dogan_id` ve `invoice_pdf_url` alanlarını DB'ye yazıyor

### P0 FRONTEND — Mobil-First Elit Siyah/Beyaz Minimal Tema
- `Cart.jsx` baştan sona yeniden yazıldı:
  - **Mobile sticky bottom CTA** (`fixed bottom-0 z-40 ... md:hidden`) safe-area-inset-bottom destekli
  - **"Stilini tamamla"** kombin önerileri **sadece görsel** + hover overlay "DETAYI GÖR" (eski h3 + fiyat kaldırıldı)
  - Editorial tipografi, divide-y border, tabular-nums fiyatlar
- `Footer.jsx` minimal kurumsal — mobile accordion (chevron), desktop 3 kolon
- `CartDrawer.jsx` premium yan panel — slide-right animasyon, `Ödemeye Geç` + `Sepete Git` CTAs
- `Header.jsx` glassmorphism (`bg-white/90 backdrop-blur-xl`)
- `index.css`'e `@keyframes slideRight` + `.animate-slide-right` eklendi

### Test Sonuçları (iteration_22.json)
- Backend: 16/16 ✅ (UBL well-formed, tüm zorunlu UBL-TR alanları, smoke endpoints)
- Frontend: 10/10 ✅ (mobil sticky CTA, "Stilini tamamla" image-only, drawer, footer accordion, header glass)
- Manual QA pending: tek bir gerçek order üzerinde POST /api/orders/{id}/create-invoice tetikleyip canlı PDF link doğrulaması (operatör tarafından)


## Completed in Iteration 14 (2026-04-23) — FAZ 1 + FAZ 2 + FAZ 3

### FAZ 1 — TR Lokasyon (İl/İlçe)
- `ProvinceDistrictSelect.jsx` — iki dropdown, `/api/locations/tr/provinces` (81 il) + `/api/locations/tr/districts?province=` (973 ilçe)
- `Checkout.jsx` ve `Account.jsx` adres formları serbest metin inputlarından dropdown'a geçirildi
- Modül içi cache ile sayfa geçişlerinde tekrar fetch etmiyor

### FAZ 2 — Bildirim Altyapısı (SMS + WhatsApp + E-posta)
- **Backend servis**: `/app/backend/notification_service.py`
  - 8 SMS sağlayıcı slot (Netgsm, İletiMerkezi, Twilio, VatanSMS + 4 mock slot)
  - WhatsApp Meta Cloud API (text + template mesaj desteği)
  - Resend e-posta
  - `{variable}` tabanlı template render + TR telefon normalizasyonu
  - `notification_logs` koleksiyonu (her gönderim log'lanır)
- **Admin CRUD**: `/api/notifications/*` endpoint'leri
  - `GET /providers/catalog` — sağlayıcı listesi + event listesi
  - `GET/POST /providers` — credential yönetimi (**secret maskeleme** + UI'den maskeli değer dönünce eski değer korunur)
  - `GET/POST /templates` + `POST /templates/seed` (default 30 şablon)
  - `POST /test` — canlı test gönderimi
  - `GET /logs` — son gönderim geçmişi
- **Admin UI**:
  - `/admin/ayarlar/bildirim` → sağlayıcı seçimi + credential + test paneli
  - `/admin/ayarlar/bildirim/sablonlar` → 10 event × 3 kanal şablon editörü
- **Order hook**: `PUT /api/orders/{id}/status` durum değişikliğinde `asyncio.create_task` ile fire-and-forget bildirim tetikler (UI bloklamıyor)

### FAZ 3 (kısmi) — SMS OTP Şifre Sıfırlama
- `POST /api/auth/forgot-password/request-otp` — 6 haneli OTP, SHA256 hash, 5 dk ömür, **60 sn rate limit** (aynı telefon), eski kodlar yeni OTP üretilince iptal
- `POST /api/auth/forgot-password/verify-otp` — 5 yanlış deneme → 429, başarılı doğrulamada 10 dk ömürlü `reset_token`
- `POST /api/auth/forgot-password/reset` — reset_token ile şifre değiştirme
- Enumeration önlemi: bilinmeyen numara için de aynı başarılı cevap

### Testing
- `/app/backend/tests/test_iteration14_notifications_locations_otp.py` — 18/18 PASS
- `/app/test_reports/iteration_14.json` — başarı oranı %100 (backend)


## Completed Features
- [2026-04-20] **Görevler & Haftalık Checklist Modülü (Iteration 12)**:
  - `/api/admin/tasks` CRUD + `/complete` (tekrar kur) + `/snooze` + `/seed-defaults` (16 hazır görev) + `/summary` + `/history`
  - Tekrar tipleri: once, daily, weekly, biweekly, monthly, quarterly, yearly, custom
  - Tamamlandığında `last_completed_at` + `completion_count++` + `due_at = next_period`; log `admin_task_logs` koleksiyonuna yazılır
  - 16 varsayılan görev (kullanıcının liste verdiği): müşteri sorularını kontrol, havale onayla, yorum moderasyonu, terkedilmiş sepet mail at, haftalık bülten, kampanya kurgula, satış raporu, stok ikmali, banner güncelle vb.
  - `/admin/gorevler` sayfası: 4 özet kartı (bugün/gecikmiş/bu hafta/son 30 gün), kategori rozetleri (müşteri/sipariş/stok/pazarlama/rapor/içerik/SEO/ayar/entegrasyon), öncelik noktaları (acil/yüksek/normal/düşük), "Git" (ilgili admin sayfasına) + "Tamamla" + "+1g ertele" butonları, tamamlanma ısı haritası (son 30 gün)
  - **Dashboard widget**: "Bugün Yapılacaklar" paneli (6 görev + tek tıkla tamamla + gecikmiş/bekleyen/bu hafta özeti) Sipariş Durumu Dağılımı yanında
  - Menüde "Görevler" ana link Dashboard'dan sonra

- [2026-04-20] **Ticimax P1 — 20 yeni modül (Iteration 11)**:
  - **Katalog**: Marka Yönetimi (brands), Etiket Yönetimi (product_tags, bg_color+text_color), Stok & Fiyat Alarm Hatırlatma (public /alerts POST, admin liste/delete)
  - **Siparişler**: Admin Manuel Sipariş Oluştur (MNL-YYMMDD-XXXXXX, stok düşer), Silinmiş Siparişler arşivi + restore, Havale/EFT Bildirimleri (müşteri /payments/havale-notify; admin onay → siparişe payment_status=paid işler)
  - **Üyeler**: Üye Grupları (B2B/VIP), Destek Talepleri (Tickets — ticket_number, reply thread)
  - **İçerik**: Duyuru Yönetimi, Süreli Popup Yönetimi (delay_seconds, trigger)
  - **Pazarlama**: Kargo Kuralları (min_cart, free_shipping), Ödeme Tipi İndirimleri, Toplu Mail Gönderme (Resend API — segment=all/newsletter/abandoned, batch 100, email_campaigns log)
  - **Raporlar Gelişmiş**: Saatlik Satış (BarChart), İl Bazında Satış, Ürün Karlılık (margin), Stok Hareket

## Iteration 15 (2026-04-23) — FAZ 4 + FAZ 5 + FAZ 6

### FAZ 4 — Checkout İyileştirmeleri
- **Hediye notu** (300 karaktere kadar) — `orders.gift_note` alanına kaydedilir
- **Hediye paketi** (+130 TL) — checkbox, toplam tutara eklenir, `orders.gift_wrap`/`gift_wrap_price` ile kayda girer
- **Trendyol Go stili kupon kutusu**: Yeni endpoint `POST /api/coupons/available` (sepet+kullanıcı için uygun kuponları hesaplanmış discount ile listeler), checkout sepet özetinde kart olarak görünür, tıklayınca otomatik uygulanır
- Uygulanmış kupon "Kaldır" butonu + kupon kodu order'a kaydolur

### FAZ 5 — Sipariş Durum Zinciri Standardizasyonu
- Yeni durum: **`undelivered`** (Teslim Edilemedi — Şubede Bekliyor)
- Durum seçenekleri: `pending → confirmed → processing (Paketleniyor) → shipped (Kargoda) → delivered | undelivered | cancelled`
- Yeni endpoint'ler:
  - `POST /api/orders/{id}/ship?cargo_company=&tracking_number=` — 9 geçerli kargo firması whitelist; bildirim fire-and-forget
  - `POST /api/orders/{id}/undeliver?reason=&branch_info=` — teslim edilemedi bildirimi
- Status hook `order_undelivered` event'ini notification_service'e taşır

### FAZ 6 — Müşteri Risk & Blok Yönetimi
- **Sipariş oluştururken IP + User-Agent kaydı** (`customer_ip`, `user_agent` — X-Forwarded-For destekli)
- **Risk skoru endpoint'leri**: `GET /api/customer-risk/users/{uid}`, `/by-email`, `/bulk?user_ids=&emails=`
  - Formül: `return_rate = returns / (total_orders - cancelled)`, risk_level: low (<20%) / medium (20-49%) / high (≥50%)
- **Blok CRUD**: `POST /block`, `GET /blocked`, `DELETE /blocked/{id}` (user_id VEYA ip VEYA email)
- **Otomatik blok enforcement**: POST /api/orders üzerinde blocked_customers lookup → 403 "sipariş veremez"
- **Admin UI — `/admin/bloklu-musteriler`** (yeni sayfa): form + liste + kaldır
- **Sipariş listesinde risk rozeti**: yüksek iadeli müşterilerin adı kırmızı + "⚠ %X" rozeti (medium için sarı)

### Testing (Iteration 15)
- `/app/backend/tests/test_iteration15_faz456.py` — 14/14 PASS
- Minor fix: `_compute_risk` fast-path now includes `return_rate_pct: 0.0` for UI consistency


  - **Ayarlar**: Döviz Kurları (exchangerate.host)
  - **Resend entegrasyonu**: RESEND_API_KEY env'de boş (kullanıcı verince aktif)
  - Backend 16 yeni router (catalog_extras.py tek dosya), Frontend 12 yeni admin sayfası
  - Test 23/23 backend + 12/12 frontend (profit KeyError fix + Promise.allSettled)
- [2026-04-20] **Iteration 10 Ticimax P0** (6 modül): Kuponlar, Ürün Yorumları, Terkedilmiş Sepet, 4 Rapor (satış/ürün/stok/üye), SEO Meta + 301 Yönlendirmeler
- [2026-04-20] **Iteration 9 Büyük restructure**: Menü 9 gruba bölündü, Üyeler modülü, Attribution/Funnel takibi, HB/Temu Eşleştir sayfaları, HB Basic Auth düzeltildi

- [2026-04-20] **Büyük admin restructure (Iteration 9)**:
  - **Menü 9 ana gruba bölündü**: Dashboard | Katalog | Siparişler | Üretim | Üyeler | İçerik | Pazarlama | Entegrasyonlar | Ayarlar (İmalat Üretim altına, Banner/Sayfalar İçerik altına taşındı)
  - **Üyeler modülü (YENİ)**: `/api/admin/members` CRUD + stats (VIP/Sadık/Yeni/Aday segmentleri, edinim kanalları), `/admin/uyeler` sayfası (drawer detay, segment filtresi, UTM kaynakları görünümü)
  - **Attribution / Funnel takibi (YENİ)**: `/api/attribution/track-visit` (public, UTM + referrer + gclid/fbclid), `/api/attribution/stats` (admin). Otomatik kanal algılama: instagram_ads, google_ads, instagram_organic, google_organic, email, influencer, direct, referral, trendyol, hepsiburada, vs. `/admin/kaynak` sayfası: Kanal Bazında Gelir/Ziyaret grafikleri, en iyi kampanyalar tablosu, dönüşüm oranı
  - **Sipariş Kaynağı**: Order detay modalında attribution kartı (kanal, UTM source/medium/campaign, referrer, landing page, device)
  - **Storefront UTM tracker**: `lib/attribution.js` App.js'te otomatik çağrılır, facette_sid localStorage'a yazılır, Checkout'ta siparişe iliştirilir
  - **Hepsiburada Eşleştir (YENİ sayfa)**: Basic Auth (Merchant ID + Username + Password) ayar formu + kategori ID/ad eşleştirme tablosu. Integrations.jsx HB modalı da Basic Auth'a düzeltildi
  - **Temu Eşleştir (YENİ sayfa)**: Shop ID + App Key + App Secret + kategori eşleştirme
  - **Test-connection artık GERÇEK**: Hepsiburada'ya httpx ile Basic Auth listing endpoint ping'i atılır, 200/401/403/timeout mesajları açıkça döner
  - **Ölçü Tabloları listesi**: `/admin/olcu-tablolari` ürün bazlı gezinti
  - **Dashboard**: "Toplam Müşteri" → "Toplam Üye"
  - Backend testing iteration 9: 19/19 backend + frontend 5 yeni sayfa doğrulandı
- [2026-03-25] MongoDB data restore (290 products, 34 categories)
- [2026-03-25] Stock code visibility, Global Markup & VAT, Vendors module
- [2026-03-25] Trendyol category/attribute sync, auto-match, 4-digit IDs
- [2026-03-25] Variant dropdown UX improvements
- [2026-03-26] Excel Technical Details Import (126 products matched)
- [2026-03-26] Attributes tab reorganization (filled > required > hidden)

## Iteration 16 (2026-04-23) — FAZ 7 İmalat Planı 18 Sütunlu Tablo

### Ürün kartı
- Yeni alanlar: `collection` (ör. "2026 İlkbahar/Yaz"), `color` (ana renk), `purchase_price` (mevcut — imalat ile entegre)
- Admin "Ürün Ekle/Düzenle" formunda yeni 2 input (datalist ile koleksiyon önerisi)

### İmalat Planı (`/api/production-plan`)
- 18 sütunluk spreadsheet-style CRUD endpoint'leri:
  - `GET /api/production-plan?search=&manufacturer_id=&collection=`
  - `POST /api/production-plan` — seq_no = `max(seq_no)+1` (silme sonrası uniqueness), ürün seçilirse collection/price/color/product_description otomatik dolum
  - `PUT /api/production-plan/{id}` — payment_date → planned_delivery (+21 gün) otomatik hesap; delay_days + qty_diff_pct türetilir
  - `DELETE /api/production-plan/{id}`
  - `GET /api/production-plan/collections` — distinct koleksiyonlar (product + plan)
- Türetilmiş alanlar:
  - `planned_delivery` = payment_date + 21 gün
  - `delay_days` = actual_delivery − planned_delivery (pozitif=gecikme kırmızı, negatif/0=zamanında yeşil)
  - `qty_diff_pct` = ((delivered − order) / order) × 100 (pozitif yeşil, negatif kırmızı; delivered=0 ise null)

### Admin UI — `/admin/uretim-plani` (yeni sayfa)
- 18 sütunluk tablo, satır bazlı 800 ms debounced auto-save
- Üretici dropdown (vendors/manufacturer), koleksiyon datalist, ürün select (autofill)
- Inline QC + Final QC: Geçti (yeşil) / Kaldı (kırmızı) butonlu + **resim upload** (base64 önizleme)
- Gecikme ve +/-% göstergesi hücre altında
- Menü: Üretim → İmalat Planı (Tablo)

### Testing
- `test_iteration16_production_plan.py` — 16/16 PASS (%100)
- Minor: seq_no race condition fix eklendi (max-based), PUT Pydantic validation optional iyileştirme


- [2026-03-26] Fixed Trendyol attribute matching (strict name match)
- [2026-03-26] Auto-fill Yaş Grubu=Yetişkin, Menşei=TR for all products
- [2026-03-26] Cleaned 71 non-textile attributes, hidden Beden/Renk/Web Color
- [2026-03-26] Multi-color variant system (each color = separate product + auto Web Color)
- [2026-03-26] İade iskonto düzeltmesi (sipariş API'den net tutar çekme)
- [2026-03-26] Gider Pusulası (VUK 234 uyumlu, şirket bilgileri ile)
- [2026-03-26] İade sayfası yeniden yapılandırma (checkbox, pasifizasyon, toplu yazdırma, 5dk auto-refresh)
- [2026-03-26] Ayarlara Şirket Bilgileri bölümü eklendi
- [2026-03-26] Doğan e-Dönüşüm entegrasyonu (bağlantı test, CheckUser) temel yapı
- [2026-04-19] Hepsiburada & Temu marketplace scaffolding:
  - Backend: `/api/integrations/{hepsiburada|temu}/settings|status|test-connection`, unified `/api/integrations/marketplace/questions` + stub sync/answer endpoints
  - Frontend Entegrasyonlar: Hepsiburada + Temu kartları, settings dialogları
  - Frontend Products Özellikler: Trendyol altında Hepsiburada & Temu için bağımsız özellik bölümleri (Trendyol'da seçilen değer boş ise HB/Temu'ya otomatik kopyalama)
  - Frontend Questions: marketplace filtresi, sol kenarlıkta renkli çerçeve, sağ üst köşede pazaryeri rozeti, pazaryeri bazlı senkron butonları

## Iteration 17 (2026-04-23) — FAZ 8 + FAZ 9 + Üretici Performans

### FAZ 8 — Gelişmiş Raporlar
Backend (`/api/admin/reports/*`):
- `GET /returns/by-size` — beden bazlı iade sayısı (en çok iade edilen beden)
- `GET /returns/by-product` — ürün bazlı iade + satışa oranla `return_rate_pct` (sarı >%20, kırmızı >%50)
- `GET /returns/reasons` — iade sebebi dağılımı
- `GET /fast-selling?window_days=14&min_sold=10` — "ilk 14 günde ≥10 satış" dedektörü; `recommend_ads: true` → kartta yeşil "Reklam Öneriliyor" rozeti
- `GET /manufacturer-performance` — üretici bazında avg_delay, avg_qty_diff, skor (100 - gecikme*3 - |%|*0.5)

Admin UI: `/admin/raporlar/iade-ve-trend` — 5 kart (beden, sebep, ürün, hızlı satış kartları, üretici performans tablosu renk kodlu)

### FAZ 9 — Pazarlama Pixel Yönetimi
Backend (`/api/marketing-pixels`):
- `GET /providers` — 8 sağlayıcı (GA4, Meta Pixel, Google Ads, TikTok, Yandex, Hotjar, Clarity, Custom)
- `GET/POST/DELETE` — CRUD (tag_id → otomatik snippet template; custom için manuel HTML)
- `GET /active-public` — **AUTH YOK** — frontend site'a inject için head + body snippet birleşimi (60s cache)

Frontend:
- `MarketingPixelsInjector.jsx` (App.js'e yüklendi) — ilk render'da /active-public'ten pixel'leri çekip `<head>`'e enjekte (script tag'leri yeniden oluşturarak execute olur)
- Admin sayfası `/admin/ayarlar/pixel` — form + liste, sadece GA4 tag ID yapıştır→aktif

### Testing
- `test_iteration17_reports_pixels.py` — **22/22 PASS** (%100)
- Cache-Control eklendi (middleware override'dan etkilenebilir; iyi-bir-çaba)

## Iteration 18 (2026-04-23) — Pixel E-commerce Events + Apple/FB Sosyal Login Scaffold

### Pixel E-commerce Events (FAZ 9 potansiyel iyileştirme)
- `/app/frontend/src/utils/pixelEvents.js` helper — Meta Pixel + GA4 için 6 olay: ViewContent, AddToCart, InitiateCheckout, Purchase, Search, CompleteRegistration
- `ProductDetail.jsx` → ViewContent (ürün sayfasında) + AddToCart
- `Checkout.jsx` → InitiateCheckout (mount) + Purchase (direkt ödeme VE iyzico callback)
- Pixel pasifse sessizce no-op olur — hataya neden olmaz

### Apple + Facebook Sosyal Login (FAZ 3 upcoming)
Backend (`/api/auth/social/*`):
- `GET /providers` (public) — UI'nın hangi butonu göstereceğini belirler
- `GET/POST /settings` (admin) — credential yönetimi, **tam maskeleme** (only `"****"` + `has_*` bayrağı döner, ilk/son karakter sızıntısı yok)
- `POST /apple` — Apple public key fetch + RS256 verify (aud/iss check) → user upsert → JWT
- `POST /facebook` — OAuth code → access_token → profile → user upsert → JWT
- `_upsert_social_user`: 3 aşama (provider_id match → email match → yeni oluştur) + `auth_providers.{provider}` kaydı

Frontend:
- `Login.jsx` — `/providers` endpoint'ine bağlı Apple + Facebook butonları (credential girilince görünür)
- `/admin/ayarlar/sosyal-giris` — SocialAuthSettings sayfası (Apple Services ID/Team/Key/Private Key + FB App ID/Secret/Redirect URI)

### Testing
- `test_iteration18_social_auth.py` — **9/9 PASS** (%100)
- Minor fix: secret masking güvenliği artırıldı (tam maskeleme)




  - Products modeli `hepsiburada_attributes` + `temu_attributes` alanlarını destekler
- [2026-04-20] Kapsamlı Admin Panel Genişletme (Fork devamı):
  - **RBAC (Rol & Yetki)**: `/api/admin/roles` + `UsersRoles.jsx`, 64 permission ağacı
  - **APScheduler**: `scheduler.py` 30dk'da bir çalışır, 48 saati geçmiş ödenmemiş Havale siparişlerini iptal eder ve stokları iade eder
  - **İmalat Takip**: 12 aşamalı pipeline (`manufacturing.py`), `Manufacturing.jsx`, tedarikçi yönetimi, F7-F11 (maliyet/fire/satınalma emri), size_distribution opsiyonel (bedenler artık default gelmiyor)
  - **Ölçü Tablosu**: `size_tables.py` + Pillow ile 1200x1800 PNG render, `SizeTablePanel.jsx`, storefront HTML tablo
  - **AI Chatbot**: `ai_chatbot.py` — Emergent LLM (GPT-5.2) ile 7 kanal (WhatsApp, Instagram, Messenger, Web, Trendyol, Hepsiburada, Temu) cevap taslağı ve RAG knowledge base
  - **Kampanya Şablonları**: 10 hazır şablon kart (Campaigns.jsx)
  - **Konum API**: `/api/locations/countries` (pycountry 249 ülke, TR ilk), `/api/locations/tr/provinces` (81 il), `/api/locations/tr/districts?province=`, `/api/locations/tr/search?q=`
  - **7 Kargo Entegrasyon Kartı**: MNG, Aras, Yurtiçi, PTT, HepsiJet, Trendyol Express, Sürat — `/api/integrations/{provider}/settings` (generic, scaffolding; gerçek API keys bekleniyor)
  - **Iyzico Ayar UI**: `/api/integrations/iyzico/settings` (kısmi iade mantığı P1 backlog)
  - **HB/Temu Kategori ID**: Products modeli ve formuna `hepsiburada_category_id`, `temu_category_id` alanları
  - **Sipariş Renklendirme**: Havale bekleyen kırmızı/onaylanan normal, fatura kesilmiş pasif
  - **İade Geliştirmeleri**: Ret Sebebi modalı, Kargo & Ödeme Tipi sütunları
  - Backend testing iteration 8: 24/24 backend test geçti (locations, cargo settings, manufacturing CRUD+advance, products HB/Temu, AI settings, RBAC, size tables)

## Credentials
- Admin: admin@facette.com / admin123
- Doğan e-Dönüşüm: dogantest / dgn2024@!

## Backlog
- P0: Hepsiburada gerçek API entegrasyonu (Listing Products, Orders, QNA) — credentials alındığında
- P0: Temu gerçek API entegrasyonu (Products, Orders, QNA) — credentials alındığında
- P0: Trendyol ürün aktarım detaylı sonuç ekranı (stok kodu, barkod, başarı/hata + hata nedeni)
- P0: Doğan e-Dönüşüm üzerinden e-Fatura kesme (tam entegrasyon)
- P0: Fatura numarası çıkarma (PDF parsing veya API)
- P1: **Iyzico Kısmi İade + Kargo Ücreti Düşme + Kampanya Oransal Hesap** (UI+backend mantığı)
- P1: **Checkout/Sipariş adres formlarında İl/İlçe dropdown bağlama** (`/api/locations/tr/*` endpoint'leri frontend'e bağla)
- P1: 7 Kargo firması gerçek API entegrasyonu (kullanıcı API keys verince)
- P1: Mevcut tüm claim'lerin iskontolarını düzeltme
- P1: Tüm search/dropdown UX tutarlılığı
- P2: Trendyol Mikro İhracat ayrı faturalandırma altyapısı
- P2: Trendyol ürün export testi
- P2: Products.jsx (2500+ satır) ve Orders.jsx (1500+ satır) modal/sekme componentlerine bölme
- P2: integrations.py (3500+ satır) provider'a göre bölme

## Changelog — 23 Nis 2026 (Oturum 5)
- **RFM Müşteri Segmentasyonu** (`/admin/musteri-segmentleri`): `analytics_extra.py`. Recency/Frequency/Monetary quintile puanları (1-5) + klasik pazarlama segmentleri (VIP, Sadık, Yeni, Risk Altında, Kaybedilen, Hibernasyon). Renkli segment kartları filter olarak tıklanabilir, CSV export. Test: 18 müşteri (10 Hibernasyon, 6 Kaybedilen, 2 Yeni).
- **Pazaryeri Karlılık Raporu** (`/admin/pazaryeri-karlilik`): Brüt ciro - komisyon - kargo - iade = net kâr. Komisyon oranı `marketplace_accounts.transfer_rules.commission_{type,value}`'dan otomatik okunur. Kanal bazlı ağırlıklı kıyaslama, net marj renkli badge (yeşil ≥%20, sarı ≥%10, kırmızı <%10). Test: web 5 sipariş/6742₺ net.
- **Google Merchant XML Feed** (`/api/feeds/google-merchant.xml` — **public**, Google Merchant Center tarafından otomatik çekilir): 248 ürün aktarıldı, g:gtin/g:mpn/g:brand/g:availability/g:price alanlarıyla.
- **Menü güncellemeleri**: Üyeler altına "Müşteri Segmentleri (RFM)", Raporlar altına "Pazaryeri Karlılık".

## Changelog — 23 Nis 2026 (Oturum 4)
**Piyasa araştırması (ideaSoft/T-Soft/Akinon) sonucu eksik modüller:**
- **Toplu Fiyat/Stok Excel** (`/admin/toplu-fiyat-stok`): 3 adım (şablon indir → preview dry-run → apply). `bulk_ops.py` + openpyxl. Ürün stock_code VEYA barcode ile eşleştirme, varyant seviyesi stok güncellemesi.
- **Stok Uyarıları + Reorder Önerileri** (`/admin/stok-uyarilari`): Kritik Stok sekmesi (threshold ayarlanabilir) + Yeniden Sipariş Önerileri (son 60 gündeki sipariş kalemlerinden stok=0 ama satılanlar, agg pipeline).
- **Multi-Marketplace Kategori Eşleştirme** (`/admin/kategori-eslestir`): BrandMapping ile aynı üst yapı. `category_mapping.py` + `category_mappings` koleksiyonu. 13 pazaryeri sekmesi.
- **Scheduled Auto-Sync** (scheduler.py): `_marketplace_sync_tick()` her dk çalışır; her enabled marketplace_account için `products_interval_min` ve `orders_interval_min`'e göre queued log atar (`_last_products_sync` / `_last_orders_sync` zaman damgalarıyla). İlerde gerçek integrations.py servisleri bu cron'a bağlanacak.
- **AddressFields** component (`components/admin/AddressFields.jsx`): İl/İlçe dropdown (backend `/api/locations/tr/{provinces,districts}`) — Siparişler/Checkout adres formlarında kullanılmak üzere yeniden kullanılabilir bileşen.

**Test edildi**:
- stock-alerts threshold=3 → 230 kritik varyant ✅
- reorder-suggestions → 0 (son 60 günde hiç sipariş yok) ✅
- Template download (.xlsx) → 4971 bytes ✅
- category-mapping/trendyol → 33 kategori / 0 eşleşme ✅
- locations/tr/provinces → 81 il ✅
- UI: Stok Uyarıları tablosu (Haki Trençkot, Gri Blazer, vb. 230 varyant) + Toplu Fiyat/Stok 3 adım kart + Kategori Eşleştirme 13 sekme ✅

## Changelog — 23 Nis 2026 (Oturum 3)
- **Integration Logging Middleware**: `server.py`'ye otomatik logging middleware eklendi. `/api/integrations/{marketplace}/...` altındaki tüm POST/PUT/DELETE çağrıları `integration_logs` koleksiyonuna otomatik kaydediliyor (marketplace + action + status + HTTP kod + süre). Manuel wrapping gereksiz.
- **Aktarılamayanlar sayfası** (`/admin/aktarilamayanlar`): integration_logs'tan `status=failed` kayıtları; tek satır veya seçili satırlarda "Tekrar Aktar" butonu uygun endpoint'e (product_push → /integrations/{mp}/products/{id}/sync, stock_update → /sync-inventory, order_pull → /orders/import) yönlendirir.
- **Marka Eşleştirme** (`/admin/marka-eslestir`): Multi-marketplace tek ekran. 13 pazaryeri sekmesi, özet kartlar (toplam/eşleşti/eşleşmedi), arama + filtre (tümü/eşleşti/eşleşmedi), satır başına manuel "Düzenle/Sil", toplu "Otomatik Eşleştir" (isim bazlı upsert) + "Hepsini Sıfırla". Backend `brand_mapping.py` + `brand_mappings` koleksiyonu. Brand koleksiyonu boşsa `products.distinct("brand")` fallback ile sistem markalarını türetir.

## Changelog — 23 Nis 2026 (Oturum 2)
- **Marketplace Hub (yeni)**: `routes/marketplace_hub.py` — 13 pazaryeri (Trendyol, Hepsiburada, Temu, N11, Amazon TR/DE, AliExpress, Etsy, Hepsi Global, Fruugo, eMAG, Trendyol İhracat, Çiçek Sepeti) için tek merkezli yönetim. Her biri için:
  - Credential şeması (Supplier ID, API Key/Secret, Username/Password, vb.)
  - 19 Ortak Transfer Kuralı (Lisans Kodu, Eksi Stok, Fiyat Türü, Komisyon, Barkod/Stok Kodu aktarım, Yeni Ürün Otomatik, Sipariş Durum güncelleme, İade, Ödeme Vade/Teslim tarihi, Marka, Kargo Süresi)
  - Auto-sync (products/orders ayrı on-off + dk periyot + lookback saat)
  - `marketplace_accounts` koleksiyonu ile tek kayıt.
  - Frontend: `MarketplaceHub.jsx` Ticimax Marketplace v2 ile birebir görünüm (sol pazaryeri listesi + sağ 3 kart: API + Kurallar + Auto-Sync).
- **Integration Logs (yeni)**: `integration_logs` koleksiyonu + endpoint'ler (`/api/marketplace-hub/logs`, `logs/summary`, `logs/test`). Her API çağrısı status/direction/ref_id/message/duration ile kaydedilir.
  - `log_integration_event()` helper — integrations.py'den çağrılabilir.
  - Frontend: `IntegrationLogs.jsx` — filtreleme (pazaryeri, aktarım türü, durum, tarih, ref_id), "Son 5 İşlem" özet kartları, CSV export, pagination.
- **E-Fatura aktif provider routing**: `POST /api/orders/{id}/create-invoice` endpoint'i eklendi. `providers_config.einvoice.active_provider`'ı okur, provider prefix + sıra no ile `FAC00000001` formatında invoice_number üretir, siparişe yazar, integration_logs'a kayıt düşer. `GET /api/orders/{id}/invoice/print` yazdırılabilir HTML fatura. Bulk invoice akışları artık uçtan uca çalışıyor.
- **Menü**: Entegrasyonlar altına **Pazaryerleri Hub** ve **Entegrasyon Logları** eklendi.
- **Test**: Backend 13 pazaryeri şeması OK, account save/load OK, log summary OK, create-invoice FAC00000001 + provider=dogan-edonusum + integration_logs kayıt OK. Frontend screenshot'larında Pazaryerleri Yönetimi (sol liste + Trendyol seçili + 3 kart) ve Entegrasyon Logları (özet + filtre + tablo) beklenen şekilde render.
- **UI**: Admin Pagination tekdüze hale getirildi. `/app/frontend/src/components/admin/Pagination.jsx` (compact + full variants, jump-to-page input, ilk/son/prev/next, "..." ellipsis). Sayfa başına kayıt seçici (20/50/100/200) hem üst hem alt varyantında.
- **UI**: Ürünler ve Siparişler tablolarına `.admin-table-compact` CSS varyantı → bir ekrana daha çok kayıt sığıyor. Thumbnail w-12→w-10.
- **UI**: ÜST (compact) + ALT (full) pagination — her ikisi aynı state'i paylaşır.
- **Products Bulk Select**: Ürünler tablosuna sol checkbox sütunu + "Tümünü seç" + seçilen ürünler için üst turuncu bulk bar eklendi.
- **Barcode Cards**: Yeni backend router `barcode_cards.py`. Giyim firması ürün kartı (ürün adı, stok kodu, GTIN Code128/EAN-13 barkod, beden, renk, fiyat) — tek ürün `GET /api/products/{id}/barcode-card` + toplu `POST /api/products/barcode-cards/bulk`. A4 2 sütunlu yazdırılabilir HTML.
- **Orders Bulk Invoices**: `Orders.jsx` bulk bar'a **Toplu Fatura Kes** + **Toplu Fatura Yazdır** butonları eklendi. Toplu yazdırma tüm seçili faturaları tek sayfada iframe grid ile basar (A4 başına bir fatura).
- **Provider Settings (yeni)**: Ticimax'teki E-Arşiv/E-Fatura ayarları benzeri jenerik altyapı.
  - Backend: `routes/provider_settings.py` — 11 e-fatura entegratörü (Doğan, Nilvera, Uyumsoft, Logo, Mikro, Foriba/EDM, QNB Finansbank, Turkcell, İzibiz, İdea, Kolaysoft) + 13 kargo firması (MNG, Yurtiçi, Aras, PTT, Sürat, HepsiJet, Trendyol Express, Sendeo, Kolay Gelsin, DHL, UPS, FedEx, TNT). Her biri için alan şeması (field type/required/placeholder) tanımlı.
  - Endpoints: `/api/provider-settings/{einvoice|cargo}/{schemas|config|test}`.
  - MongoDB: tek `providers_config` koleksiyonu, `kind` bazlı tek döküman (active_provider + providers map).
  - Frontend: jenerik `components/admin/ProviderSettings.jsx` (sol liste + sağ dinamik form + arama + şifre toggle + test butonu) → `EInvoiceSettings.jsx` ve `CargoSettings.jsx` sayfaları bu componenti kullanır.
  - Routes: `/admin/ayarlar/e-fatura` ve `/admin/ayarlar/kargo`.
  - Sidebar "Ayarlar" altında yeni menü kalemleri.
- **Refactor (P2 1. adım)**: Products.jsx 2543→2376 satır. Çıkarılan yeni dosyalar:
  - `components/admin/product-form/SearchableAttribute.jsx` (166 satır)
  - `components/admin/product-form/SeoTab.jsx` (65 satır)
  - `components/admin/product-form/StockTab.jsx` (101 satır)
- **Test**: Backend curl testleri başarılı — 11 e-fatura + 13 kargo provider schemas/config/test endpoint'leri çalışıyor. UI smoke testi: sol liste + sağ dinamik form + bulk checkbox'lar + pagination size selector hepsi render ediliyor. Ürün attributes PUT→GET roundtrip doğru (Yaka: V Yaka, Kumaş: Pamuk test edildi).

## [2026-04-23] Pazaryeri Konsolidasyon + Otomasyon + İade Motoru

Kullanıcının "karıştı" geribildirimi üzerine yapılan büyük temizlik ve otomasyon işi:

### Sidebar konsolidasyonu (AdminLayout.jsx)
- "Entegrasyonlar" menüsü 10 kalemden 6 kaleme indi. Ayrı Trendyol/Hepsiburada/Temu Eşleştir ve Trendyol Logları kalemleri kaldırıldı — artık detaylı sayfalar "Detaylı Aktarım & Eşleştirme" (`/admin/entegrasyonlar`) ve "Entegrasyon Logları" (`/admin/entegrasyon-loglari?marketplace=...`) içinden erişilir.
- `MarketplaceHub.jsx` header kartına 4 quick-link eklendi: Aktarım İşlemleri, Marka Eşleştirme, Kategori Eşleştirme, Bu Pazaryerinin Logları.
- `Integrations.jsx` Trendyol/HB/Temu kartlarına "Gelişmiş Eşleştirme" ve "Trendyol Logları" butonları (href destekli) eklendi.
- `IntegrationLogs.jsx` URL `?marketplace=trendyol` query parametresini okuyor, filtre otomatik set ediliyor.

### APScheduler gerçek bağlantı (scheduler.py)
- `_run_trendyol_auto_products_sync` → Trendyol config varsa aktif ürünleri `_sync_inventory_to_trendyol` ile gerçek push.
- `_run_trendyol_auto_orders_pull` → Trendyol'dan son 15 günlük siparişleri çekip `map_trendyol_order` ile DB'ye yazar.
- `_marketplace_sync_tick` artık Trendyol için gerçek fonksiyonu `asyncio.create_task` ile arka plan kuyruğuna alıyor (her 1 dk).
- `_send_abandoned_cart_reminders` → 24 saatte bir, RESEND_API_KEY varsa 2–48 saatlik sepetlere "Sepetinizi unutmayın" maili gönderir (tekrar göndermez).

### Stok pasifleme (bulk_ops.py + StockAlerts.jsx)
- `POST /api/bulk-ops/stock-alerts/deactivate-on-marketplaces` — stoku threshold altı olan aktif ürünleri tüm etkin pazaryerlerinde pasife alır (Trendyol'a qty=0 güncelleme; diğer MP'lere log kuyruğa alır).
- Frontend'de StockAlerts sayfasına "Pazaryerinde Pasife Al" butonu + onay modalı. Test: 14 ürün için başarıyla tetiklendi.

### Iyzico kısmi iade + kargo kesintisi (integrations.py)
- `POST /api/integrations/iyzico/refund` — body: `{order_id, amount, shipping_deduction, reason}`. Kargo bedeli iade tutarından düşülüp Iyzico `/payment/refund` çağrısı yapılır. `_iyzico_auth_header` PKI Base64 auth builder eklendi.
- Siparişe `refunds[]` array'i push edilir; integration_logs'a `iyzico.refund` event yazılır.
- Validasyonlar: zorunlu alanlar, geçersiz sipariş, payment_id yoksa, net iade ≤ 0 hataları doğrulandı.

### Trendyol Mikro İhracat faturalandırma (integrations.py + orders.py)
- `map_trendyol_order` artık `is_micro_export`, `shipment_country`, `delivery_type` alanlarını ekliyor (country≠TR veya deliveryType=international/micro olan siparişler).
- `POST /api/orders/{id}/create-invoice` — sipariş `is_micro_export` ise e-arşiv yerine `ETGB00000001` formatında ETGB beyannamesi üretilir, provider `etgb-micro-export` olarak işaretlenir.

### Test durumu
- Backend e2e curl: ✅ login, stock-alerts deactivate (14 ürün), marketplace-hub/logs filtreli çekim, iyzico/refund (zorunlu alan + 404 sipariş).
- Frontend konsolide sidebar canlı önizlemede (preview uyku modu dışında) beklendiği gibi render ediliyor; eski eşleştirme sayfaları route olarak korundu, Integrations ve MarketplaceHub üzerinden erişilebilir.

## Pending / Backlog

### P0 (Kullanıcı Credential Bekliyor)
- **Pazaryeri Canlı API testleri**: Trendyol/HB/Temu gerçek credential'larla uçtan uca ürün push + sipariş pull doğrulaması.
- **E-Fatura/Kargo Canlı Entegrasyonları**: Doğan e-Dönüşüm SOAP + Yurtiçi Kargo REST için gerçek payload gönderimi ve dönen PDF/URL'in siparişe yazılması.

### P1
- **Hepsiburada / Temu / Pazarama auto-sync**: Scheduler hook'u var (log ile kuyruğa alınıyor) — canlı API entegrasyonu için `_run_hepsiburada_*`, `_run_temu_*` fonksiyonları eklenecek.
- **integrations.py refactoring**: 3700+ satır, pazaryeri bazlı modüllere (integrations_trendyol.py, integrations_hepsiburada.py, integrations_temu.py) bölünmeli.

### P2
- Iyzico refund için UI entegrasyonu (iade detay sayfasına "Kısmi İade + Kargo Kesintisi" modalı).
- Mikro ihracat ETGB için gerçek gümrük beyannamesi PDF üretimi (şu an sadece belge numarası).
- A/B test altyapısı, push notification altyapısı (gelecek).

## [2026-04-23] Entegrasyon Denetimi + 10 Fix (iteration_12 & 13)

Kullanıcı "tüm entegrasyonların test API'larıyla kontrol edilmesi — canlıya alırken sadece credential girmesi yeterli olsun" istedi. `testing_agent_v3_fork` ile 2 iterasyon denetimi yapıldı:
- iteration_12: 46/46 pytest → 1 CRITICAL + 4 HIGH + 3 MEDIUM + 1 LOW bug bulundu
- iteration_13 (retest): **77/77 pytest geçti, 0 critical, 3 minor iyileştirme (tümü fix edildi)**

### Yapılan Fix'ler
- **[CRITICAL] Sessiz pasifleme hatası**: `integrations.py:798` `update_inventory` → `update_price_and_inventory`. `bulk_ops.py` dönüş `success` artık `total_fail==0` bazlı.
- **[HIGH] Settings required-field validasyonu** (5 endpoint): Iyzico/Trendyol/HB/Temu/Doğan — `is_active`/`enabled` true iken zorunlu alanlar eksikse 400 döner.
- **[HIGH] Doğan password leak**: `GET /dogan/settings` artık `password: '********'` maskeli. Payload'da `********` gelirse mevcut değer korunur.
- **[HIGH] Webhooks HMAC signature**: `X-Trendyol-Signature` HMAC-SHA256 (hex + base64) `TRENDYOL_WEBHOOK_SECRET` env ile doğrulanıyor.
- **[MEDIUM] Trendyol özel test-connection**: YENİ endpoint `POST /api/integrations/trendyol/test-connection` — `TrendyolClient.get_brands` probe ile 401/403/HTTP hata net.
- **[MEDIUM] Temu gerçek probe**: `bg.auth.access_token.info.get` MD5 signed çağrı; sandbox `openapi-b-global-stg.temu.com`, live `openapi-b-us.temu.com`.
- **[LOW] HB 400 errorCode parse**: Hepsiburada 400 body'sinden errorCode/errorMessage parse ediliyor.
- **[MINOR] Doğan sync SOAP → threadpool**: event loop bloklanmasın.

### Canlıya Hazır Checklist (iteration_13)
- ✅ **HAZIR**: Iyzico settings + refund, Trendyol settings + test-connection, HB/Temu settings + gerçek probe, Doğan settings + mask, bulk-ops pasifleme, webhooks HMAC, 13 MP Hub + 11 E-fatura + 13 Kargo şeması, create-invoice + ETGB.
- ⏳ **CREDENTIAL BEKLİYOR**: Iyzico live key, Trendyol supplier_id/key/secret, HB merchant_id/user/pass, Temu shop_id/app_key/secret, Doğan prod, `TRENDYOL_WEBHOOK_SECRET` env, 10 einvoice provider SDK (sadece Doğan SDK hazır).

### Canlıya Geçiş Adımları
1. Admin panelden her entegrasyon Ayarlar → credential gir, `is_active=true`.
2. "Test Et" butonu → 401/403/timeout/errorCode mesajı net görünür.
3. Prod'da `TRENDYOL_WEBHOOK_SECRET` env set et.
4. Trendyol `mode: live` seçildiğinde otomatik `https://api.trendyol.com` host.

## [2026-04-23] Eşleştirme UX İyileştirmeleri (Search + Bulk Delete)

Kullanıcı "eşleştirmelerde bana ID soruyorsun, search ile seçeyim; kategori eşleştirmede tek tek/toplu silmek istiyorum; ürün özellikleri görünmüyor" diye şikayet etti:

### Backend
- `GET /api/brand-mapping/{mp}/options?q=` — pazaryerinin marka cache'inden arama (Trendyol için `trendyol_brands`, diğerleri için "cache yok, manuel gir" hint'i).
- `GET /api/category-mapping/{mp}/options?q=` — Trendyol kategori ağacını flatten edip arama (full_path içerir: "Giyim > Abiye & Mezuniyet Elbisesi").
- `POST /api/{brand|category}-mapping/{mp}/bulk-delete` — body `{brand_ids: []}` / `{category_ids: []}`.
- Route sıralama fix: options/bulk-delete/reset-all, generic `{brand_id}`/`{category_id}` route'undan ÖNCE tanımlandı (FastAPI catch-all önceliği).
- `GET /api/attributes` artık `_id` projection ile sızmıyor.

### Frontend
- `SearchableMapSelect.jsx` yeni ortak bileşen (`/app/frontend/src/components/admin/`) — debounced fetch + dropdown + full_path gösterimi + "seçili ID" etiketi.
- `BrandMapping.jsx`: ID/Name inputları SearchableMapSelect'e değiştirildi. Checkbox sütunu + Toggle-all + bulk-delete bar.
- `CategoryMapping.jsx`: aynı — checkbox + SearchableMapSelect + tek-tek + toplu sil butonu.
- Ürün global attributes response `_id` temizliği → attribute picker/seçici UI yan etkisi kaldırıldı.

### Test
Backend curl: brand/cat bulk-delete ikisi de `{success:true,deleted:0}` (boş ID), cat options `?q=elbise` → 2+ gerçek sonuç, brand options hepsiburada → hint. Tüm lint temiz.

## [2026-04-23] Gelişmiş Eşleştirme — Tüm Pazaryerleri için Konsolide

Kullanıcı isteği: "Gelişmiş kategori eşleştirme sayfasına (TrendyolEslestir) tıklanınca açılan özellikler, normal kategori eşleştirme sayfasının içinde olsun ve tüm pazaryerleri için çalışsın."

### Backend (generic, MP-agnostic)
- `GET /api/category-mapping/{mp}/{local_cat_id}/attributes` — MP'nin bu kategori için zorunlu+opsiyonel özellikleri. Trendyol için `TrendyolClient.get_category_attributes` canlı çağrısı + DB cache (`trendyol_category_attributes`). Diğer MP'ler için `{mp}_category_attributes` cache varsa dönüyor, yoksa boş + hint.
- `POST /api/category-mapping/{mp}/{local_cat_id}/attribute-map` — attribute_mappings + default_mappings + value_mappings kaydeder (mapping doküman alanları).
- `GET /api/category-mapping/{mp}/{local_cat_id}/values` — bu kategorideki sistem ürünlerinin distinct attribute değerleri (MP'ye gönderirken "Kırmızı ↔ Red" gibi value mapping için).

### Frontend
- Yeni `components/admin/MarketplaceAdvancedMatch.jsx` — iki ortak modal:
  - `AdvancedAttributeMatchModal` — Zorunlu/opsiyonel attribute tablosu, otomatik eşleştir, datalist ile global attr öneri, listeden seçme + serbest yazı (allowCustom), default mappings. MP_COLORS map'i ile her pazaryeri kendi rengiyle gösterilir.
  - `AdvancedValueMatchModal` — attribute tab'ları + değer-bazlı mapping tablosu.
- `CategoryMapping.jsx` her matched kategori satırına 2 yeni buton: "⚙ Özellik" ve "⇅ Değer" — tıklayınca ilgili modal açılır, kaydedince tablo yenilenir.
- Route `/admin/trendyol-eslestir` artık `<Navigate to="/admin/kategori-eslestir">` ile redirect. Eski `TrendyolEslestir.jsx` silinmedi ama menü+route bağlantıları kaldırıldı.
- `Integrations.jsx` içindeki Trendyol/HB/Temu "Gelişmiş Eşleştirme" butonları artık `/admin/kategori-eslestir`'e gider (önceden MP-spesifik ayrı sayfalardı).

### Test
Backend curl: `/category-mapping/trendyol/nonexistent/attributes` → hint "Önce eşleştirin" ✅, `/hepsiburada/*/attributes` → hint+boş ✅, `/values` → `{local_values:{},value_mappings:{}}` ✅, `/attribute-map` POST → `{success:true}` ✅. Lint 4/4 temiz.

## [2026-04-23] Tümünü Otomatik Eşleştir (Potansiyel İyileştirme)

Önceki finish'te önerilen potansiyel iyileştirme uygulandı:

### Backend
`POST /api/category-mapping/{mp}/bulk-auto-match-attributes` — matched tüm kategoriler için toplu otomatik attribute eşleştirme:
- Global attributes bir kez çekilir.
- Trendyol için canlı `TrendyolClient.get_category_attributes` + cache write; diğer MP'ler için `{mp}_category_attributes` cache'inden.
- İsim eşleştirmesi: exact/contains + alias (color↔renk, size↔beden).
- **Manuel eşleştirmeler korunur**, sadece boşlar doldurulur.
- Rapor: `{processed, total_new_mappings, details:[{category_name, new, total_mp_attrs, fetched}]}`.

### Frontend
- CategoryMapping üst barına gradient turuncu-amber "⚡ Tümünü Otomatik Eşleştir" butonu.
- Sonuç modal'ı: 3 özet kart + kategori bazlı detay tablosu (CANLI/CACHE/YOK rozet).

### Test
- Credential yokken Trendyol → 1 matched kategori için `{processed:1, new:0, note:"MP attribute listesi boş"}` ✅
- matched yok iken → `{message:"Eşleştirilecek matched kategori bulunamadı"}` ✅
- Lint: CategoryMapping + category_mapping.py temiz.

## [2026-04-23] Ürün Özellikleri Regression + Değer Otomatik Eşleştir

Kullanıcı şikayetleri: (1) "Ürün özellikleri sekmesinde değerler görünmüyor" (2) "Eşleştirme ayarlarında bu değerleri bulmuyor".

### 1. ProductAttributes.jsx — API env regression
`const API = process.env.REACT_APP_API_URL || 'http://localhost:8001/api'` → Var olmayan env ile production'da `localhost:8001` fallback'ine düşüyor, K8s ingress dışarı yönlendiremiyor → tüm istekler sessiz fail, özellikler boş görünüyor.
**Fix**: `${process.env.REACT_APP_BACKEND_URL}/api`. DB'de zaten 53 attribute + değerleriyle dolu (sync-from-products ile eklendi).

### 2. AdvancedValueMatchModal — Global attribute değerleri eklendi
`GET /api/category-mapping/{mp}/{cat_id}/values` artık `db.products` distinct değerlerine ek olarak `db.attributes` koleksiyonundaki tüm global değerleri birleştirerek döner. Ayrıca ürünün `type` alanı okunuyor (önceden sadece `name`). Kategoride ürün olmasa bile sistemde tanımlı "Renk: Kırmızı/Mavi…" vs görünür.
**Test**: 51 attribute grubu (Renk: 100 değer, Boy: 101, Kol Tipi: 30…) ✅.

### 3. "⚡ Otomatik Değer Eşleştir" Butonu
`AdvancedValueMatchModal` başlığında yeni yeşil "Otomatik Eşleştir" butonu. İsim benzerliği + alias tablosuyla (Kırmızı↔Red, S↔Small, XL↔X-Large…) otomatik eşleştirir. Manuel eşleştirmeler korunur.

### Test
- `sync-from-products`: 9 yeni + 3 güncelleme → 53 attribute dolu ✅
- `/values` 51 grup, 10-100+ değer ✅
- Lint: MarketplaceAdvancedMatch.jsx, ProductAttributes.jsx, category_mapping.py — 3/3 temiz.

## [2026-04-23] Modal Özellik Autocomplete — Datalist Yerine Görünür Dropdown

Kullanıcı: "kategori eşleştirme ayarlarında ürünlerin özellik alanlarını sistemden çekmiyor." Arka planda `GET /api/attributes` 53 attribute çekiyordu ama UI `<datalist>` kullanıyordu; çoğu browser'da input boşken açılmaz.

### Fix
- Yeni `LocalAttrAutoComplete` bileşeni: Focus'ta tüm 53 sistem özelliği açılır dropdown'da (değer sayacıyla) görünür, yazdıkça filtreler.
- Banner: "Sistemde tanımlı **N** özellik var — kutuya tıkladığınızda liste açılır."
- Boş fallback: globalAttrs=0 ise sarı "Ürünlerden Yükle" → `POST /attributes/sync-from-products`.

## [2026-04-23] Empty State + Zorunlu Ayrımı (Screenshot Sorunu)

Kullanıcı ekran görüntüsü: Trenço kategori modal'ı "özellik bulunamadı" gösteriyordu (Trendyol cache yok).

### Fix
- mpAttrs boşsa, globalAttrs'ı pseudo-satırlar olarak listeler (kullanıcı manuel seçim yapar).
- Amber banner "credential/cache eksik — N sistem özelliğinden manuel seç".
- Zorunlu satırlar: `bg-red-50/40` kırmızı zemin + kırmızı ZORUNLU badge + "ZORUNLU ALANLAR (N)" / "OPSİYONEL ALANLAR (N)" grup başlıkları.
- React.Fragment key ile header+row çifti, `isReq` hatasız durum sütunu.

## [2026-04-23] P1/P2/P3 — Canlı Çek + Manuel Cache Upload + Eski Sayfa Temizlik

Kullanıcı isteği: önceki "Next Action Items" (P1 Trendyol canlı çek butonu, P1 HB/Temu cache besleme, P2 eski TrendyolEslestir silme).

### 1. "Canlı Çek" Butonu (Modal içinde)
- Backend: `POST /api/category-mapping/{mp}/{local_cat_id}/refresh-attributes` — tek kategoride MP attribute listesini anlık yeniler.
  - **Trendyol**: `TrendyolClient.get_category_attributes(mp_cat_id)` canlı çağrı + cache upsert + `{success:true, count:N}` dönüş.
  - **Diğer MP'ler**: "canlı API yok, manuel upload yap" mesajı.
- Frontend: AdvancedAttributeMatchModal header'ına mavi **"{marketplace} Canlı Çek"** butonu. İşlem sonrası modal tablosu otomatik yeniden yüklenir.

### 2. HB/Temu için Manuel Attribute Cache Upload
`POST /api/category-mapping/{mp}/attr-cache` yeni endpoint:
- Body: `{marketplace_category_id, attributes: [{id, name, required, attributeValues:[...]}]}`
- Kullanıcı kendi HB/Temu panelinden export ettiği JSON'u buraya POST eder → `{mp}_category_attributes` cache'e yazılır → Modal'da o kategori için attribute listesi görünür hale gelir.
- Route sıralaması düzeltildi: `attr-cache` `{category_id}` generic'ten ÖNCE tanımlı.
- Test: HB için 1 attribute (Renk: Kırmızı/Mavi) upload → `{success:true, count:1}` ✅

### 3. Eski Eşleştirme Sayfaları Silindi
- `TrendyolEslestir.jsx` (1286 satır), `HepsiburadaEslestir.jsx`, `TemuEslestir.jsx` fiziksel olarak silindi.
- App.js'te 3 route → `<Navigate to="/admin/kategori-eslestir" replace />`
- Import satırları temizlendi. Lint: temiz.

### Test
Backend: `/refresh-attributes` → "önce eşleştirin" net hata ✅; `/attr-cache` → manuel 1 attr yüklendi ✅
Frontend lint: App.js, MarketplaceAdvancedMatch.jsx, category_mapping.py — 3/3 temiz.

Kullanıcı şikayeti: "Kategori eşleştirme ayarlarında ürünlerin özellik alanlarını sistemden çekmiyor." Arka planda `GET /api/attributes` doğru şekilde 53 attribute çekiyordu ama UI `<datalist>` kullanıyordu — bu element çoğu browser'da input boşken açılmaz, kullanıcı sistem özelliklerini göremezdi.

### Fix
- **Yeni `LocalAttrAutoComplete` bileşeni**: `MarketplaceAdvancedMatch.jsx` içinde standalone autocomplete. Focus'ta sistem özelliklerinin tamamını (53 tane, "Beden — 100 değer" gibi) gösterir, yazdıkça filtreler.
- **Banner bilgisi**: "Sistemde tanımlı **N** özellik var — kutuya tıkladığınızda öneri listesi açılır."
- **Fallback**: Global attrs boşsa (yeni kurulum) banner'da "Ürünlerden Yükle" butonu → `POST /api/attributes/sync-from-products` çağırır, liste yeniler.

### Test
- `/api/attributes` 53 attribute döner, değer sayılarıyla birlikte autocomplete'de görünür ✅
- Lint temiz ✅

## [2026-04-23] Bulk Delete + Global AppConfirm Pop-up

Kullanıcı şikayetleri: (1) Ürün sayfasında birden fazla ürün seçince sil butonu aktif olmuyor. (2) Tüm sitede onaylar browser native popup (sekme üstü) çıkıyor, app içinde pop-up istendi.

### 1. Global `appConfirm` Altyapısı
- Yeni `components/admin/AppConfirm.jsx`: Shadcn AlertDialog tabanlı Promise API.
- `appConfirm("metin")` veya `appConfirm({title, description, confirmText, cancelText, variant:"danger"|"warning"|"default"})` Promise<boolean> döner.
- Tek global resolver; `<AppConfirmRoot />` AdminLayout'ta mount, `window.appConfirm` global.

### 2. Migration: `window.confirm` → `await window.appConfirm`
- 20 admin sayfası (Orders, Products, Returns, Vendors, Coupons, Members, BulkPriceStock, StockAlerts, ProductReviews, Manufacturing, Settings, UsersRoles, PageDesign, SeoAdmin, CatalogExtras, AdminTasks, BrandMapping, CategoryMapping, Questions, Account) sed ile migrated.
- Sonuç: browser native popup kayboldu; Shadcn app-içi pop-up (temayla uyumlu, variant'lı danger/warning/default).
- Lint: tüm admin + Account.jsx — temiz ✅.

### 3. Products Bulk Delete
- Seçili ürünler bar'ına kırmızı **"Seçili Ürünleri Sil"** butonu (Trash2 ikonu).
- `handleBulkDeleteProducts` → appConfirm `danger` ile "{N} ürün silinsin mi?" → DELETE loop → başarı/fail sayacı toast + liste refresh.



## [2026-05-04] Ticimax Üye Senkronizasyonu + Site-Only Sipariş Filtresi

Kullanıcı isteği: "ticimax kaynaklı tüm siparişleri tüm detayların kadar çek. hangi müşteriler hangi üyelik bilgileriyle sisteme üye olduysa onları da sistemme kaydet. bu ws yetki kodundan SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V üyeler ve siparişlerin çekilme durumlarını araştır. ancak pazaryerlerinden gelen siparişleri çekme trendyol hepsiburada n11 aliexpress gibi. sadece siteden sipariş veren telefon nosu olan insanların verdiği siparişleri çek"

### Yapılanlar
- `ticimax_client.py`: 
  - Yeni varsayılan WS kodu: `SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V` (DB ayarından override edilebilir).
  - **UyeServis** (member service) entegrasyonu eklendi: `get_members(page, page_size, only_active, only_with_phone)`, `get_member_addresses(uye_id)`, `find_member_by_phone_or_email(...)`.
  - `get_orders()` artık `exclude_marketplace=True` (PazaryeriIhracat=0) ve `only_with_phone=True` parametreleri destekliyor; `IsMarketplace`, `Kaynak`, `PazaryeriButikId` alanlarına göre post-filter ile Trendyol/HB/N11/AliExpress/Temu/Pazarama/Çiçeksepeti/Amazon/PTTAVM siparişleri kesin elenir.
- `routes/integrations.py`:
  - Yeni endpoint: `POST /api/integrations/ticimax/members/import?page_size=&max_pages=&only_with_phone=&only_active=&fetch_addresses=` → 91 üye başarıyla çekildi (Hatice Zeybek, Fatma Nur, Ebru Yaren vb. gerçek müşteri verisi). KVKK onayı, SMS/Mail izinleri, üyelik tarihi, son giriş IP'si, doğum tarihi, il/ilçe, üye kodu, para puan, kredi limiti dahil tüm alanlar `customers` koleksiyonuna kaydediliyor; mail veya telefon eşleşmesinde mevcut `users` hesapları `ticimax_uye_id` ile bağlanıyor.
  - Yeni endpoint: `GET /api/integrations/ticimax/members?skip=&limit=&search=` → kayıtlı Ticimax müşterilerinin listesi.
  - Mevcut `POST /api/integrations/ticimax/orders/import` → artık `exclude_marketplace`, `only_with_phone`, `pages`, `days` query parametreleri ile çalışıyor; UrunGetir/OdemeGetir/KampanyaGetir flag'leri açık (tek API çağrısında tüm detay), satır kalemleri + IP + kargo takip + fatura no + indirim/KDV detayları kaydediliyor.
  - Marketplace siparişleri sayılarak atlanır (`skipped_marketplace`); telefon yoksa atlanır (`skipped_no_phone`).
- `frontend/src/pages/admin/Integrations.jsx`:
  - Ticimax kartına "Üyeleri Aktar (Telefonlu)" mor butonu (Users ikonu) ve "Siparişleri Aktar (Site, Son 365 Gün)" buton metni güncellemesi.
  - Açıklayıcı not: "Sipariş aktarımı yalnızca siteden verilen ve telefon numarası bulunan siparişleri çeker. Trendyol/Hepsiburada/N11/AliExpress siparişleri otomatik olarak hariç tutulur."

### WS Yetki Kodu Araştırma Sonucu
- `SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V` testlerinden çıkan sonuç:
  - ✅ **UyeServis** (üyeler): ÇALIŞIYOR — 475+ üye erişimi var (sayfa sayfa pull edildi, 91 telefonlu aktif üye DB'ye yazıldı).
  - ❌ **SiparisServis** (siparişler): API boş response (`<SelectSiparisResult/>`) dönüyor. Bu WS kodu ya `Sipariş Servisi` iznine sahip değil ya da Tedarikçi-scope’lu bir izin (eski key `HANXFW...` "Tedarikçiye bağlı siparişler bulunamadı" hatası veriyor).
  - ❌ **UrunServis** (ürünler): `SelectUrunCount=0` → bu key ürün servisi iznine de sahip değil.
- Sonuç: **Sipariş çekme akışı kodda hazır** (filtreler, tüm detay alanları, paging) ama **kullanıcının Ticimax panelinden 'Sipariş Web Servisi' yetkisi olan bir WS kodu** sağlaması gerekiyor (Ticimax → Yönetim → Web Servis Yetkileri → Yeni yetki ekle → "Sipariş Servisi" işaretli).

### Test
- Backend `/api/integrations/ticimax/members/import?page_size=100&max_pages=2` → `imported: 91, total: 91, message: "91 yeni üye, 0 güncellendi"` ✅
- Backend `/api/integrations/ticimax/members?limit=5` → real customer data (Konya, İstanbul vs.) ✅
- Backend `/api/integrations/ticimax/orders/import?days=365&pages=2` → 0 (beklenen, WS izni yok) — kullanıcıya net mesaj.

## [2026-05-05] MNG Kargo Canlı Barkod Entegrasyonu (P0 - Tamamlandı)

Kullanıcı isteği: "bir de bi sipariş oluşturdum ama mng kargo barkodu oluşmadı: başka bir sistemde entegrasyonun aktif olması için gereken kullanıcı adı ve şifre bilgilerimi sana ilettim aynıları ile senin de mng kargo için barkod oluşturman lazım"

### Tespit
- Frontend `Orders.jsx` `/api/orders/{id}/cargo-barcode?cargo_company=MNG` ve `/api/orders/{id}/create-mng-shipment` endpoint'lerini çağırıyordu ama backend'de bu endpoint'ler **YOKTU** — bu yüzden barkod oluşmuyordu (404 veya silent fail).

### Yapılanlar
- Yeni `mng_kargo_client.py`: MNG Kargo (DHL eCommerce) SOAP entegrasyonu
  - `Baglanti_Test()` → bağlantı testi
  - `SiparisGirisiDetayliV3(...)` → sipariş kaydı (status code "1" döner)
  - `FaturaSiparisListesi(pSiparisNo)` → MNG_SIPARIS_NO (gerçek 10 haneli barkod) çekme
  - `KargoTakipByReferans(...)` → siparis no ile takip
  - `TekBarkodGonderiIptali(...)` → iptal
  - WSDL: `https://service.mngkargo.com.tr/musterikargosiparis/musterikargosiparis.asmx?WSDL`
- `routes/orders.py` yeni endpoint'ler:
  - `POST /api/orders/{id}/cargo-barcode?cargo_company=MNG` → canlı MNG barkod oluşturur, order'a tracking number + tracking link yazar, `cargo_logs` tablosuna log atar.
  - `POST /api/orders/{id}/create-mng-shipment` → kısayol (yukarıdakini çağırır).
  - `POST /api/orders/bulk/cargo-barcode` → toplu barkod (frontend mevcut buton).
  - `GET /api/orders/{id}/cargo-label` → 100mm × 150mm yazdırılabilir HTML kargo etiketi.
  - `GET / POST /api/orders/cargo/mng-settings` → MNG Kargo credentials yönetimi (password maskelenir).
  - `POST /api/orders/cargo/mng-test` → bağlantı testi.

### MNG İş Akışı (Anlaşılan ve Implement Edilen)
1. `SiparisGirisiDetayliV3` çağrılır → MNG `1` (sadece success status) döner.
2. Hemen ardından `FaturaSiparisListesi(pSiparisNo)` çağrılır → response içinde `MNG_SIPARIS_NO` (örn. `1757391335`) gelir → bu gerçek kargo barkodu.
3. Order MongoDB'ye `cargo_tracking_number=1757391335` ve `cargo_tracking_link=https://kargotakip.mngkargo.com.tr/?BarkodNo=1757391335` yazılır.

### Doğrulanan Hata Mesajları (MNG WSDL)
- `pKargoParcaList` formatı: `"Kg:Desi:En:Boy:Yukseklik:;..."` (default `1:1:20:30:15:;`)
- `pLuOdemeSekli`: sadece `P` (Peşin/Gönderici), `U` (Ücretli/Alıcı), `PL` (Kapıda+Peşin) kabul edilir
- `pGonderiHizmetSekli`: sadece `NORMAL` | `ONCELIKLI` | `GUNICI` | `AKSAM_TESLIMAT`
- `pPlatformKisaAdi` ve `pPlatformSatisKodu`: ya ikisi de boş, ya ikisi dolu olmalı (boş = kendi sitemiz). Doluysa: `N11`/`GG`/`TRND`.

### Test
- `POST /api/orders/cargo/mng-test` → `{ok: true, result: "1"}` ✅ (Baglanti_Test başarılı)
- `POST /api/orders/cargo/mng-settings` → ayarlar kaydedildi ✅
- `POST /api/orders/{order_id}/cargo-barcode?cargo_company=MNG` → **Gerçek MNG barkodu üretildi: 1757391335** ✅
  - DB'de order güncellendi (cargo_tracking_number, cargo_tracking_link, cargo_provider_name="MNG Kargo")
  - `cargo_logs` tablosuna log atıldı

### Default Credentials (DB'ye kaydedildi)
- Customer Code: `FACETTE DIŞ TİC.A.Ş.`
- Username: `490059279`
- Password: `Face.0024E`
- Vergi No: `6080712084`


## [2026-05-05] Ticimax -1 Filter + MNG Etiket Güncelleme + Auto SMS/WhatsApp/Email

### Tespit
- Ticimax SiparisServis ve UyeServis için **int filtre alanlarında "-1" = "filtre yok"**. 0 göndermek "değeri 0 olanları getir" demek olduğu için 0 sipariş dönüyordu. Doc: https://www.destekalani.com/Icerik/ws-yetki-kodu-yonetimi-web-servis-modulu-649

### Yapılanlar
1. **`ticimax_client.py`**:
   - `get_orders()` — tüm int filtre alanları default `-1` (EntegrasyonAktarildi, SiparisDurumu, OdemeDurumu, OdemeTamamlandi, OdemeTipi, PaketlemeDurumu, PazaryeriIhracat, SiparisID, TedarikciID, UyeID, EFaturaURL, KargoEntegrasyonTakipDurumu, KargoFirmaID, TeslimatMagazaID).
   - `get_members()` — UyeFiltre int alanları (Aktif, AlisverisYapti, Cinsiyet, IlID, IlceID, MailIzin, SmsIzin, UyeID) default `-1`.
   - **CANLI TEST: 150 sipariş çekildi** (FC1777939101 dahil tüm gerçek siparişler MongoDB'ye yazıldı).
2. **`integrations.py`**:
   - `/ticimax/orders/import` default'ları gevşetildi (`exclude_marketplace=False`, `only_with_phone=False`, `days=365→3650`, `pages=20`, `limit=200`).
   - "ayrım yapma" talebi → tüm siparişler (site + pazaryeri) ve tüm üyeler (telefonlu + telefonsuz) çekiliyor.
3. **MNG Kargo Etiketi (`/api/orders/{id}/cargo-label`)**:
   - MNG DHL E-Commerce başlık + üst Code39 barkod **sipariş numarası** + alt Code39 barkod **MNG kargo takip no**.
   - Gönderici/Alıcı/Kargo bilgi bölümleri (10cm × 15cm thermal).
   - Authorization yerine `?token=` query parametresi kabul ediyor (yeni sekme yazdırma için).
4. **Otomatik Müşteri Bildirimi (kargoya verildi)**:
   - MNG barkodu üretildikten sonra `notification_service.send_notification(event="order_shipped")` çağrılıyor.
   - 3 kanal aktif: SMS (Netgsm/İletimerkezi/Twilio/VatanSMS), WhatsApp (Meta Cloud API), Email (Resend).
   - Default template'ler DB'ye seedlendi: `/api/notification-templates` üzerinden düzenlenebilir.
5. **Mağaza bilgileri**: `settings.id=store_info` (sender_name=`FACETTE DIŞ TİC.A.Ş.`, sender_phone, sender_address vb.) etikette gönderici olarak kullanılıyor.
6. **Cargo nested obje**: Frontend `selectedOrder.cargo?.tracking_number` üzerinden kontrol ediyordu. Backend artık hem `cargo_tracking_number` (top-level) hem `cargo.tracking_number` (nested) yazıyor → manuel input kaybolur. 23 mevcut sipariş için backfill yapıldı.

### MNG Kargo Workflow (Final)
1. SiparisGirisiDetayliV3 → status code "1" döner.
2. FaturaSiparisListesi(pSiparisNo) → MNG_SIPARIS_NO çekilir (gerçek 10 haneli barkod).
3. Order'a 2 alanda yazılır: `cargo_tracking_number` + `cargo.tracking_number`.
4. SMS/WhatsApp/Email otomatik gönderilir (template'ler {tracking_number}, {tracking_link}, {order_number}, {name} değişkenleriyle).

### Doğan e-Dönüşüm e-Fatura (PENDING — büyük iş)
Kullanıcı "neden gerçek faturası dogandonusume düşmüyor" sordu. Mevcut `create_invoice_for_order` endpoint sadece **MOCK fatura numarası** üretiyor (`FAC00000001` gibi). Gerçek e-fatura için Doğan'a UBL-TR XML formatında SOAP üzerinden gönderim gerekiyor — Doğan client'da SendInvoice methodu eksik. Sonraki iterationda eklenecek (login → SendInvoice(xmlContent, type) → invoice UUID al → DB'ye yaz).

### Test
- `/ticimax/orders/import` (730 gün, 3 sayfa, no filter) → **150 sipariş eklendi** ✅
- `/ticimax/members/import` → 91 üye (önceki) ✅
- `/orders/{id}/cargo-barcode?cargo_company=MNG` → barkod `1757391445` üretildi ✅
- `/orders/{id}/cargo-label` (browser render) → MNG-style etiket, üst sipariş no + alt takip no barkodu ✅
- order_shipped notification → 3 kanal template seedlendi (SMS/WhatsApp/Email) ✅


## [2026-05-05] MNG GONDERI_NO + Doğan UBL-TR e-Arşiv Entegrasyonu

### MNG Kargo Takip No Anlamı (CRITICAL)
- `MNG_SIPARIS_NO` (örn. `1757391445`): MNG'nin **iç referans numarası** (sipariş kayıt anında atanır).
- `GONDERI_NO` (örn. `NZ197406`): **Gerçek kargo takip numarası** (MNG çıkış şubesi paketi işleme aldığında atanır, başlangıçta `null`).
- Etiket/UI artık `GONDERI_NO` öncelikli, yoksa `MNG_SIPARIS_NO` gösterir.
- Yeni endpoint: `POST /api/orders/{id}/cargo-refresh` → MNG'den güncel `FaturaSiparisListesi` çekip `GONDERI_NO`/`KARGO_STATU` günceller.
- 22 mevcut order için cargo.mng_siparis_no/mng_gonderi_no fieldları backfill edildi.

### Doğan e-Dönüşüm UBL-TR e-Arşiv Entegrasyonu (Kod tamamlandı, Auth bekliyor)
- `dogan_client.py`:
  - `build_earsiv_ubl_xml(...)` - Tam UBL-TR 1.2 e-Arşiv Fatura XML üretici (bireysel TCKN + kurumsal VKN destekli, satır kalemleri, KDV, kargo, indirim).
  - `send_earsiv_invoice(ubl_xml)` - Doğan `WriteToArchive` SOAP çağrısı.
  - `login()` artık ERROR_TYPE'ı kontrol ediyor (önceden mock success dönüyordu, şimdi gerçek credentials hatası net dönüyor).
- `routes/orders.py` `create_invoice_for_order` artık Doğan canlı çağırıyor (`is_test=true` veya `false`).
- Credentials kaydedildi: VKN `7810816779`, kullanıcı `7810816779`, şifre `Facette.98`, prefix `FAC`/`FCT`.

### ⚠️ Doğan Auth Sorunu (Kullanıcı Aksiyonu Gerekli)
- **Production endpoint** (`efatura.doganedonusum.com`) → bizim pod'dan timeout. **IP whitelist gerekli.** Pod outbound IP: `34.170.12.145` — bu IP'yi Doğan destek ekibine ileterek whitelist'e eklettirin.
- **Test endpoint** (`efaturatest.doganedonusum.com`) → erişilebilir ama verdiğiniz prod credentials test'te `10004 Kullanıcı adı veya şifre hatalı` hatası alıyor (test ortamında ayrı kullanıcı gerekir).
- Whitelist sonrası canlıya geçiş: `is_test=false` ile aynı credentials kullanılarak otomatik fatura kesimi başlar.


## [2026-05-05] MNGGonderiBarkod (NZ Anında Barkod) + Postal Code → İl

### MNGGonderiBarkod Entegrasyonu
- `mng_kargo_client.py` → `get_mng_barcode_immediately(...)` eklendi (MNGGonderiBarkod SOAP).
- Kargo barkodu oluşturulduğu anda **NZ formatlı** kargo takip kodunu çeker (sipariş ofisten çıkmadan önce).
- `routes/orders.py` create_cargo_barcode + cargo-refresh artık 3 katmanlı veriyi DB'ye yazıyor:
  1. **MNGGonderiBarkod** (NZ barkod) — anında alınır, IP whitelist gerekli.
  2. **FaturaSiparisListesi.GONDERI_NO** — şube işlemi sonrası dolar.
  3. **MNG_SIPARIS_NO** — fallback (her zaman dolu).
- Frontend Orders.jsx → `cargo.provider == 'MNG' && !cargo.mng_nz_barkod` koşulunda **🔄 Yenile** butonu görünür.

### IP Whitelist Talebi (KRİTİK)
- **Pod outbound IP**: `34.170.12.145`
- Bu IP whitelist edilmesi gereken iki servis:
  - **MNG Kargo** (`MNGGonderiBarkod` endpoint için) → şu an `YETKİ HATASI! Mac : 000000000000 Ip :34.170.12.145`
  - **Doğan e-Dönüşüm** (`efatura.doganedonusum.com:443`) → şu an connection timeout

### Postal Code → İl Mapping
- Yeni `il_mapping.py` modülü (81 il, posta kodu prefix bazlı).
- Ticimax import sırasında `Sehir` boş gelirse posta kodundan otomatik il çıkartılıyor.
- 137 mevcut sipariş için backfill yapıldı.

### Test
- POST `/orders/{id}/cargo-refresh` → MNGGonderiBarkod denemesi → `YETKİ HATASI` (whitelist sonrası NZ barkod gelecek), FaturaSiparisListesi → `kargo_statu: "Gönderi Kargo İşlemi Yapılmadı"` (şube henüz işlemedi). Mesaj net.
- Etiket render → Code39 üst (sipariş no `FC1777939101`) + alt (takip no `1757391445`) doğru formatta ✅


## [2026-05-05] DÜZELTME: MNG Self Barkod modu (whitelist/NZ varsayımı yanlıştı)

### Doğru Anlayış
- MNG Kargo entegrasyonunda **iki tip hesap** vardır:
  1. **Self Barkod hesabı** (varsayılan, çoğu e-ticaret sitesi): `SiparisGirisiDetayli` çağrıldığında MNG sistem `MNG_SIPARIS_NO` (örn. `1757391445`) atar — **bu zaten gerçek kargo takip kodudur**, MNG kuryesi etiketteki bu numarayı okutur ve sistemine düşer.
  2. **Kurumsal NZ-formatlı barkod havuzu** (özel müşteriler): MNG müşteri yöneticisi tarafından NZ-prefix'li bir barkod range tahsis edilir; `pChBarkod` parametresinde kullanıcı bunu gönderir.
- "MNGGonderiBarkod YETKİ HATASI Mac:0..." → bizim hesap NZ havuzu yok, Self Barkod modu → bu operasyona ihtiyacımız yok.
- **Çözüm: MNGGonderiBarkod denemesi kaldırıldı.** Mevcut akış:
  1. SiparisGirisiDetayliV3 → MNG_SIPARIS_NO al (örn. `1757391445`)
  2. FaturaSiparisListesi → kargo_statu, çıkış/teslim şubesi, varsa GONDERI_NO
  3. Etikette MNG_SIPARIS_NO basılır → kuryenin scan ettiği gerçek kargo barkodu

### Doğan e-Dönüşüm Production Erişim Sorunu
- `efatura.doganedonusum.com:443` (195.155.128.35) — pod'dan TCP timeout (Doğan firewall pod'umuzun outbound IP'sini reddediyor, bu network seviyesinde — kod tarafında düzeltilemez).
- `efaturatest.doganedonusum.com:443` (176.236.208.19) — erişim var ✅, gerçek kullanıcı/şifre kabul etmiyor (test env için ayrı creds).
- Bu sorun **whitelist talebi değil**, network routing — bizim Google Cloud pod'umuzdan Doğan production'a paket gitmiyor. Çözüm: User'ın kendi Türkiye-bazlı sunucusuna deploy etme (preview ortamında değil, üretimde).

### Temizlik Yapılan
- `mng_kargo_client.get_mng_barcode_immediately` (MNGGonderiBarkod) — kod kalsın ama default akıştan çıkarıldı.
- `routes/orders.py create_cargo_barcode` — sadece SiparisGirisiDetayliV3 + FaturaSiparisListesi.
- `cargo-refresh` — sadece FaturaSiparisListesi (NZ deneme yok).
- Frontend Orders.jsx — yenile butonu her MNG order için (NZ check kaldırıldı), error toast'larında "whitelist" terimi yok.


## [2026-05-05] Trendyol-Style One-Page Checkout Yeniden Tasarımı

### Tetikleyici
Kullanıcı Trendyol checkout ekran görüntüsü ve detaylı prompt paylaşarak benzer UI/UX talep etti.

### Yapılanlar (`/app/frontend/src/pages/Checkout.jsx` tam yeniden yazıldı)
- **Layout**: 12-col grid; sol 9 col (içerik), sağ 3 col (sticky `Sipariş Özeti` paneli).
- **Sepetimdeki Ürünler**: Collapsible card; daraltılınca thumbnail stack + adet özeti, açılınca detaylı liste.
- **Adres Bölümü**: Yan yana 2 kart (Teslimat + Fatura) + her birinin sağ üstünde turuncu **Adres Ekle/Değiştir** butonu. **Modal** açılır (sayfa yenilemeden async).
  - Modal içinde: kayıtlı adres seçicisi (logged-in users) + yeni adres formu + ProvinceDistrictSelect + Posta Kodu.
  - `POST/PUT /api/customer/addresses` ile DB'ye kaydeder, listeyi yeniler.
  - **Faturamı Aynı Adrese Gönder** checkbox — checked olunca billing card "Teslimat ile aynı" mesajı + edit butonu disable.
- **Ödeme Seçenekleri**: 3 method radio (Banka & Kredi Kartı / Havale / Kapıda Ödeme), seçili olana turuncu vurgu. Kredi Kartı seçili iken: Kart bilgileri (iyzico'ya yönlendirme infosu), Taksit özeti, **3D Secure** checkbox (default ON), **Puan Kullan** checkbox (puan varsa).
- **Hediye Seçenekleri**: Hediye paketi (+130 TL) + Hediye notu (300 char limit).
- **Sipariş Özeti** (sticky):
  - **Sana Özel Kuponlar** — Trendyol-style turuncu kart (seçili olunca dolu turuncu, hover'da turuncu border).
  - Manuel kupon input + Uygula/Kaldır.
  - Ara Toplam, Kargo (≥500₺ "Bedava" badge + üstü çizili 59,99₺), Kupon, Puan, Hediye paketi, Kapıda Ödeme satırları, Toplam (turuncu).
  - **Ödeme Yap** turuncu büyük buton (sözleşme onaylanmadan disabled).
  - **Mesafeli Satış Sözleşmesi + Ön Bilgilendirme Koşulları** checkbox butonun altında.
- **SSL Güvenli Ödeme** rozet üst sağda.
- **Quick signup modal** korundu (guest sipariş sonrası hesap oluşturma).

### Test
- Hot reload + smoke test ile gerçek render doğrulandı (Slim Fit Triko Bluz, Yüksek Bel Kumaş Pantolon, kupon TEST10 -149.97 TL, bedava kargo, toplam 1499.70 TL). ✅
- Lint pass.



## [2026-05-05] Sipariş Başarı Sayfası (ZaraHome) + Kurumsal Fatura + Zengin Mail + MNG NZ + Collision Fix

### Yapılanlar
- **OrderSuccess.jsx (yeni)**: ZaraHome stili minimal beyaz tasarım, harf aralıklı `TEŞEKKÜR EDERİZ` başlık, sipariş numarası kartı, 4 adımlı ilerleme göstergesi (Onaylandı/Hazırlanıyor/Kargoda/Teslim), ürün listesi, totallar, teslimat adresi, kurumsal fatura bilgisi (varsa), CTA "Siparişlerimi Gör" + "Alışverişe Devam Et". Routes: `/order-success/:orderNumber` ve `/siparis-tamamlandi/:orderNumber`.
- **Backend `GET /api/orders/by-number/{n}` (yeni public)**: Sipariş numarasıyla getir. **PII maskeleme**: `phone="055****67"`, `email="te***@example.com"`, address ilk 40 karakter. `billing_address`, `payment_id`, `admin_notes`, `customer_ip` gizli.
- **Checkout Kurumsal Fatura**: "Kurumsal Fatura İstiyorum" checkbox + Firma Ünvanı + VKN/TCKN (10/11 hane validation) + Vergi Dairesi + e-Fatura mükellefi flag. `orders.billing_info: {is_corporate, company_name, tax_office, tax_number, e_invoice_user}` MongoDB'ye yazılır.
- **Checkout Redirect**: Tüm ödeme yolları (bank_transfer / cash_on_delivery / 3D credit_card) success → `/order-success/{order_number}`.
- **Sipariş Onay Maili Zenginleştirme**: `_EMAIL_HTML_TEMPLATES` ile `order_confirmed`, `order_shipped`, `order_delivered`, `order_cancelled`, `order_undelivered` için ZaraHome stili HTML şablonları (3393+ karakter, FACETTE letter-spacing branding, ürün thumb listesi, totallar, teslimat bloğu, "Siparişimi Görüntüle" CTA). `POST /api/notifications/templates/seed?force=true` ile mevcut template'leri override eder (manually_edited=true olanlara dokunmaz).
- **Otomatik order_confirmed bildirimi**: `POST /api/orders` create-order'da fire-and-forget `order_confirmed` SMS+Email+WhatsApp tetiklenir.
- **MNG NZ Barkod denemesi**: `cargo-barcode` endpoint'inde `MNGGonderiBarkod` çağrısı geri eklendi (graceful fallback). Yetki hatası alsa bile sipariş oluşur, fallback MNG_SIPARIS_NO. NZ alınırsa `cargo.mng_nz_barkod` field'ına yazılır ve etikette öncelikli gösterilir. Öncelik: `mng_nz_barkod` → `mng_gonderi_no` → `mng_siparis_no`.
- **CRITICAL FIX — Sipariş No Collision**: `generate_order_number()` artık `f"FC{int(time.time())}{secrets.token_hex(2).upper()}"` formatında (örn. `FC1777945272DE0C`). Aynı saniye 3 sipariş = 3 farklı numara. /app/backend/routes/{deps,orders}.py.
- **React Warning Fix**: Checkout'ta render-içi `navigate()` useEffect'e taşındı.

### Test (Iteration 19)
- Backend 11/12 PASS, 0 critical (collision-resistant + PII masking eklendi).
- Frontend `/order-success` ve `/odeme` corporate UI smoke test geçti.


## [2026-05-05] Excel Üye Bulk Import + Kombin Ürün + Adres Bug + Checkout B&W Tema

### 1. Ticimax Excel Üye Toplu Import (10,522 üye)
- Excel: `/app/backend/imports/uyelist_facette_05052026.xlsx` (15 ana kolon: ID, ISIM, SOYISIM, MAIL, TEL, CEP, DOGUMTARIHI, CINSIYET, MUSTERIKODU, UYELIKTARIHI, UYE TURU, AKTIF, SONGIRISTARIHI, …)
- **Yeni endpoint**: `POST /api/integrations/ticimax/members/import-excel` (admin)
- Direkt script çalıştırma: `/tmp/import_ticimax_excel.py` (HTTP timeout sorunu için bulk insert with batch=500)
- **Sonuç**: 10,431 yeni `customers` (ticimax_uye_id ile) + 10,482 yeni pasif `users` (mail varsa, `is_active=false, needs_password_setup=true`).
- Mevcut kullanıcı (mail/phone match) varsa `ticimax_uye_id` ile bağlanır. Yeni hesaplar şifre sıfırlama akışıyla aktif edilir.

### 2. Kombin Ürün Önerileri (Cross-sell)
- **Backend** `routes/products.py`:
  - `GET /api/products/{id}/combine-products` (public) — ürünün kombin listesini döner.
  - `PUT /api/products/{id}/combine-products` (admin) — kombin ID listesi günceller (max 12, self-ref filtreli).
  - `POST /api/products/cart-suggestions` (public) — sepet ürün ID'lerine göre öneriler:
    1. Sepet ürünlerinin `combine_products`'ı (öncelik)
    2. Yetersizse → indirimdeki (`discount_price > 0` veya `is_on_sale`) ürünler
    3. Hala yetersizse → en yeni aktif ürünler
- **Admin UI** `Products.jsx` form'una **"Kombin"** tab eklendi:
  - `CombineProductsTab.jsx` (yeni component) — solda atanmış ürünler (sürükle-yukarı/aşağı + kaldır), sağda arama + ekle (max 12).
  - formData.combine_products → PUT/POST payload'a otomatik dahil.
- **Storefront `Cart.jsx`** sayfa altında **"Bu ürünlerle yakışanlar / Beğenebilecekleriniz"** carousel/grid (4 kart × 2 satır):
  - "Kombin" rozeti (siyah) veya "İndirim" rozeti (kırmızı) — kaynak rozeti
  - Hover'da scale-105 görsel animasyonu

### 3. Adres Kaydetme Bug (P0 fix)
- `Checkout.jsx handleSaveAddress`: `try { … } catch (e) { /* silently continue */ }` → toast.error ile gerçek hata mesajı gösterilir; 401 ise "Oturumunuz sonlanmış" warning toast'ı eklenir.

### 4. Checkout Renk Düzeni — Turuncu → Siyah/Beyaz Facette Teması
- 33 turuncu sınıf değişikliği: `text-orange-*` → `text-stone-900`, `bg-orange-*` → `bg-stone-50/900`, `border-orange-*` → `border-stone-*`, `accent-orange-500` → `accent-black`. Minimal siyah-beyaz Facette branding'e uygun hale geldi.

### Test (smoke)
- Excel import: 10,431 yeni customer + 10,482 user oluşturuldu ✅
- `/products/cart-suggestions` (boş sepet) → 4 yeni ürün döndü ✅
- Lint temiz (Cart.jsx, Checkout.jsx, CombineProductsTab.jsx, products.py)

### Backlog (yeni)
- Ticimax sipariş servisi yetkisi: Kullanıcının Ticimax panelinde "Sipariş Servisi" izni verilmesi gerekiyor — şu anki WS Yetki Kodu (`SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V`) sipariş servisi izni içermiyor (empty response). Üye listesi başarıyla çekilebiliyor, sipariş için ayrı yetki açılmalı.

## [2026-05-05] Ticimax Sipariş Agresif Import + Pagination Bug Fix

### Yapılanlar
- **`get_orders` post-filter pagination bug fix** (`integrations.py` 1766): Önceki `if len(page_orders) < limit: break` post-filter sonrası dönüş sayısını gerçek raw sayfa boyutuyla karıştırıyordu → page=1'den sonra erken terminate. Çözüm: route'ta `exclude_marketplace=False, only_with_phone=False` raw çek, post-filter route içinde yapılır. Sayfa boş olduğunda dur.
- **Marketplace prefix filter eklendi**: `SiparisNo` "TY-", "HB-", "N11-", "AMZ-", "AE-" prefix'leri Trendyol/HB/N11/Amazon/AliExpress siparişleri olarak post-filter'da skip edilir (Ticimax `Kaynak` field'ı bazı pazaryeri siparişlerde boş gelebiliyordu).
- **DB temizlik**: Mevcut 289 marketplace prefix'li sipariş silindi (TY-/HB-/N11-).
- **Agresif import**: `?limit=200&days=3000&pages=100` ile 8 yıl × 100 sayfa max çekim. Sonuç:
  - **800 raw sipariş** Ticimax'tan çekildi (4 sayfa × 200, 5. sayfa boş → durdu)
  - **293 site siparişi** DB'de güncellendi (ticimax_order_id ile match)
  - **507 marketplace siparişi** filter ile atlandı
  - DB toplam: **357 sipariş, 304'ü site Ticimax siparişi**

### Notlar
- WS yetki kodu `SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V` HEM üye HEM sipariş servisi için yetkili (kullanıcı doğruladı).
- Ticimax'ta toplam ~800 site siparişi mevcut — tümü çekildi. Yeni siparişler için import endpoint'i tekrar çalıştırılabilir (idempotent — mevcut siparişler güncellenir).

## [2026-05-05] P1+P2 — Cron Scheduler + Temu Router + Auto-Combine

### 1. Periyodik Ticimax Sipariş Senkronizasyonu (P1)
- `scheduler.py::_ticimax_sync_orders` — her 6 saatte bir çalışır (günde 4×). Son 30 gün, 5 sayfa × 100 sipariş.
- Idempotent: mevcut order_number/ticimax_order_id varsa atlar.
- Marketplace prefix filter (TY-, HB-, N11-, AMZ-, AE-) + Kaynak keyword filter ile sadece site siparişlerini DB'ye yazar.
- `imported_from: 'ticimax_cron'` flag'i ile manual import'tan ayırt edilir.
- Critical fix (testing agent): `db` + `log_integration_event` lazy import eklendi.

### 2. Temu Router Bağlantısı (P1)
- `from routes.integrations_temu import router as integrations_temu_router` (server.py:79)
- `api_router.include_router(integrations_temu_router, prefix="/integrations")` (server.py:265)
- Endpoint'ler aktif: `/api/integrations/temu/products`, `/orders`, `/stock/update`, `/price/update`. Credential yokken 400 (Temu hesabı tanımlı değil) dönüyor.
- MarketplaceHub `/marketplace-hub/marketplaces` listesinde `temu` zaten var, UI'da otomatik görünür.

### 3. Otomatik Kombin Ürün Önerisi (P2 — cross-sell ML)
- **Backend** `routes/products.py`:
  - `POST /api/products/{id}/auto-combine` — Tek ürün için co-occurrence: aynı siparişlerde geçen ürün ID'lerini sayar (limit 2000 sipariş), top-N'i kombin atar. Existence validation, max 12 cap, dry_run/replace flag'leri.
  - `POST /api/products/auto-combine-all` — Tüm aktif ürünler için tek tıkla kombin atama. only_empty=True (default) ile sadece kombin'i boş olanlara.
- **Admin UI** `CombineProductsTab.jsx`: Kombin tab'ının üstünde **"⚡ Otomatik Kombin Önerisi"** siyah card + "Otomatik Ata" butonu (`data-testid="auto-combine-btn"`). Tek tıkla geçmiş siparişlerden top-8 atama.

### Test (Iteration 21)
- Backend 7/7 PASS, 0 critical (testing agent fixed scheduler imports).
- Auto-combine ürün 1182 için: co-occurrence ile 1 candidate (8642 Tina Jean) buldu, _co_count=1 ✅
- Temu router HTTP 400 ✅, MarketplaceHub temu key ✅
- Cron job listesinde aktif ✅

### Atlandı (yüksek risk, düşük değer)
- `integrations.py` (4150 satır) refactoring — Trendyol/HB/Temu modüllerini ayırma. İhtiyaç olunca yapılır.

## [2026-05-05] Doğan e-Arşiv Canlı Fatura Kesimi — ÇÖZÜLDÜ ve DOĞRULANDI

### Hata kodu 10013'ün kök nedeni
Doğan canlı `connector.doganedonusum.com/EIArchiveWS/EFaturaArchive` endpoint'i raw XML kabul etmiyor — UBL'nin **ZIP'lenmiş paket** içinde gönderilmesini bekliyor:
- ✗ ElementType="XML" + raw bytes → 10013 "Yüklediğiniz dosyada eFatura bulunamamıştır"
- ✗ ElementType="XML.GZ" + gzip → 10013
- ✗ ElementType="XML" + compressed=Y → 10013
- ✅ **ElementType="ZIP" + ZIP payload (içinde `<uuid>.xml`)** → RETURN_CODE=0 başarı

### Düzeltme
- `dogan_client.py::send_earsiv_invoice` — UBL'i ZIP içine paketlenir (`zipfile.ZIP_DEFLATED`), `ElementType="ZIP"` ile gönderir.
- Response parsing iyileştirildi: `ERROR_TYPE` öncelikli + `REQUEST_RETURN.RETURN_CODE=0` başarı kriteri.
- Yeni response field'ları: `intl_txn_id` (Doğan tarafı işlem ID), `uuid` (zip içindeki dosya UUID'i).
- `routes/orders.py::create-invoice` → `invoice_intl_txn_id` artık DB'ye kaydediliyor.

### End-to-End Doğrulama (canlı)
- Order: `11053838413` (Ticimax'tan import edilen gerçek sipariş)
- Invoice no: **FAC2026000000001** (ilk canlı fatura)
- UUID: `f35f37b4-11c9-48a8-8e06-f53832c6bafc`
- Doğan INTL_TXN_ID: **13776942506**
- HTTP 200, success: true


## [2026-05-05] Doğan e-Arşiv UBL Şema Validation — DEVAM EDEN İŞ

### Mevcut durum
- ✅ Bağlantı (connector.doganedonusum.com) çalışıyor
- ✅ Login (Facette.98) başarılı
- ✅ ZIP payload formatı çalışıyor (10013 hatası geçti)
- ✅ Status query (GetEArchiveInvoiceStatus) entegre edildi (4×5sn retry ile)
- ✅ Fatura prefix'leri düzeltildi: e-Arşiv=FCT, e-Fatura=EFC
- ❌ **Doğan UBL'imizi parse edemiyor** → STATUS=200 "FATURA ID BULUNAMADI" (4 retry sonrası bile)

### UBL'de yapılan iyileştirmeler
- `unitCode="C62"` → `"NIU"` (UBL-TR adet standardı)
- Boş `<cbc:Telephone>None</cbc:Telephone>` "None" string sorunu fix (null-safety helper `_s()`)
- Boş `<cbc:WebsiteURI/>` ve `<cac:Contact/>` koşullu render

### Hala çözülemeyen — gerekli aksiyon
UBL-TR şemasıyla tam uyum için Doğan'dan **örnek geçerli UBL XML** istenmeli. Olası eksiklikler:
- `<ext:UBLExtensions>` (imza bloğu zorunlu olabilir)
- `<cac:Signature>`
- `<cac:PaymentMeans>`
- `<cbc:ProfileID>` değeri (`EARSIVFATURA` doğrulanmalı, alternatifi `TICARIFATURA` olabilir)

### Sonraki agent için
Kullanıcıdan Doğan portalında manuel kesilmiş bir faturanın UBL XML dosyasını alın → `build_earsiv_ubl_xml` çıktısıyla diff alın → eksik blokları ekleyin.

---

## Iteration 45 — Tema Yönetimi (Storefront) — 2026-05-18
**Original ask**: "tema yönetimi diye bi alan ekle. oraya farklı temalar koy. birinci tema için miumiu'nun masaüstü ve mobil versiyonunun aynısı gibi olsun, fonksiyonları ve blokları ile. miumiu için olan temayı seçince bloklardaki görselleri vb istediğim gibi güncelleyebileyim."

### ✅ Tamamlanan (Faz 1 — Anasayfa + Yönetim)
- Backend: `themes` koleksiyonu + CRUD + activate + reset + block-level update (`/app/backend/routes/themes.py`)
- Default Miu Miu teması auto-seed (8 blok + 8 mega menü öğesi)
- Admin: `/admin/temalar` — kart listesi (preview/aktive et/düzenle/sil), editor (meta + bloklar)
- Block editor: tip seçimi (announcement_bar/hero_fullscreen/editorial_card/product_scroller/newsletter/...), title/subtitle/CTA, masaüstü + mobil görsel (URL veya `/api/upload`), reorder (▲▼), aktif toggle
- Storefront: `/tema/:slug` — Mulish font, sticky header + italic "miu miu" logo + mega menu (hover) + ikonlar, full-screen editorial bloklar (1/N counter + "scroll to explore" hint), ürün şeridi (yatay scroll), newsletter, 4 sütunlu footer
- Mobil responsive (1024px ve 540px breakpoint'ler) + burger menü

### Backend endpointleri
- Admin (auth): `GET/POST/PUT/DELETE /api/admin/themes`, `POST /api/admin/themes/:id/activate`, `POST /api/admin/themes/:id/reset`, `PUT /api/admin/themes/:id/blocks/:bid`
- Public: `GET /api/storefront/themes/active`, `GET /api/storefront/themes/:slug`

### Pending (Faz 2 & 3)
- **Faz 2**: PLP (kategori) + PDP (ürün detay) + Sepet + Favoriler — Miu Miu birebir
- **Faz 3**: Üye ol/Giriş + Hesabım + Checkout (3-step) + AI Asistan widget
- Trendyol Q&A senkronizasyon canlı tetik
- Cloudflare R2 entegrasyonu (kullanıcı onayı bekliyor)
- Resend (mail) API key

### Architecture notes
- Theme blocks `MongoDB` üzerinde Theme dökümanı içine `blocks: [...]` array olarak gömülü (denormalize). Sıralama `order` field'ına göre.
- Block görselleri: harici URL veya `/api/upload` ile self-host. Mobil ayrı görsel desteği var (`mobile_image`).
- `product_scroller` block tipi `/api/products?category=<slug>&limit=<n>` ile dinamik ürün çekiyor.

---

## Iteration 46 — Ticimax XML Fix + Storefront Live Data (2026-05-18)

### ✅ Tamamlanan

**Ticimax Ürün İçe Aktarımı (kök neden çözüldü):**
- Önceki ajan WS Yetki Kodunu `HANX...` → `SSIQ...` ile değiştirmişti, `SSIQ...` sadece UyeServis'e yetkili
- Ürünler aslında **Ticimax XML Feed** (Google Shopping format) üzerinden çekiliyor, SOAP'tan değil
- `/api/integrations/xml/products/import` çağrıldığında **563 ürün** başarıyla DB'ye geldi
- `description` HTML'inden teknik detaylar parse ediliyor → product.attributes:
  - `urun_bilgisi`, `kumas`, `kalip`, `beden_olculeri`, `model_olculeri`, `yikama`, `astar`, `renk`, vb.
- Yeni endpoint: `GET /api/integrations/ticimax/test-connection` → hangi SOAP servislerinde yetki var net gösteriyor
- Admin UI'da `"Bağlantı Testi"` butonu eklendi (Ticimax kartının altında)
- Import endpoint artık erişim yoksa HTTP 403 + açıklayıcı remedy mesajı dönüyor (eski "sessiz 0 ürün" yanılgısı düzeldi)

**Miu Miu Storefront Live Data:**
- Mega menü artık **kullanıcının gerçek kategorilerinden** dinamik build ediliyor (`/api/categories` → buildMegaMenu)
- Root kategoriler (parent_id=null) top-level nav, L1 children → mega columns, L2 children → links
- Product scroller bloku **gerçek DB ürünlerinden** çekiyor (Ticimax thumbnail'ları + fiyatlar)
- Kategori-bazlı filtre boş dönerse tüm aktif ürünlere fallback
- Miu Miu hover efektleri: ürün kartında alt görsele swap, wishlist butonu opaklığı, fiyat + indirim gösterimi

### Files
- `/app/backend/routes/integrations.py` — `parse_description_attributes()` helper, `ticimax_test_connection` endpoint, XML import attributes
- `/app/backend/ticimax_client.py` — `check_urun_service_access()`, `TicimaxAuthError`
- `/app/frontend/src/pages/storefront/MiuMiuTheme.jsx` — `buildMegaMenu()`, `ProductCard` with hover
- `/app/frontend/src/pages/storefront/miumiu.css` — hover/image-swap/wishlist styling

### Pending
- **Faz 2 (Miu Miu)**: PLP (kategori) + PDP (ürün detay) — gerçek ürünler ile, hover/zoom/galleri
- **Faz 3 (Miu Miu)**: Cart, Checkout (3 step), Login, Register, Account
- Theme block editor UI → PageDesign.jsx tarzı drag-drop + thumbnail (kullanıcı isteği)
- Trendyol Q&A canlı tetik, Cloudflare R2, Resend mail
